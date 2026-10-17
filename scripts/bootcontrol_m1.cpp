// Android BootControl V1 for this single-slot M1 port. Never opens the parent GPT.
// Persistent state uses the standard 32-byte A/B control record in logical misc.
#include <aidl/android/hardware/boot/BnBootControl.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>
#include <android/log.h>
#include <array>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <linux/fs.h>
#include <mutex>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <zlib.h>

using ndk::ScopedAStatus;
using aidl::android::hardware::boot::BnBootControl;
using aidl::android::hardware::boot::MergeStatus;

class M1BootControl final : public BnBootControl {
    int fd_ = -1;
    std::mutex mutex_;
    std::array<uint8_t, 32> state_{};
    static constexpr off_t offset_ = 2048;

    ScopedAStatus error() {
        return ScopedAStatus::fromServiceSpecificErrorWithMessage(COMMAND_FAILED, strerror(errno));
    }
    ScopedAStatus invalid() {
        return ScopedAStatus::fromServiceSpecificErrorWithMessage(INVALID_SLOT, "Only Android slot A exists");
    }
    bool read() {
        if (pread(fd_, state_.data(), state_.size(), offset_) != ssize_t(state_.size())) return false;
        uint32_t magic, stored;
        memcpy(&magic, state_.data()+4, 4); memcpy(&stored, state_.data()+28, 4);
        return magic == 0x42414342 && state_[8] == 1 && (state_[9] & 7) == 1 &&
               stored == uint32_t(crc32(0, state_.data(), 28));
    }
    bool save() {
        uint32_t crc = crc32(0, state_.data(), 28);
        memcpy(state_.data()+28, &crc, 4);
        return pwrite(fd_, state_.data(), state_.size(), offset_) == ssize_t(state_.size()) && fsync(fd_) == 0;
    }
public:
    bool initialize() {
        // Only the dedicated four-MiB mapped slice can be opened by this service.
        fd_ = open("/dev/block/mapper/misc", O_RDWR | O_CLOEXEC);
        struct stat st{}; uint64_t bytes = 0;
        if (fd_ < 0 || fstat(fd_, &st) || !S_ISBLK(st.st_mode) ||
            ioctl(fd_, BLKGETSIZE64, &bytes) || bytes != 4*1024*1024) return false;
        if (!read()) {
            state_.fill(0); memcpy(state_.data(), "_a", 2);
            uint32_t magic = 0x42414342; memcpy(state_.data()+4, &magic, 4);
            state_[8] = 1; state_[9] = 1; state_[12] = 15 | (7 << 4);
            if (!save()) return false;
        }
        return true;
    }
    ~M1BootControl() override { if (fd_ >= 0) close(fd_); }
    ScopedAStatus getActiveBootSlot(int32_t* out) override { *out=0; return ScopedAStatus::ok(); }
    ScopedAStatus getCurrentSlot(int32_t* out) override { *out=0; return ScopedAStatus::ok(); }
    ScopedAStatus getNumberSlots(int32_t* out) override { *out=1; return ScopedAStatus::ok(); }
    ScopedAStatus getSnapshotMergeStatus(MergeStatus* out) override { *out=MergeStatus::NONE; return ScopedAStatus::ok(); }
    ScopedAStatus getSuffix(int32_t slot, std::string* out) override {
        if (slot != 0) return invalid(); *out="_a"; return ScopedAStatus::ok();
    }
    ScopedAStatus isSlotBootable(int32_t slot, bool* out) override {
        if (slot != 0) return invalid(); std::lock_guard lock(mutex_);
        if (!read()) return error();
        *out = (state_[12] & 15) && !(state_[13] & 1) && (state_[12] & 0xf0);
        return ScopedAStatus::ok();
    }
    ScopedAStatus isSlotMarkedSuccessful(int32_t slot, bool* out) override {
        if (slot != 0) return invalid(); std::lock_guard lock(mutex_);
        if (!read()) return error(); *out = state_[12] & 0x80; return ScopedAStatus::ok();
    }
    ScopedAStatus markBootSuccessful() override {
        std::lock_guard lock(mutex_); if (!read()) return error();
        state_[12] |= 0x80; state_[12] = (state_[12] & 0x8f) | 0x10;
        return save() ? ScopedAStatus::ok() : error();
    }
    ScopedAStatus setActiveBootSlot(int32_t slot) override {
        if (slot != 0) return invalid(); std::lock_guard lock(mutex_);
        if (!read()) return error(); state_[12] = 15 | (7 << 4); state_[13] &= ~1;
        return save() ? ScopedAStatus::ok() : error();
    }
    ScopedAStatus setSlotAsUnbootable(int32_t slot) override {
        if (slot != 0) return invalid(); std::lock_guard lock(mutex_);
        if (!read()) return error(); state_[12]=0;
        return save() ? ScopedAStatus::ok() : error();
    }
    ScopedAStatus setSnapshotMergeStatus(MergeStatus status) override {
        if (status == MergeStatus::NONE) return ScopedAStatus::ok();
        return ScopedAStatus::fromExceptionCodeWithMessage(EX_UNSUPPORTED_OPERATION, "Virtual A/B is not enabled on this board");
    }
};

int main() {
    auto service = ndk::SharedRefBase::make<M1BootControl>();
    if (!service->initialize()) {
        __android_log_print(ANDROID_LOG_ERROR, "googlebook-bootctl", "misc initialization failed: %s", strerror(errno));
        return 1;
    }
    ABinderProcess_setThreadPoolMaxThreadCount(0);
    const std::string name = std::string(BnBootControl::descriptor) + "/default";
    if (AServiceManager_addService(service->asBinder().get(), name.c_str()) != STATUS_OK) return 2;
    __android_log_print(ANDROID_LOG_INFO, "googlebook-bootctl", "Single-slot boot control registered; only logical misc is writable");
    ABinderProcess_joinThreadPool();
    return 3;
}
