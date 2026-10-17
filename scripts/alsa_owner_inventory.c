// SPDX-License-Identifier: Apache-2.0
// Read the kernel ALSA control ABI. Never opens a PCM data device or writes controls.
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <sound/asound.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static void string(const unsigned char *s, size_t limit) {
    putchar('"');
    for (size_t i = 0; i < limit && s[i]; ++i) {
        if (s[i] == '"' || s[i] == '\\') printf("\\%c", s[i]);
        else if (s[i] < 32 || s[i] >= 127) printf("\\u%04x", s[i]);
        else putchar(s[i]);
    }
    putchar('"');
}

static void error(const char *op, int err) {
    printf("GOS_ALSA_JSON {\"kind\":\"error\",\"operation\":\"%s\",\"errno\":%d}\n", op, err);
}

static int inspect(const char *path) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) { error("open-control", errno); return 1; }
    struct snd_ctl_card_info card = {0};
    if (ioctl(fd, SNDRV_CTL_IOCTL_CARD_INFO, &card)) {
        error("card-info", errno); close(fd); return 1;
    }
    printf("GOS_ALSA_JSON {\"kind\":\"card\",\"card\":%d,\"path\":", card.card);
    string((const unsigned char *)path, strlen(path));
    printf(",\"id\":"); string(card.id, sizeof(card.id));
    printf(",\"driver\":"); string(card.driver, sizeof(card.driver));
    printf(",\"name\":"); string(card.name, sizeof(card.name));
    printf(",\"longname\":"); string(card.longname, sizeof(card.longname));
    printf(",\"components\":"); string(card.components, sizeof(card.components));
    puts("}");
    int device = -1, last = -1, incomplete = 0;
    for (;;) {
        if (ioctl(fd, SNDRV_CTL_IOCTL_PCM_NEXT_DEVICE, &device)) { error("pcm-next", errno); incomplete = 1; break; }
        if (device < 0) break;
        if (device <= last) { error("pcm-nonmonotonic", EPROTO); incomplete = 1; break; }
        last = device;
        for (int direction = 0; direction < 2; ++direction) {
            struct snd_pcm_info info = {.device = (unsigned)device, .stream = direction};
            if (ioctl(fd, SNDRV_CTL_IOCTL_PCM_INFO, &info)) {
                if (errno != ENOENT && errno != ENODEV && errno != ENXIO) incomplete = 1;
                printf("GOS_ALSA_JSON {\"kind\":\"pcm-query-error\",\"card\":%d,\"device\":%d,\"stream\":%d,\"errno\":%d}\n",
                       card.card, device, direction, errno);
                continue;
            }
            printf("GOS_ALSA_JSON {\"kind\":\"pcm\",\"card\":%d,\"device\":%u,\"stream\":%d,\"subdevices\":%u,\"id\":",
                   info.card, info.device, info.stream, info.subdevices_count);
            string(info.id, sizeof(info.id)); printf(",\"name\":"); string(info.name, sizeof(info.name));
            puts("}");
        }
    }
    struct snd_ctl_elem_list list = {0};
    if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_LIST, &list)) { error("control-count", errno); close(fd); return 1; }
    if (list.count > 8192) { error("control-count-bound", EOVERFLOW); close(fd); return 1; }
    list.space = list.count;
    list.pids = calloc(list.space ? list.space : 1, sizeof(*list.pids));
    if (!list.pids) { close(fd); return 1; }
    if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_LIST, &list)) {
        error("control-list", errno); free(list.pids); close(fd); return 1;
    }
    if (list.used > list.space) { error("control-list-bound", EOVERFLOW); free(list.pids); close(fd); return 1; }
    if (list.count > list.space) { error("control-list-changed", EAGAIN); incomplete = 1; }
    printf("GOS_ALSA_JSON {\"kind\":\"control-list\",\"card\":%d,\"count\":%u,\"read\":%u}\n", card.card, list.count, list.used);
    for (unsigned i = 0; i < list.used; ++i) {
        struct snd_ctl_elem_info info = {.id = list.pids[i]};
        if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_INFO, &info)) { error("control-info", errno); incomplete = 1; continue; }
        printf("GOS_ALSA_JSON {\"kind\":\"control\",\"card\":%d,\"numid\":%u,\"index\":%u,\"type\":%d,\"count\":%u,\"access\":%u,\"name\":",
               card.card, info.id.numid, info.id.index, info.type, info.count, info.access);
        string(info.id.name, sizeof(info.id.name));
        if (info.type == SNDRV_CTL_ELEM_TYPE_INTEGER || info.type == SNDRV_CTL_ELEM_TYPE_BOOLEAN)
            printf(",\"min\":%ld,\"max\":%ld,\"step\":%ld", info.value.integer.min, info.value.integer.max, info.value.integer.step);
        if (info.type == SNDRV_CTL_ELEM_TYPE_INTEGER64)
            printf(",\"min\":%lld,\"max\":%lld,\"step\":%lld", info.value.integer64.min, info.value.integer64.max, info.value.integer64.step);
        unsigned items = info.type == SNDRV_CTL_ELEM_TYPE_ENUMERATED ? info.value.enumerated.items : 0;
        if (items) printf(",\"enum_items\":%u", items);
        puts("}");
        for (unsigned item = 0; item < items && item < 1024; ++item) {
            info.value.enumerated.item = item;
            if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_INFO, &info)) { error("enum-info", errno); incomplete = 1; break; }
            printf("GOS_ALSA_JSON {\"kind\":\"enum\",\"card\":%d,\"numid\":%u,\"item\":%u,\"name\":", card.card, info.id.numid, item);
            string((const unsigned char *)info.value.enumerated.name, sizeof(info.value.enumerated.name)); puts("}");
        }
        if (items > 1024) { error("enum-truncated", EOVERFLOW); incomplete = 1; }
    }
    free(list.pids); close(fd); return incomplete;
}

int main(int argc, char **argv) {
    if (argc != 1 && !(argc == 2 && !strcmp(argv[1], "--preboot-nodes"))) return 2;
    setvbuf(stdout, NULL, _IOLBF, 4096);
    puts("GOS_ALSA_CONTROL_INVENTORY_BEGIN");
    glob_t paths = {0};
    const char *pattern = argc == 2 ? "/gos-owner/devsnd/controlC*" : "/dev/snd/controlC*";
    int rc = glob(pattern, 0, NULL, &paths), failed = 0;
    if (rc) { printf("GOS_ALSA_JSON {\"kind\":\"discovery-error\",\"glob_result\":%d}\n", rc); failed = 1; }
    else for (size_t i = 0; i < paths.gl_pathc; ++i) failed |= inspect(paths.gl_pathv[i]);
    printf("GOS_ALSA_CONTROL_INVENTORY_END discovered=%zu rc=%d\n", paths.gl_pathc, failed);
    globfree(&paths); return failed;
}
