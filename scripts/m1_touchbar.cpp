// SPDX-License-Identifier: Apache-2.0
// Native J293 function row. Uses Linux DRM/evdev/uinput and frozen Android ILights.
// libdrm modetest demonstrates the KMS/page-flip ABI; no other function-row daemon code used.
#include "m1_touchbar_model.h"
#include "m1_input_key_state.h"
#include <aidl/android/hardware/light/ILights.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>
#include <android/log.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include <linux/input.h>
#include <linux/uinput.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <dirent.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <unistd.h>
#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using googlebook::TouchRow;
using googlebook::RowAction;
using googlebook::RowEvent;
using aidl::android::hardware::light::ILights;
static volatile sig_atomic_t stopped;
static void stop(int) { stopped = 1; }
static void require(bool ok, const char* reason) {
    if (!ok) throw std::runtime_error(std::string(reason)+": "+strerror(errno));
}
struct FD {
    int n = -1;
    FD() = default;
    explicit FD(int value) : n(value) {}
    ~FD() { if (n >= 0) close(n); }
    FD(const FD&) = delete; FD& operator=(const FD&) = delete;
};
static std::vector<std::string> entries(const char* directory, const char* prefix) {
    DIR* dir = opendir(directory); require(dir, directory);
    std::vector<std::string> out;
    while (dirent* entry = readdir(dir)) {
        std::string name = entry->d_name;
        std::string suffix = name.substr(std::min(name.size(), strlen(prefix)));
        if (name.rfind(prefix, 0) == 0 && !suffix.empty() &&
            std::all_of(suffix.begin(), suffix.end(), [](char c) { return c >= '0' && c <= '9'; }))
            out.push_back(std::string(directory)+"/"+name);
    }
    closedir(dir); std::sort(out.begin(), out.end()); return out;
}
static std::string readlinkName(const std::string& path) {
    char text[4096]; ssize_t n = readlink(path.c_str(), text, sizeof(text)-1);
    if (n < 0) return {};
    text[n] = 0; std::string value(text); return value.substr(value.find_last_of('/')+1);
}
struct Scanout {
    int fd = -1;
    uint32_t connector = 0, crtc = 0;
    drmModeModeInfo mode{};
    struct Buffer { uint32_t handle = 0, id = 0, pitch = 0; uint64_t size = 0; void* data = MAP_FAILED; };
    std::array<Buffer, 2> buffers{};
    int front = 0;
    bool pending = false, active = false;
    ~Scanout() {
        if (fd < 0) return;
        // Drop our own scanout before destroying GEM mappings. Never access another DRM device.
        if (active) drmModeSetCrtc(fd, crtc, 0, 0, 0, nullptr, 0, nullptr);
        for (auto& buffer : buffers) {
            if (buffer.data != MAP_FAILED) munmap(buffer.data, buffer.size);
            if (buffer.id) drmModeRmFB(fd, buffer.id);
            if (buffer.handle) { drm_mode_destroy_dumb d{}; d.handle = buffer.handle; drmIoctl(fd, DRM_IOCTL_MODE_DESTROY_DUMB, &d); }
        }
        drmDropMaster(fd); close(fd);
    }
    static bool isNonDesktop(int fd, uint32_t connector) {
        drmModeObjectProperties* props = drmModeObjectGetProperties(fd, connector, DRM_MODE_OBJECT_CONNECTOR);
        if (!props) return false;
        bool found = false;
        for (uint32_t i = 0; i < props->count_props; ++i) {
            drmModePropertyRes* property = drmModeGetProperty(fd, props->props[i]);
            if (!property) continue;
            if (!strcmp(property->name, "non-desktop") && property->count_values == 2 &&
                property->values[0] == 0 && property->values[1] == 1 && props->prop_values[i] == 1) found = true;
            drmModeFreeProperty(property);
        }
        drmModeFreeObjectProperties(props); return found;
    }
    void openDevice() {
        for (const auto& sys : entries("/sys/class/drm", "card")) {
            // Select platform owner before opening any card. DCP/GPU are never opened.
            if (readlinkName(sys+"/device/driver") != "adp") continue;
            require(fd < 0, "multiple ADP controllers are not qualified");
            std::string dev = "/dev/dri/"+sys.substr(sys.find_last_of('/')+1);
            fd = open(dev.c_str(), O_RDWR | O_CLOEXEC | O_NONBLOCK); require(fd >= 0, dev.c_str());
            drmVersion* version = drmGetVersion(fd);
            bool correct = version && version->name_len == 3 && !memcmp(version->name, "adp", 3);
            if (version) drmFreeVersion(version);
            require(correct, "DRM owner must be adp");
        }
        require(fd >= 0, "no ADP card available");
        drmModeRes* resources = drmModeGetResources(fd); require(resources, "ADP resources");
        int choices = 0;
        for (int i = 0; i < resources->count_connectors; ++i) {
            // get_modes publishes Summit's non-desktop property; it must precede the classification.
            drmModeConnector* output = drmModeGetConnector(fd, resources->connectors[i]);
            if (!output) continue;
            if (output->connection == DRM_MODE_CONNECTED && output->count_modes > 0 && isNonDesktop(fd, output->connector_id)) {
                for (int e = 0; e < output->count_encoders; ++e) {
                    drmModeEncoder* encoder = drmModeGetEncoder(fd, output->encoders[e]);
                    if (!encoder) continue;
                    bool chosen = false;
                    for (int c = 0; c < resources->count_crtcs && c < 32; ++c) {
                        if (!(encoder->possible_crtcs & (1u << c))) continue;
                        ++choices; connector = output->connector_id; crtc = resources->crtcs[c]; mode = output->modes[0];
                        chosen = true; break;
                    }
                    drmModeFreeEncoder(encoder); if (chosen) break;
                }
            }
            drmModeFreeConnector(output);
        }
        drmModeFreeResources(resources);
        require(choices == 1 && mode.hdisplay > 0 && mode.hdisplay < mode.vdisplay && mode.vdisplay <= 8192,
                "exactly one portrait non-desktop ADP output required");
        // drmSetMaster fails when someone already owns KMS; never revoke/steal the other owner.
        require(drmIsMaster(fd) == 1 || drmSetMaster(fd) == 0, "ADP KMS master busy");
        for (auto& buffer : buffers) {
            drm_mode_create_dumb create{}; create.width = mode.hdisplay; create.height = mode.vdisplay; create.bpp = 32;
            require(drmIoctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &create) == 0, "create ADP dumb buffer");
            buffer.handle = create.handle; buffer.pitch = create.pitch; buffer.size = create.size;
            require(buffer.pitch >= uint64_t(mode.hdisplay)*4 && buffer.size >= uint64_t(buffer.pitch)*mode.vdisplay && buffer.size < 32*1024*1024,
                    "ADP returned invalid buffer bounds");
            uint32_t handles[4] = {buffer.handle}, pitches[4] = {buffer.pitch}, offsets[4] = {};
            require(drmModeAddFB2(fd, mode.hdisplay, mode.vdisplay, DRM_FORMAT_XRGB8888,
                                handles, pitches, offsets, &buffer.id, 0) == 0, "ADP framebuffer");
            drm_mode_map_dumb map{}; map.handle = buffer.handle;
            require(drmIoctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &map) == 0, "ADP map offset");
            buffer.data = mmap(nullptr, buffer.size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, map.offset);
            require(buffer.data != MAP_FAILED, "map ADP scanout");
        }
        __android_log_print(ANDROID_LOG_INFO, "M1TouchBar", "ADP connector=%u crtc=%u actual mode=%ux%u", connector, crtc, mode.hdisplay, mode.vdisplay);
    }
    static void flipped(int, unsigned, unsigned, unsigned, void* self) { static_cast<Scanout*>(self)->pending = false; }
    void dispatch() {
        drmEventContext context{}; context.version = DRM_EVENT_CONTEXT_VERSION; context.page_flip_handler = flipped;
        require(drmHandleEvent(fd, &context) == 0, "ADP completion event");
    }
    void present(int index) {
        require(!pending, "buffer reuse before actual flip completion");
        if (!active) {
            require(drmModeSetCrtc(fd, crtc, buffers[index].id, 0, 0, &connector, 1, &mode) == 0, "ADP first modeset");
            active = true;
        } else {
            pending = true;
            if (drmModePageFlip(fd, crtc, buffers[index].id, DRM_MODE_PAGE_FLIP_EVENT, this)) {
                pending = false; require(false, "ADP page flip rejected");
            }
        }
        front = index;
    }
};
class Font {
    FT_Library library_ = nullptr;
    FT_Face face_ = nullptr;
public:
    Font() {
        require(FT_Init_FreeType(&library_) == 0, "FreeType init");
        require(FT_New_Face(library_, "/vendor/etc/m1-touchbar/Roboto-Regular.ttf", 0, &face_) == 0, "Android system font");
    }
    ~Font() { if (face_) FT_Done_Face(face_); if (library_) FT_Done_FreeType(library_); }
    void draw(Scanout& display, int index, const TouchRow& row) {
        auto& b = display.buffers[index]; memset(b.data, 0, b.size);
        int width = display.mode.vdisplay, height = display.mode.hdisplay;
        require(FT_Set_Pixel_Sizes(face_, 0, std::max(10, height*2/5)) == 0, "font size");
        auto pixel = [&](int x, int y, uint32_t color) {
            googlebook::rowPixel(static_cast<uint32_t*>(b.data), b.size, b.pitch, display.mode.hdisplay, display.mode.vdisplay, x, y, color);
        };
        for (int key = 0; key < TouchRow::cells; ++key) {
            int left = width*key/TouchRow::cells, right = width*(key+1)/TouchRow::cells;
            for (int y = 4; y < height-4; ++y) for (int x = left+3; x < right-3; ++x) pixel(x, y, 0x181818);
            std::string label = row.key(key).label;
            int advance = 0;
            for (unsigned char c : label) { require(FT_Load_Char(face_, c, FT_LOAD_DEFAULT) == 0, "load glyph"); advance += face_->glyph->advance.x >> 6; }
            int pen = (left+right-advance)/2, baseline = height*2/3;
            for (unsigned char c : label) {
                require(FT_Load_Char(face_, c, FT_LOAD_RENDER) == 0, "render glyph");
                const FT_GlyphSlot glyph = face_->glyph;
                require(glyph->bitmap.pixel_mode == FT_PIXEL_MODE_GRAY && glyph->bitmap.pitch >= 0, "grayscale font raster");
                for (unsigned y = 0; y < glyph->bitmap.rows; ++y) for (unsigned x = 0; x < glyph->bitmap.width; ++x) {
                    unsigned coverage = glyph->bitmap.buffer[y*glyph->bitmap.pitch+x];
                    unsigned level = 24+coverage*231/255;
                    pixel(pen+glyph->bitmap_left+int(x), baseline-glyph->bitmap_top+int(y), level*0x010101);
                }
                pen += glyph->advance.x >> 6;
            }
        }
    }
};
struct Inputs {
    FD touch, keyboard, output;
    TouchRow row;
    bool outputCreated = false, physicalFn = false, stickyFn = false;
    std::array<int, KEY_MAX+1> keyCounts{};
    ~Inputs() { if (outputCreated) { release(); ioctl(output.n, UI_DEV_DESTROY); } if (touch.n >= 0) ioctl(touch.n, EVIOCGRAB, 0); }
    void writeEvents(int code, bool down) {
        input_event events[2] = {}; events[0].type = EV_KEY; events[0].code = code; events[0].value = down; events[1].type = EV_SYN;
        const char* p = reinterpret_cast<const char*>(events); size_t count = sizeof(events);
        while (count) { ssize_t n = write(output.n, p, count); if (n < 0 && errno == EINTR) continue; require(n > 0, "uinput event write"); p += n; count -= n; }
    }
    void key(int code, bool down) {
        if (code <= 0 || code > KEY_MAX) return;
        int& n = keyCounts[code]; if (down) { if (n++ == 0) writeEvents(code, true); }
        else if (n > 0 && --n == 0) writeEvents(code, false);
    }
    void release() noexcept {
        for (int code = 1; code <= KEY_MAX; ++code) if (keyCounts[code]) {
            input_event events[2] = {}; events[0].type = EV_KEY; events[0].code = code; events[1].type = EV_SYN;
            // Best-effort release on owner exit; closing uinput also disconnects the device.
            (void)write(output.n, events, sizeof(events)); keyCounts[code] = 0;
        }
    }
    void openDevices() {
        for (const auto& path : entries("/dev/input", "event")) {
            int fd = open(path.c_str(), O_RDONLY | O_NONBLOCK | O_CLOEXEC);
            if (fd < 0) continue;
            char name[256] = {};
            if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) >= 0) {
                if (!strcmp(name, "MacBookPro17,1 Touch Bar")) { require(touch.n < 0, "ambiguous Touch Bar sensor"); touch.n = fd; fd = -1; }
                else if (!strcmp(name, "Apple SPI Keyboard")) { require(keyboard.n < 0, "ambiguous physical keyboard"); keyboard.n = fd; fd = -1; }
            }
            if (fd >= 0) close(fd);
        }
        require(touch.n >= 0, "Touch Bar evdev missing");
        require(ioctl(touch.n, EVIOCGRAB, 1) == 0, "exclusive Touch Bar sensor owner");
        input_absinfo x{}, y{}, slot{};
        require(ioctl(touch.n, EVIOCGABS(ABS_MT_POSITION_X), &x) == 0 && ioctl(touch.n, EVIOCGABS(ABS_MT_POSITION_Y), &y) == 0 &&
                ioctl(touch.n, EVIOCGABS(ABS_MT_SLOT), &slot) == 0 && slot.minimum == 0 && slot.maximum < TouchRow::slots &&
                row.configure(x.minimum, x.maximum, y.minimum, y.maximum), "Touch Bar multitouch axes");
        row.activeSlot = slot.value;
        require(row.activeSlot >= 0 && row.activeSlot <= slot.maximum, "initial MT slot");
        // A restart with fingers already down must not manufacture presses. Wait for their release.
        std::array<int32_t, TouchRow::slots+1> tracking{}; tracking[0] = ABS_MT_TRACKING_ID;
        require(ioctl(touch.n, EVIOCGMTSLOTS((slot.maximum+2)*sizeof(int32_t)), tracking.data()) == 0, "initial finger census");
        for (int i = 0; i <= slot.maximum; ++i) { row.touches[i].tracking = tracking[i+1]; if (tracking[i+1] >= 0) row.touches[i].held = -2; }
        for (int axis : {ABS_MT_POSITION_X, ABS_MT_POSITION_Y}) {
            tracking[0] = axis;
            require(ioctl(touch.n, EVIOCGMTSLOTS((slot.maximum+2)*sizeof(int32_t)), tracking.data()) == 0, "initial per-slot position cache");
            for (int i = 0; i <= slot.maximum; ++i) {
                if (axis == ABS_MT_POSITION_X) { row.touches[i].x = tracking[i+1]; row.touches[i].validX = true; }
                else { row.touches[i].y = tracking[i+1]; row.touches[i].validY = true; }
            }
        }
        output.n = open("/dev/uinput", O_WRONLY | O_CLOEXEC); require(output.n >= 0, "uinput");
        require(ioctl(output.n, UI_SET_EVBIT, EV_KEY) == 0 && ioctl(output.n, UI_SET_EVBIT, EV_SYN) == 0, "uinput event types");
        for (bool fn : {false, true}) { row.functionKeys = fn; for (int i = 0; i < TouchRow::cells; ++i) if (row.key(i).code) require(ioctl(output.n, UI_SET_KEYBIT, row.key(i).code) == 0, "uinput key capability"); }
        row.functionKeys = false;
        uinput_setup setup{}; setup.id.bustype = BUS_VIRTUAL;
        strcpy(setup.name, "GoogleBook M1 Native Function Row");
        require(ioctl(output.n, UI_DEV_SETUP, &setup) == 0 && ioctl(output.n, UI_DEV_CREATE) == 0, "create truthful virtual function row");
        outputCreated = true;
        if (keyboard.n >= 0) {
            int copied = refreshFn();
            __android_log_print(ANDROID_LOG_INFO, "M1TouchBar", "Actual keyboard EVIOCGKEY snapshot: %d bytes, Fn=%d", copied, physicalFn);
        }
        __android_log_print(ANDROID_LOG_INFO, "M1TouchBar", "Real Touch Bar axes X=%d..%d Y=%d..%d slots=%d; keyboard is read-only, never grabbed", x.minimum, x.maximum, y.minimum, y.maximum, slot.maximum+1);
    }
    int refreshFn() {
        int copied = 0;
        int result = googlebook::readInputKeyState(keyboard.n, KEY_FN, &physicalFn, &copied);
        if (result) { errno = -result; require(false, "physical Fn state"); }
        return copied;
    }
};
class LightClient {
    std::shared_ptr<ILights> service_;
public:
    bool brightness(int id, unsigned value) {
        if (!service_ || !AIBinder_isAlive(service_->asBinder().get())) {
            ndk::SpAIBinder binder(AServiceManager_checkService("android.hardware.light.ILights/default"));
            service_ = ILights::fromBinder(binder);
        }
        if (!service_) { __android_log_print(ANDROID_LOG_ERROR, "M1TouchBar", "ILights owner unavailable"); return false; }
        aidl::android::hardware::light::HwLightState state{}; state.color = 0xff000000u | (std::min(value, 255u)*0x010101u);
        auto result = service_->setLightState(id, state);
        if (!result.isOk()) __android_log_print(ANDROID_LOG_ERROR, "M1TouchBar", "ILights id=%d rejected request: %s", id, result.getDescription().c_str());
        if (result.isOk()) __android_log_print(ANDROID_LOG_INFO, "M1TouchBar", "ILights id=%d request=%u accepted by kernel-backed owner", id, std::min(value, 255u));
        return result.isOk();
    }
    int keyboardLevel() {
        auto number = [](const char* path) {
            FD fd(open(path, O_RDONLY | O_CLOEXEC)); if (fd.n < 0) return -1;
            char text[32] = {}; ssize_t n = read(fd.n, text, sizeof(text)-1); if (n <= 0) return -1;
            char* end; long value = strtol(text, &end, 10); if (end == text || value < 0 || value > 65535) return -1; return int(value);
        };
        int max = number("/sys/class/leds/kbd_backlight/max_brightness"), value = number("/sys/class/leds/kbd_backlight/brightness");
        if (max <= 0 || value < 0 || value > max) return -1;
        return (int64_t(value)*255+max/2)/max;
    }
};
int main(int argc, char**) {
    if (argc != 1) { fprintf(stderr, "m1-touchbar takes no options; production hardware owners only\n"); return 2; }
    signal(SIGTERM, stop); signal(SIGINT, stop);
    ABinderProcess_setThreadPoolMaxThreadCount(2); ABinderProcess_startThreadPool();
    try {
        Scanout display; display.openDevice(); Font font; Inputs input; input.openDevices(); LightClient lights;
        input.row.functionKeys = input.physicalFn;
        font.draw(display, 0, input.row); display.present(0);
        bool lit = lights.brightness(2, 180), dirty = false;
        auto activity = std::chrono::steady_clock::now();
        auto flipStarted = activity;
        auto lightAttempt = activity;
        while (!stopped) {
            pollfd polls[] = {{display.fd, POLLIN, 0}, {input.touch.n, POLLIN, 0}, {input.keyboard.n, POLLIN, 0}};
            int rc = poll(polls, 3, 1000); if (rc < 0 && errno == EINTR) continue; require(rc >= 0, "poll native row owners");
            for (auto p : polls) require(!(p.revents & (POLLHUP | POLLERR | POLLNVAL)), "native row owner disconnected");
            if (polls[0].revents & POLLIN) display.dispatch();
            for (int source = 1; source <= 2; ++source) {
                if (!(polls[source].revents & POLLIN)) continue;
                input_event events[64]; ssize_t count = read(polls[source].fd, events, sizeof(events));
                if (count < 0 && errno == EAGAIN) continue;
                require(count > 0 && count % sizeof(input_event) == 0, "evdev event framing");
                for (size_t i = 0; i < size_t(count)/sizeof(input_event); ++i) {
                    const auto& event = events[i];
                    // Exit releases every held key and fd. Init restarts, performs a fresh kernel slot census.
                    require(!(event.type == EV_SYN && event.code == SYN_DROPPED), "evdev overflow; re-census required");
                    if (source == 2) {
                        if (event.type == EV_SYN && event.code == SYN_REPORT) input.refreshFn();
                    } else if (event.type == EV_ABS) {
                        if (event.code == ABS_MT_SLOT) { require(event.value >= 0 && event.value < TouchRow::slots, "invalid touch slot"); input.row.activeSlot = event.value; }
                        auto& touch = input.row.touches[input.row.activeSlot];
                        if (event.code == ABS_MT_TRACKING_ID) { require(event.value >= -1, "invalid tracking id"); input.row.begin(event.value); }
                        if (event.code == ABS_MT_POSITION_X) { touch.x = event.value; touch.validX = true; }
                        if (event.code == ABS_MT_POSITION_Y) { touch.y = event.value; touch.validY = true; }
                    } else if (event.type == EV_SYN && event.code == SYN_REPORT) {
                        for (const RowEvent& action : input.row.report()) {
                            if (action.key.action == RowAction::Key) input.key(action.key.code, action.down);
                            else if (!action.down && action.key.action == RowAction::ToggleFn) input.stickyFn = !input.stickyFn;
                            else if (!action.down) {
                                int current = lights.keyboardLevel();
                                if (current >= 0) lights.brightness(1, std::clamp(current+(action.key.action == RowAction::KeyboardUp ? 32 : -32), 0, 255));
                                else __android_log_print(ANDROID_LOG_ERROR, "M1TouchBar", "Keyboard PWM state unreadable; command not sent");
                            }
                        }
                    }
                    bool function = input.physicalFn != input.stickyFn;
                    if (function != input.row.functionKeys) {
                        for (const auto& action : input.row.cancel()) input.key(action.key.code, action.down);
                        input.row.functionKeys = function; dirty = true;
                    }
                }
                activity = std::chrono::steady_clock::now();
            }
            auto now = std::chrono::steady_clock::now();
            require(!display.pending || now-flipStarted < std::chrono::seconds(3), "ADP flip completion timeout");
            if (dirty && !display.pending) {
                int next = 1-display.front; font.draw(display, next, input.row); display.present(next); flipStarted = now; dirty = false;
            }
            // Event-driven rendering; no animation loop. Actual keyboard/touch activity wakes the row.
            bool wantLit = now-activity <= std::chrono::seconds(60);
            // HAL startup/death is independent of KMS. Retry a missing owner
            // at a bounded rate, and never make a per-touch-event Binder loop.
            if (wantLit != lit && now-lightAttempt >= std::chrono::seconds(1)) {
                lightAttempt = now;
                if (lights.brightness(2, wantLit ? 180 : 0)) lit = wantLit;
            }
        }
        input.release(); lights.brightness(2, 0);
        return 0;
    } catch (const std::exception& error) {
        __android_log_print(ANDROID_LOG_ERROR, "M1TouchBar", "Owner stopped: %s", error.what());
        fprintf(stderr, "M1TouchBar: %s\n", error.what()); return 1;
    }
}
