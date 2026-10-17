// SPDX-License-Identifier: Apache-2.0
#include "m1_touchbar_model.h"
#include <cstddef>
#include <linux/input-event-codes.h>

namespace googlebook {
bool TouchRow::configure(int x0, int x1, int y0, int y1) {
    if (x0 >= x1 || y0 >= y1) return false;
    minX = x0; maxX = x1; minY = y0; maxY = y1; return true;
}
int TouchRow::hit(int x, int y) const {
    if (maxX <= minX || maxY <= minY || x < minX || x > maxX || y < minY || y > maxY) return -1;
    return static_cast<int>((int64_t(x)-minX)*cells/(int64_t(maxX)-minX+1));
}
RowKey TouchRow::key(int cell) const {
    if (cell == 12) return {"Fn", 0, RowAction::ToggleFn};
    if (cell < 0 || cell >= 12) return {"", 0, RowAction::Key};
    static const RowKey functions[] = {{"F1", KEY_F1, RowAction::Key}, {"F2", KEY_F2, RowAction::Key},
        {"F3", KEY_F3, RowAction::Key}, {"F4", KEY_F4, RowAction::Key}, {"F5", KEY_F5, RowAction::Key},
        {"F6", KEY_F6, RowAction::Key}, {"F7", KEY_F7, RowAction::Key}, {"F8", KEY_F8, RowAction::Key},
        {"F9", KEY_F9, RowAction::Key}, {"F10", KEY_F10, RowAction::Key}, {"F11", KEY_F11, RowAction::Key},
        {"F12", KEY_F12, RowAction::Key}};
    static const RowKey controls[] = {{"Dim", KEY_BRIGHTNESSDOWN, RowAction::Key},
        {"Bright", KEY_BRIGHTNESSUP, RowAction::Key}, {"K-", 0, RowAction::KeyboardDown},
        {"K+", 0, RowAction::KeyboardUp}, {"Prev", KEY_PREVIOUSSONG, RowAction::Key},
        {"Play", KEY_PLAYPAUSE, RowAction::Key}, {"Next", KEY_NEXTSONG, RowAction::Key},
        {"Mute", KEY_MUTE, RowAction::Key}, {"Vol-", KEY_VOLUMEDOWN, RowAction::Key},
        {"Vol+", KEY_VOLUMEUP, RowAction::Key}, {"F11", KEY_F11, RowAction::Key}, {"F12", KEY_F12, RowAction::Key}};
    return functionKeys ? functions[cell] : controls[cell];
}
void TouchRow::begin(int tracking) {
    auto& slot = touches[activeSlot];
    if (tracking == slot.tracking) return;
    // Protocol B may retire and reuse one slot within a single SYN_REPORT.
    // Preserve the old release until report(); a replacement without an
    // explicit lift cancels local actions rather than inventing a tap.
    if (slot.held >= 0) {
        auto old = key(slot.held);
        if (tracking < 0 || old.action == RowAction::Key) pending.push_back({old, false});
    }
    slot.tracking = tracking;
    slot.held = -1;
    // Type-B positions persist across contacts. The kernel omits unchanged axes;
    // validity describes our per-slot cache, not the current contact lifetime.
}
std::vector<RowEvent> TouchRow::report() {
    std::vector<RowEvent> out; out.swap(pending);
    for (auto& slot : touches) {
        int cell = slot.tracking >= 0 && slot.validX && slot.validY ? hit(slot.x, slot.y) : -1;
        if (slot.held >= 0 && (slot.tracking < 0 || cell != slot.held)) {
            RowKey old = key(slot.held);
            // Cancel local actions when a finger slides outside its original key.
            if (old.action == RowAction::Key || slot.tracking < 0) out.push_back({old, false});
            slot.held = -2; // no new press until this finger lifts
        }
        if (slot.tracking < 0) slot.held = -1;
        else if (slot.held == -1 && cell >= 0) { slot.held = cell; out.push_back({key(cell), true}); }
    }
    return out;
}
std::vector<RowEvent> TouchRow::cancel() {
    std::vector<RowEvent> out;
    for (const auto& event : pending) if (!event.down && event.key.action == RowAction::Key) out.push_back(event);
    pending.clear();
    for (auto& slot : touches) {
        if (slot.held >= 0 && key(slot.held).action == RowAction::Key) out.push_back({key(slot.held), false});
        slot.held = slot.tracking >= 0 ? -2 : -1;
    }
    return out;
}
bool rowPixel(uint32_t* data, size_t bytes, unsigned pitch, unsigned w, unsigned h,
              int x, int y, uint32_t color) {
    if (!data || x < 0 || y < 0 || unsigned(x) >= h || unsigned(y) >= w ||
        uint64_t(w)*4 > pitch || uint64_t(pitch)*h > bytes) return false;
    unsigned px = w-1-unsigned(y), py = unsigned(x);
    data[(uint64_t(py)*pitch)/4+px] = color; return true;
}
}
