// SPDX-License-Identifier: Apache-2.0
// CPU callback/filesystem fixtures, never a hardware lighting qualification.
#include "m1_lights_service.h"
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

using namespace aidl::android::hardware::light;
static void check(bool value, const char* message) {
    if (!value) { fprintf(stderr, "M1_LIGHTS_TEST_FAIL %s\n", message); exit(1); }
}
static void file(const std::string& name, const std::string& value) {
    for (size_t i = 1; i < name.size(); ++i)
        if (name[i] == '/') mkdir(name.substr(0, i).c_str(), 0700);
    FILE* out = fopen(name.c_str(), "wb"); check(out, "fixture open");
    check(fwrite(value.data(), 1, value.size(), out) == value.size(), "fixture write"); fclose(out);
}
static std::string content(const std::string& name) {
    FILE* in = fopen(name.c_str(), "rb"); check(in, "read fixture");
    char text[128]{}; size_t n = fread(text, 1, sizeof(text), in); fclose(in);
    return std::string(text, n);
}
int main() {
    const char* temporary = getenv("TMPDIR");
    std::string pattern = std::string(temporary ? temporary : "/tmp")+"/gos-lights-XXXXXX";
    char* created = mkdtemp(pattern.data()); check(created, "private fixture root");
    std::string root = created;
    std::string panel = root+"/class/backlight/apple-panel-bl";
    std::string keyboard = root+"/class/leds/kbd_backlight";
    std::string bar = root+"/class/backlight/dsi-test";
    file(panel+"/max_brightness", "100\n"); file(panel+"/brightness", "50\n");
    file(keyboard+"/max_brightness", "255\n"); file(keyboard+"/brightness", "0\n");
    file(bar+"/max_brightness", "255\n"); file(bar+"/brightness", "17\n");
    mkdir((bar+"/device").c_str(), 0700);
    check(symlink("/sys/bus/mipi-dsi/drivers/panel-summit", (bar+"/device/driver").c_str()) == 0, "fixture kernel driver binding");
    googlebook::M1Lights strict(root);
    std::vector<googlebook::M1Light> raw;
    check(strict.enumerate(&raw) == -ENODEV && raw.empty(), "production rejects ordinary filesystem");
    auto owner = std::make_shared<googlebook::M1Lights>(root, true);
    auto service = ndk::SharedRefBase::make<googlebook::M1LightsService>(owner);
    std::vector<HwLight> lights;
    check(service->getLights(&lights).isOk() && lights.size() == 3, "three real fixture controllers");
    for (int i = 0; i < 3; ++i)
        check(lights[i].id == i && static_cast<int>(lights[i].type) == i, "stable roles preserve main panel");
    HwLightState state;
    state.color = -1;
    check(service->setLightState(0, state).isOk(), "panel full scale callback");
    check(content(panel+"/brightness") == "100\n", "panel uses its actual maximum");
    state.color = static_cast<int32_t>(0xff808080u);
    check(service->setLightState(1, state).isOk(), "keyboard level callback");
    check(content(keyboard+"/brightness") == "128\n", "keyboard requested level");
    state.color = 0;
    check(service->setLightState(2, state).isOk() && content(bar+"/brightness") == "0\n", "touchbar off");
    state.flashMode = FlashMode::TIMED;
    check(!service->setLightState(1, state).isOk(), "unsupported flash rejected");
    check(content(keyboard+"/brightness") == "128\n", "rejected mode cannot alter keyboard");
    state.flashMode = FlashMode::NONE;
    check(!service->setLightState(99, state).isOk(), "invalid light ID rejected");
    file(keyboard+"/max_brightness", "unreadable-value\n");
    check(service->getLights(&lights).isOk() && lights.size() == 2, "bad keyboard cannot remove other lights");
    check(!service->setLightState(1, state).isOk(), "unqualified keyboard never acknowledged");
    check(service->setLightState(0, state).isOk() && content(panel+"/brightness") == "0\n", "main display independent of keyboard failure");
    std::map<int, int> issues;
    check(owner->enumerate(&raw, &issues) == 0 && issues.count(1), "keyboard failure remains observable");
    file(keyboard+"/max_brightness", "255\n");
    check(unlink((bar+"/device/driver").c_str()) == 0, "replace fixture driver");
    check(symlink("/sys/bus/mipi-dsi/drivers/other-panel-summit", (bar+"/device/driver").c_str()) == 0, "unrelated kernel owner fixture");
    check(owner->enumerate(&raw, &issues) == 0 && raw.size() == 2 && issues[2] == -ENOENT,
          "only the exact bound panel-summit driver qualifies");
    check(unlink((bar+"/device/driver").c_str()) == 0 && symlink("/sys/bus/mipi-dsi/drivers/panel-summit", (bar+"/device/driver").c_str()) == 0, "restore qualified driver");
    std::string other = root+"/class/backlight/second-dsi";
    file(other+"/max_brightness", "255\n"); file(other+"/brightness", "1\n");
    mkdir((other+"/device").c_str(), 0700);
    check(symlink("/sys/bus/mipi-dsi/drivers/panel-summit", (other+"/device/driver").c_str()) == 0, "second driver binding fixture");
    check(owner->enumerate(&raw, &issues) == 0 && raw.size() == 2 && issues[2] == -EEXIST,
          "ambiguous touchbar owner is not selected");
    check(!service->setLightState(2, state).isOk(), "ambiguous touchbar cannot be written");
    puts("M1_LIGHTS_BIONIC_CALLBACK_FIXTURES_PASS: filesystem guard, exact controllers, real readback, independent failure and ambiguity");
    return 0;
}
