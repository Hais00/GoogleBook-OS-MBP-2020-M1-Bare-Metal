// SPDX-License-Identifier: Apache-2.0
// The board's empty audio profile must not initialize a Qualcomm DSP service.
#include <errno.h>
#include <android/log.h>

int registerService(void)
{
    __android_log_print(ANDROID_LOG_WARN, "googlebook-audio",
                        "Qualcomm AGM is absent; using the provided empty audio HAL");
    return -ENODEV;
}
