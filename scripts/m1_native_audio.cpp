// SPDX-License-Identifier: Apache-2.0
// Native M1 primary. Public AOSP V3 protocol/worker; real ALSA PCM owner.
#define LOG_TAG "M1Audio"
#include <android-base/logging.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>
#include <atomic>
#include <cstdio>
#include "core-impl/Module.h"
#include "m1_native_audio_pcm.h"
using namespace aidl::android::hardware::audio::core;
using namespace aidl::android::media::audio::common;
using aidl::android::hardware::audio::common::SourceMetadata;
using aidl::android::hardware::audio::common::SinkMetadata;

namespace {
#ifdef M1_AUDIO_LOCAL_ALSA_TEST
constexpr auto kSinkType=AudioDeviceType::OUT_BUS;
#else
constexpr auto kSinkType=AudioDeviceType::OUT_SPEAKER;
#endif
class Output final:public StreamOut,public StreamCommonImpl {
 std::shared_ptr<m1audio::Playback> mPlayback;
 std::atomic<bool> mSpeaker{false};
 public:
 Output(StreamContext&& c,const SourceMetadata& metadata,const std::optional<AudioOffloadInfo>& offload,std::shared_ptr<m1audio::Playback> playback)
  :StreamOut(std::move(c),offload),StreamCommonImpl(&mContextInstance,metadata),mPlayback(std::move(playback)){}
 ~Output(){cleanupWorker();}
 binder_status_t dump(int fd,const char**,uint32_t) override {
  auto text=mPlayback->diagnostics();dprintf(fd,"%s",text.c_str());return STATUS_OK;
 }
 android::status_t init(DriverCallbackInterface*) override {
  int rc=mPlayback->resetStream();if(rc<0)return rc;
  return getContext().getSampleRate()==48000&&getContext().getFormat().pcm==PcmType::INT_16_BIT&&getContext().getFrameSize()==4?android::OK:android::BAD_VALUE;
 }
 android::status_t start() override {return mSpeaker?mPlayback->start():-ENODEV;}
 android::status_t transfer(void* b,size_t n,size_t* done,int32_t* latency) override {if(!mSpeaker){*done=0;return -ENODEV;}return mPlayback->write(static_cast<int16_t*>(b),n,done,latency);}
 android::status_t drain(StreamDescriptor::DrainMode mode) override {
  if(mode!=StreamDescriptor::DrainMode::DRAIN_ALL)return android::INVALID_OPERATION;
  return mPlayback->drain();
 }
 android::status_t pause() override {return mPlayback->pause();}
 android::status_t flush() override {return mPlayback->flush();}
 android::status_t standby() override {return mPlayback->standby();}
 void shutdown() override {(void)mPlayback->standby();}
 android::status_t refinePosition(StreamDescriptor::Position* p) override {return mPlayback->position(&p->frames,&p->timeNs);}
 ndk::ScopedAStatus setConnectedDevices(const ConnectedDevices& devices) override {
  if(devices.size()>1)return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
  if(!devices.empty()&&devices[0].type.type!=kSinkType)return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
  mSpeaker=!devices.empty();return StreamCommonImpl::setConnectedDevices(devices);
 }
 private:
 void onClose(StreamDescriptor::State) override {defaultOnClose();}
};
std::unique_ptr<Module::Configuration> configuration() {
 auto c=std::make_unique<Module::Configuration>();
 AudioProfile profile;
 profile.format=AudioFormatDescription{.type=AudioFormatType::PCM,.pcm=PcmType::INT_16_BIT};
 profile.sampleRates={48000};profile.channelMasks={AudioChannelLayout::make<AudioChannelLayout::layoutMask>(AudioChannelLayout::LAYOUT_STEREO)};
 AudioPort speaker;speaker.id=1;speaker.name=
#ifdef M1_AUDIO_LOCAL_ALSA_TEST
 "ALSA loopback test sink";
#else
 "M1 J293 speakers";
#endif
speaker.profiles={profile};speaker.flags=AudioIoFlags::make<AudioIoFlags::output>(0);
 AudioPortDeviceExt dev;dev.device.type.type=kSinkType;dev.device.address=AudioDeviceAddress::make<AudioDeviceAddress::id>(std::string{});dev.flags=1<<AudioPortDeviceExt::FLAG_INDEX_DEFAULT_DEVICE;speaker.ext=AudioPortExt::make<AudioPortExt::device>(dev);
 AudioPort mix;mix.id=2;mix.name="M1 primary PCM";mix.profiles={profile};mix.flags=AudioIoFlags::make<AudioIoFlags::output>(1<<int(AudioOutputFlags::PRIMARY));
 AudioPortMixExt mx;mx.maxOpenStreamCount=1;mx.maxActiveStreamCount=1;mix.ext=AudioPortExt::make<AudioPortExt::mix>(mx);
 c->ports={speaker,mix};AudioRoute route;route.sourcePortIds={2};route.sinkPortId=1;route.isExclusive=false;c->routes={route};
 AudioPortConfig sp;sp.id=1;sp.portId=1;sp.sampleRate=Int{.value=48000};sp.channelMask=profile.channelMasks[0];sp.format=profile.format;sp.flags=speaker.flags;sp.ext=speaker.ext;
 c->portConfigs={sp};c->initialConfigs=c->portConfigs;c->nextPortId=3;return c;
}
class Primary final:public Module {
 std::shared_ptr<m1audio::Playback> mPlayback;
 public:
 explicit Primary(std::shared_ptr<m1audio::Playback> p):Module(Module::DEFAULT,configuration()),mPlayback(std::move(p)){}
 binder_status_t dump(int fd,const char** args,uint32_t count) override {
  auto text=mPlayback->diagnostics();dprintf(fd,"%s",text.c_str());return Module::dump(fd,args,count);
 }
 protected:
 ndk::ScopedAStatus createInputStream(StreamContext&&,const SinkMetadata&,const std::vector<MicrophoneInfo>&,std::shared_ptr<StreamIn>*) override {return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);}
 ndk::ScopedAStatus createOutputStream(StreamContext&& c,const SourceMetadata& m,const std::optional<AudioOffloadInfo>& o,std::shared_ptr<StreamOut>* result) override {
  if(c.isMmap()||c.getAsyncCallback()||o)return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
  return createStreamInstance<Output>(result,std::move(c),m,o,mPlayback);
 }
 ndk::ScopedAStatus setModuleDebug(const ModuleDebug&) override {return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);}
 // AudioFlinger must apply master mute/volume in its software mixer. The
 // playback device has no independently-owned master gain or mute control.
 ndk::ScopedAStatus onMasterMuteChanged(bool) override {return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);}
 ndk::ScopedAStatus onMasterVolumeChanged(float) override {return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);}
 int32_t getNominalLatencyMs(const AudioPortConfig&) override {return 40;}
};
}
int main(int argc,char** argv) {
 android::base::SetMinimumLogSeverity(android::base::INFO);
 auto p=std::make_shared<m1audio::Playback>();int rc=p->discover();if(rc<0){LOG(ERROR)<<"ALSA owner qualification failed: "<<rc<<" "<<snd_strerror(rc);return 1;}
 if(argc==2&&!strcmp(argv[1],"--inspect")){printf("M1_AUDIO_REAL_ALSA_QUALIFIED card=%d rate=48000 channels=4 format=S32_LE no_PCM_started\n",p->card());return 0;}
 if(argc!=1)return 2;
 ABinderProcess_setThreadPoolMaxThreadCount(4);ABinderProcess_startThreadPool();
 auto module=ndk::SharedRefBase::make<Primary>(p);
#ifdef M1_AUDIO_LOCAL_ALSA_TEST
 const char* name="android.hardware.audio.core.IModule/m1_test";
#else
 const char* name="android.hardware.audio.core.IModule/m1";
#endif
 rc=AServiceManager_addService(module->asBinder().get(),name);if(rc){LOG(ERROR)<<"Registration failed: "<<rc;return 1;}
 LOG(INFO)<<"Native primary registered "<<name<<", real ALSA card="<<p->card()<<", 48kHz stereo -> 4 protected speaker channels";
 ABinderProcess_joinThreadPool();return 1;
}
