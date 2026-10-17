// Disable the unsupported Qualcomm SDM backend in the original desktop HWC.
// Its eager initialization can replace the generic buffer importer globally.
// Returning "unsupported" leaves the real DRM/KMS GenericBackend registered.
#include <android/log.h>
#include <errno.h>
#include <stdint.h>
#include <xf86drmMode.h>

namespace sdm {
class SDMInterfaceFactory;
__attribute__((visibility("default")))
SDMInterfaceFactory *GetSDMInterfaceFactory() { return nullptr; }
}

static void trace_fb(int fd, uint32_t width, uint32_t height, uint32_t format,
                     const uint32_t *handles, const uint32_t *pitches,
                     const uint32_t *offsets, uint32_t flags, int result, int error)
{
    static unsigned int calls;
    if (__atomic_fetch_add(&calls, 1, __ATOMIC_RELAXED) >= 32) return;
    __android_log_print(ANDROID_LOG_WARN, "googlebook-drm",
        "ADDFB2 fd=%d %ux%u fmt=%08x handles=%u,%u,%u,%u pitches=%u,%u,%u,%u offsets=%u,%u,%u,%u flags=%x ret=%d errno=%d",
        fd, width, height, format, handles[0], handles[1], handles[2], handles[3],
        pitches[0], pitches[1], pitches[2], pitches[3],
        offsets[0], offsets[1], offsets[2], offsets[3], flags, result, error);
}

extern "C" int gosModeAddFB2(int fd, uint32_t width, uint32_t height, uint32_t format,
                            const uint32_t handles[4], const uint32_t pitches[4],
                            const uint32_t offsets[4], uint32_t *buffer_id, uint32_t flags)
{
    int result = drmModeAddFB2(fd, width, height, format, handles, pitches, offsets, buffer_id, flags);
    int error = errno;
    trace_fb(fd, width, height, format, handles, pitches, offsets, flags, result, error);
    errno = error;
    return result;
}

extern "C" int gosModeAddFB2WithModifiers(int fd, uint32_t width, uint32_t height, uint32_t format,
                                         const uint32_t handles[4], const uint32_t pitches[4],
                                         const uint32_t offsets[4], const uint64_t modifiers[4],
                                         uint32_t *buffer_id, uint32_t flags)
{
    int result = drmModeAddFB2WithModifiers(fd, width, height, format, handles, pitches,
                                           offsets, modifiers, buffer_id, flags);
    int error = errno;
    trace_fb(fd, width, height, format, handles, pitches, offsets, flags, result, error);
    errno = error;
    return result;
}
