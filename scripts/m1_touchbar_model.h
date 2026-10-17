// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace googlebook {
enum class RowAction { Key, KeyboardDown, KeyboardUp, ToggleFn };
struct RowKey { const char* label; int code; RowAction action; };
struct RowEvent { RowKey key; bool down; };
struct TouchSlot { int tracking = -1, x = 0, y = 0, held = -1; bool validX = false, validY = false; };
class TouchRow {
public:
    static constexpr int cells = 13;
    static constexpr int slots = 256;
    bool functionKeys = false;
    int activeSlot = 0;
    std::array<TouchSlot, slots> touches{};
    std::vector<RowEvent> pending;
    int minX = 0, maxX = 0, minY = 0, maxY = 0;
    bool configure(int x0, int x1, int y0, int y1);
    int hit(int x, int y) const;
    RowKey key(int cell) const;
    std::vector<RowEvent> report();
    std::vector<RowEvent> cancel();
    void begin(int tracking);
};
// Portrait Summit scanout, clockwise rotation from the horizontal function row.
// Checked coordinates and pitch; actual panel orientation still needs hardware validation.
bool rowPixel(uint32_t* data, size_t bytes, unsigned pitch, unsigned physicalWidth,
              unsigned physicalHeight, int x, int y, uint32_t color);
}
