// SPDX-License-Identifier: Apache-2.0
// Hardware diagnostic, not part of vendor: one quiet second through AAudio.
// The operator supplies a Bluetooth output ID observed in AudioPolicy. Refuse
// to write PCM if Android routes the stream to any other output.
#include <aaudio/AAudio.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char** argv) {
    if (argc != 2) { fputs("Required: actual connected Bluetooth output device ID\n", stderr); return 2; }
    char* end = NULL;
    long wanted = strtol(argv[1], &end, 10);
    if (!end || *end || wanted <= 0 || wanted > INT32_MAX) return 2;
    AAudioStreamBuilder* builder = NULL;
    AAudioStream* stream = NULL;
    aaudio_result_t rc = AAudio_createStreamBuilder(&builder);
    if (rc != AAUDIO_OK) return 1;
    AAudioStreamBuilder_setDirection(builder, AAUDIO_DIRECTION_OUTPUT);
    AAudioStreamBuilder_setSharingMode(builder, AAUDIO_SHARING_MODE_SHARED);
    AAudioStreamBuilder_setPerformanceMode(builder, AAUDIO_PERFORMANCE_MODE_NONE);
    AAudioStreamBuilder_setUsage(builder, AAUDIO_USAGE_MEDIA);
    AAudioStreamBuilder_setContentType(builder, AAUDIO_CONTENT_TYPE_MUSIC);
    AAudioStreamBuilder_setFormat(builder, AAUDIO_FORMAT_PCM_I16);
    AAudioStreamBuilder_setChannelCount(builder, 2);
    AAudioStreamBuilder_setSampleRate(builder, 48000);
    AAudioStreamBuilder_setDeviceId(builder, (int32_t)wanted);
    rc = AAudioStreamBuilder_openStream(builder, &stream);
    AAudioStreamBuilder_delete(builder);
    if (rc != AAUDIO_OK) { fprintf(stderr, "AAudio open: %s\n", AAudio_convertResultToText(rc)); return 1; }
    int result = 1;
    if (AAudioStream_getDeviceId(stream) != wanted ||
        AAudioStream_getChannelCount(stream) != 2 ||
        AAudioStream_getFormat(stream) != AAUDIO_FORMAT_PCM_I16) goto close;
    rc = AAudioStream_requestStart(stream);
    if (rc != AAUDIO_OK) goto close;
    if (AAudioStream_getDeviceId(stream) != wanted) goto stop;
    int rate = AAudioStream_getSampleRate(stream);
    if (rate < 8000 || rate > 192000) goto stop;
    int16_t samples[960];
    int written = 0;
    while (written < rate) {
        int frames = rate - written;
        if (frames > 480) frames = 480;
        for (int i = 0; i < frames; ++i) {
            int16_t value = (int16_t)(655.0 * sin(6.283185307179586 * 440.0 * (written+i) / rate));
            samples[2*i] = samples[2*i+1] = value;
        }
        if (AAudioStream_getDeviceId(stream) != wanted) goto stop;
        int n = AAudioStream_write(stream, samples, frames, 1000000000LL);
        if (n <= 0) { fprintf(stderr, "AAudio write: %d\n", n); goto stop; }
        written += n;
    }
    printf("GOS_BT_AAUDIO_PCM_ACCEPTED device=%ld rate=%d frames=%d channels=2\n", wanted, rate, written);
    // Acceptance by Android is not proof that the headphones reproduced it.
    result = 0;
stop:
    AAudioStream_requestStop(stream);
close:
    AAudioStream_close(stream);
    return result;
}
