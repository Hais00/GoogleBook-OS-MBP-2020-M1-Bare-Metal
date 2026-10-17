// SPDX-License-Identifier: Apache-2.0
#include "m1_touchbar_model.h"
#include <cstdio>
#include <cstdlib>
#include <climits>
#include <vector>
using namespace googlebook;
static void check(bool ok, const char* message) { if (!ok) { fprintf(stderr, "ROW_MODEL_FAIL: %s\n", message); exit(1); } }
static void contact(TouchRow& row, int slot, int x, int y) {
    row.activeSlot = slot; row.begin(slot+100); auto& touch = row.touches[slot];
    touch.x = x; touch.y = y; touch.validX = touch.validY = true;
}
int main() {
    TouchRow row;
    check(!row.configure(1, 1, 0, 1), "degenerate range rejected");
    check(row.hit(0, 0) == -1, "unconfigured input cannot emit keys");
    check(row.configure(100, 23045, 10, 640), "actual sensor extents accepted");
    check(row.hit(100, 10) == 0 && row.hit(23045, 640) == 12, "physical endpoints map to first/last keys");
    check(row.hit(99, 10) == -1 && row.hit(100, 641) == -1, "out-of-range coordinates rejected");
    check(row.configure(INT_MIN, INT_MAX, -1, 1), "full signed range is safe");
    check(row.hit(INT_MAX, 1) == 12 && row.hit(INT_MIN, -1) == 0, "hit test uses overflow-safe arithmetic");
    check(row.configure(0, 1299, 0, 60), "fixture extents accepted");
    row.activeSlot = 0; row.begin(100);
    check(row.report().empty(), "tracking id before coordinates cannot press a key");
    row.touches[0].x = 50; row.touches[0].validX = true;
    check(row.report().empty(), "both axes required on a new contact");
    row.touches[0].y = 30; row.touches[0].validY = true;
    auto events = row.report(); check(events.size() == 1 && events[0].down && events[0].key.code != 0, "single actual press");
    check(row.report().empty(), "stationary contact does not generate repeated presses");
    row.touches[0].x = 160; events = row.report();
    check(events.size() == 1 && !events[0].down, "sliding out releases original key");
    row.touches[0].x = 50;
    check(row.report().empty(), "sliding back never creates a new press without lift");
    row.begin(-1); check(row.report().empty(), "cancelled drag does not duplicate key release");
    contact(row, 0, 250, 30); events = row.report();
    check(events.size() == 1 && events[0].key.action == RowAction::KeyboardDown && events[0].down, "keyboard action armed by real touch");
    row.touches[0].x = 450; check(row.report().empty(), "drag cancels keyboard brightness action");
    row.begin(-1); check(row.report().empty(), "cancelled brightness is never applied on lift");
    contact(row, 0, 350, 30); row.report(); row.begin(-1); events = row.report();
    check(events.size() == 1 && !events[0].down && events[0].key.action == RowAction::KeyboardUp, "one brightness action after a completed tap");
    row.functionKeys = true;
    contact(row, 0, 50, 30); contact(row, 255, 150, 30); events = row.report();
    check(events.size() == 2 && events[0].key.code != events[1].key.code, "independent simultaneous fingers including slot255");
    events = row.cancel(); check(events.size() == 2 && !events[0].down && !events[1].down, "layout/owner cancellation releases all held keys");
    check(row.report().empty(), "held fingers remain suppressed after a mode change");
    TouchRow reused; check(reused.configure(0, 1299, 0, 60), "replacement sensor configured");
    contact(reused, 0, 50, 30); reused.report();
    reused.begin(-1); reused.begin(200); reused.touches[0].x=150; reused.touches[0].y=30;
    reused.touches[0].validX=reused.touches[0].validY=true; events=reused.report();
    check(events.size()==2 && !events[0].down && events[1].down && events[0].key.code!=events[1].key.code,
          "same-frame slot reuse releases old contact before pressing new contact");
    reused.begin(-1); events=reused.cancel();
    check(events.size()==1 && !events[0].down, "layout change preserves a queued key release");
    check(reused.report().empty(), "queued release is consumed exactly once");
    reused.begin(300); events=reused.report();
    check(events.size()==1 && events[0].down, "unchanged kernel positions survive contact reuse without new ABS samples");
    reused.begin(-1); events=reused.report();
    check(events.size()==1 && !events[0].down, "unchanged-position tap releases normally");
    std::vector<uint32_t> pixels(16, 0xdeadbeef);
    check(rowPixel(pixels.data()+1, 12*sizeof(uint32_t), 16, 3, 3, 0, 0, 1), "portrait pitch supports actual padding");
    check(pixels[3] == 1 && pixels.front() == 0xdeadbeef && pixels.back() == 0xdeadbeef, "rotation writes intended pixel and preserves guards");
    check(!rowPixel(pixels.data(), 8, 16, 3, 3, 0, 0, 2), "undersized mapping rejected");
    check(!rowPixel(pixels.data(), 64, 8, 3, 3, 0, 0, 2), "short pitch rejected");
    check(!rowPixel(pixels.data(), 64, 16, 3, 3, 3, 0, 2), "logical out-of-range rejected");
    puts("M1_TOUCHBAR_INPUT_MODEL_PASS: real-coordinate boundaries, no ghost/repeated/drag keys, multi-touch cancellation and bounded rotated scanout");
    return 0;
}
