// SPDX-License-Identifier: Apache-2.0
// Functional diagnostic: decode a generated clip and compare every YUV sample.
#include <media/NdkMediaCodec.h>
#include <media/NdkMediaExtractor.h>
#include <media/NdkMediaFormat.h>
#include <android/binder_process.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <cstdint>
#include <cstdio>
#include <ctime>
#include "codec_reference.h"

static uint64_t hash_bytes(uint64_t h, const uint8_t* data, size_t n) {
    for (size_t i = 0; i < n; ++i) { h ^= data[i]; h *= UINT64_C(1099511628211); }
    return h;
}

int main(int argc, char** argv) {
    setbuf(stdout, nullptr);
    if (argc != 2) return 2;
    // This standalone process must service Codec2's incoming Binder callbacks.
    if (!ABinderProcess_setThreadPoolMaxThreadCount(4)) return 16;
    ABinderProcess_startThreadPool();
    if (!ABinderProcess_isThreadPoolStarted()) return 17;
    int fd = open(argv[1], O_RDONLY | O_CLOEXEC);
    struct stat st{};
    if (fd < 0 || fstat(fd, &st)) return 3;
    AMediaExtractor* ex = AMediaExtractor_new();
    if (!ex || AMediaExtractor_setDataSourceFd(ex, fd, 0, st.st_size) != AMEDIA_OK) return 4;
    close(fd);
    if (AMediaExtractor_getTrackCount(ex) != 1) return 5;
    AMediaFormat* fmt = AMediaExtractor_getTrackFormat(ex, 0);
    const char* mime = nullptr;
    if (!fmt || !AMediaFormat_getString(fmt, AMEDIAFORMAT_KEY_MIME, &mime)) return 6;
    printf("CODEC_INPUT_FORMAT %s\n", AMediaFormat_toString(fmt));
    AMediaExtractor_selectTrack(ex, 0);
    AMediaFormat_setInt32(fmt, AMEDIAFORMAT_KEY_COLOR_FORMAT, 19); // planar YUV420
    AMediaCodec* c = AMediaCodec_createCodecByName("c2.android.avc.decoder");
    if (!c) return 7;
    if (AMediaCodec_configure(c, fmt, nullptr, nullptr, 0) != AMEDIA_OK ||
        AMediaCodec_start(c) != AMEDIA_OK) return 8;
    AMediaFormat_delete(fmt);
    bool input_eos = false, output_eos = false;
    int frames = 0, inputs = 0, width = 0, height = 0, stride = 0, slice = 0, color = 0;
    timespec now{};
    clock_gettime(CLOCK_MONOTONIC, &now);
    const time_t deadline = now.tv_sec + 30;
    while (!output_eos && now.tv_sec < deadline) {
        if (!input_eos) {
            ssize_t i = AMediaCodec_dequeueInputBuffer(c, 10000);
            if (i >= 0) {
                size_t cap = 0;
                uint8_t* buf = AMediaCodec_getInputBuffer(c, i, &cap);
                if (!buf || !cap) return 15;
                ssize_t n = AMediaExtractor_readSampleData(ex, buf, cap);
                input_eos = n < 0;
                int64_t pts = input_eos ? 0 : AMediaExtractor_getSampleTime(ex);
                if (AMediaCodec_queueInputBuffer(c, i, 0, input_eos ? 0 : n, pts,
                        input_eos ? AMEDIACODEC_BUFFER_FLAG_END_OF_STREAM : 0) != AMEDIA_OK) return 9;
                ++inputs;
                if (!input_eos) AMediaExtractor_advance(ex);
            }
        }
        AMediaCodecBufferInfo info{};
        ssize_t o = AMediaCodec_dequeueOutputBuffer(c, &info, 10000);
        if (o == AMEDIACODEC_INFO_OUTPUT_FORMAT_CHANGED) {
            AMediaFormat* out = AMediaCodec_getOutputFormat(c);
            printf("CODEC_OUTPUT_FORMAT %s\n", AMediaFormat_toString(out));
            AMediaFormat_getInt32(out, AMEDIAFORMAT_KEY_WIDTH, &width);
            AMediaFormat_getInt32(out, AMEDIAFORMAT_KEY_HEIGHT, &height);
            AMediaFormat_getInt32(out, AMEDIAFORMAT_KEY_COLOR_FORMAT, &color);
            if (!AMediaFormat_getInt32(out, "stride", &stride)) stride = width;
            if (!AMediaFormat_getInt32(out, "slice-height", &slice)) slice = height;
            AMediaFormat_delete(out);
        } else if (o >= 0) {
            if (info.size > 0) {
                size_t cap = 0;
                uint8_t* buf = AMediaCodec_getOutputBuffer(c, o, &cap);
                if (width != 64 || height != 48 || color != 19 || stride < width ||
                    slice < height || stride % 2 || slice % 2 || frames >= 4 ||
                    !buf || info.offset < 0) return 10;
                size_t plane = size_t(stride) * slice;
                size_t bytes = plane + plane / 2;
                if (size_t(info.offset) > cap || cap - info.offset < bytes || size_t(info.size) < bytes) return 11;
                const uint8_t* p = buf + info.offset;
                uint64_t h = UINT64_C(14695981039346656037);
                for (int y = 0; y < height; ++y) h = hash_bytes(h, p + y * stride, width);
                for (int uv = 0; uv < 2; ++uv)
                    for (int y = 0; y < height / 2; ++y)
                        h = hash_bytes(h, p + plane + uv * plane / 4 + y * stride / 2, width / 2);
                printf("CODEC_FRAME %d fnv64=%016llx expected=%016llx\n", frames,
                       (unsigned long long)h, (unsigned long long)kExpected[frames]);
                if (h != kExpected[frames++]) return 12;
            }
            output_eos = info.flags & AMEDIACODEC_BUFFER_FLAG_END_OF_STREAM;
            AMediaCodec_releaseOutputBuffer(c, o, false);
        } else if (o != AMEDIACODEC_INFO_TRY_AGAIN_LATER &&
                   o != AMEDIACODEC_INFO_OUTPUT_BUFFERS_CHANGED) return 13;
        clock_gettime(CLOCK_MONOTONIC, &now);
    }
    printf("CODEC_SUMMARY inputs=%d frames=%d input_eos=%d output_eos=%d\n",
           inputs, frames, input_eos, output_eos);
    AMediaCodec_stop(c);
    AMediaCodec_delete(c);
    AMediaExtractor_delete(ex);
    if (!output_eos || frames != 4) return 14;
    puts("AOSP_AVC_FOUR_FRAMES_PIXEL_EXACT_PASS");
    return 0;
}
