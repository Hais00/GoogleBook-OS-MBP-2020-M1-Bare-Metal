// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <alsa/asoundlib.h>
#include <array>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace m1audio {
// Owns only routing and the playback PCM. The separate Asahi daemon owns all
// gain/V-I/unlock controls; this class never writes an unlock or amp gain.
class Playback {
 public:
  Playback();
  ~Playback();
  int discover();
  int resetStream();
  int start();
  int write(const int16_t* stereo, size_t frames, size_t* accepted, int32_t* latencyMs);
  int drain();
  int pause();
  int flush();
  int standby();
  int position(int64_t* presented, int64_t* timeNs);
  int card() const { return mCard; }
  std::string diagnostics();
 private:
  int element(const char* name, snd_ctl_elem_info_t* info);
  int readInteger(const char* name, long* value);
  int setBoolean(const char* name, bool value);
  int setEnum(const char* name, const char* value);
  int writeFrames(const int32_t* buffer, size_t frames, size_t* accepted);
  std::string diagnosticsLocked();
  int openPcm();
  int recoverXrun();
  int protectionReady();
  int closePcm();
  int loadFilters();
  void convert(const int16_t* stereo, size_t frames, int32_t* four);
  snd_ctl_t* mCtl = nullptr;
  snd_pcm_t* mPcm = nullptr;
  int mCard = -1;
  int64_t mWritten = 0, mBootstrap = 0, mBasePresented = 0, mPresented = 0;
  bool mPaused = false;
  size_t mBufferFrames = 0, mPendingBootstrap = 0;
  std::vector<int32_t> mHistory, mPending;
  uint64_t mXruns = 0;
  int64_t mLastWriteNs = 0;
  int mLastError = 0;
  double mInputPeak = 0, mOutputPeak = 0;
  std::vector<float> mFront, mRear, mLeft, mRight;
  size_t mHead = 0, mTaps = 0;
  std::mutex mLock;
};
}
