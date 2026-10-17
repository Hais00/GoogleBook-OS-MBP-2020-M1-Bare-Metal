// SPDX-License-Identifier: Apache-2.0
// CPU fixture only: Binder + FMQ + real snd-aloop PCM, never Apple hardware.
#include <aidl/android/hardware/audio/core/IModule.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>
#include <fmq/AidlMessageQueue.h>
#include <alsa/asoundlib.h>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <thread>
#include <vector>
#include <fcntl.h>
#include <unistd.h>
#include "core-impl/Stream.h"
using namespace aidl::android::hardware::audio::core;
using namespace aidl::android::media::audio::common;
using android::AidlMessageQueue;
static void require(bool v,const char* what){if(!v){fprintf(stderr,"NATIVE_AUDIO_LOCAL_FAIL %s\n",what);std::abort();}}
static void ok(const ndk::ScopedAStatus& s,const char* what){if(!s.isOk()){fprintf(stderr,"%s: %s\n",what,s.getDescription().c_str());std::abort();}}
int main(){
 require(access("/GOS_LOCAL_AUDIO_TEST",F_OK)==0,"test marker");ABinderProcess_setThreadPoolMaxThreadCount(2);ABinderProcess_startThreadPool();
 auto m=IModule::fromBinder(ndk::SpAIBinder(AServiceManager_waitForService("android.hardware.audio.core.IModule/m1_test")));require(bool(m),"remote module");
 int32_t version=0;std::string hash;ok(m->getInterfaceVersion(&version),"version");ok(m->getInterfaceHash(&hash),"hash");require(version==3,"real V3 metadata");printf("NATIVE_AUDIO_REMOTE_VERSION=%d HASH=%s\n",version,hash.c_str());
require(!m->setMasterVolume(0.5f).isOk(),"no fake hardware master volume");require(!m->setMasterMute(true).isOk(),"no fake hardware master mute");
 std::vector<AudioPort> ports;ok(m->getAudioPorts(&ports),"ports");require(ports.size()==2,"2 qualified ports");require(ports[0].ext.get<AudioPortExt::device>().device.address==AudioDeviceAddress::make<AudioDeviceAddress::id>(std::string{}),"canonical built-in address survives legacy roundtrip");int card=snd_card_get_index("Loopback");require(card>=0,"real loopback card discovery");
 AudioPortConfig request;request.portId=2;request.format=ports[1].profiles[0].format;request.sampleRate=Int{.value=48000};request.channelMask=ports[1].profiles[0].channelMasks[0];request.flags=ports[1].flags;AudioPortMixExt mx;mx.handle=123;request.ext=AudioPortExt::make<AudioPortExt::mix>(mx);AudioPortConfig suggested;bool applied=false;
 ok(m->setAudioPortConfig(request,&suggested,&applied),"mix config");require(applied,"mix config applied");
 AudioPatch patch;patch.sourcePortConfigIds={suggested.id};patch.sinkPortConfigIds={1};AudioPatch created;ok(m->setAudioPatch(patch,&created),"physical route");
 IModule::OpenOutputStreamArguments a;a.portConfigId=suggested.id;a.bufferSizeFrames=created.minimumStreamBufferSizeFrames;IModule::OpenOutputStreamReturn opened;ok(m->openOutputStream(a,&opened),"open PCM stream");require(bool(opened.stream),"real stream");
 auto& desc=opened.desc;StreamContext::CommandMQ command(desc.command);StreamContext::ReplyMQ reply(desc.reply);StreamContext::DataMQ data(desc.audio.get<StreamDescriptor::AudioBuffer::fmq>());require(command.isValid()&&reply.isValid()&&data.isValid(),"real FMQs");
 char device[40];snprintf(device,sizeof(device),"hw:%d,1,0",card);snd_pcm_t* capture=nullptr;require(snd_pcm_open(&capture,device,SND_PCM_STREAM_CAPTURE,SND_PCM_NONBLOCK)==0,"ALSA loopback capture open");require(snd_pcm_set_params(capture,SND_PCM_FORMAT_S32_LE,SND_PCM_ACCESS_RW_INTERLEAVED,4,48000,0,100000)==0,"ALSA capture exact params");require(snd_pcm_start(capture)==0,"capture start");
 std::vector<int32_t> captured;std::atomic<bool> stop{false};int captureError=0;
 std::thread reader([&]{int32_t b[480*4];while(!stop){auto n=snd_pcm_readi(capture,b,480);if(n>0)captured.insert(captured.end(),b,b+n*4);else if(n==-EAGAIN||n==-EINTR||n==0){snd_pcm_wait(capture,20);}else if(n==-EPIPE){if(snd_pcm_prepare(capture)<0||snd_pcm_start(capture)<0){captureError=int(n);break;}}else{captureError=int(n);break;}}});
 auto send=[&](const StreamDescriptor::Command& c){require(command.writeBlocking(&c,1,2000000000LL),"FMQ command");StreamDescriptor::Reply r;require(reply.readBlocking(&r,1,3000000000LL),"FMQ reply");if(r.status!=0)fprintf(stderr,"COMMAND_FAILURE tag=%d status=%d state=%d\n",int(c.getTag()),r.status,int(r.state));require(r.status==0,"real command status");return r;};
 send(StreamDescriptor::Command::make<StreamDescriptor::Command::start>(Void{}));
 constexpr int count=40;for(int block=0;block<count;block++){int16_t samples[480*2];for(int n=0;n<480;n++){int i=block*480+n;samples[n*2]=1024+(i%127);samples[n*2+1]=-512-(i%93);}require(data.write(reinterpret_cast<int8_t*>(samples),sizeof(samples)),"PCM queue bytes");auto r=send(StreamDescriptor::Command::make<StreamDescriptor::Command::burst>(sizeof(samples)));require(r.fmqByteCount==sizeof(samples),"all client samples accepted");}
 // Real timer starvation reproduces the hardware failure after a short sound:
 // an empty framework burst must not poison the stream, and fresh PCM must run.
 auto beforeGap=send(StreamDescriptor::Command::make<StreamDescriptor::Command::getStatus>(Void{}));
 std::this_thread::sleep_for(std::chrono::milliseconds(220));
 send(StreamDescriptor::Command::make<StreamDescriptor::Command::burst>(0));
 for(int block=0;block<10;block++){
  int16_t samples[480*2];for(int n=0;n<480;n++){samples[2*n]=700+(n%127);samples[2*n+1]=-900-(n%93);}
  require(data.write(reinterpret_cast<int8_t*>(samples),sizeof(samples)),"PCM after real starvation");
  auto r=send(StreamDescriptor::Command::make<StreamDescriptor::Command::burst>(sizeof(samples)));
  require(r.fmqByteCount==sizeof(samples),"fresh frames accepted after XRUN");
 }
 send(StreamDescriptor::Command::make<StreamDescriptor::Command::pause>(Void{}));
 auto paused=send(StreamDescriptor::Command::make<StreamDescriptor::Command::getStatus>(Void{}));
 std::this_thread::sleep_for(std::chrono::milliseconds(100));
 int16_t pausedSamples[480*2];for(int n=0;n<480;n++){pausedSamples[2*n]=300;pausedSamples[2*n+1]=-200;}
 require(data.write(reinterpret_cast<int8_t*>(pausedSamples),sizeof(pausedSamples)),"queue during pause");
 auto pausedBurst=send(StreamDescriptor::Command::make<StreamDescriptor::Command::burst>(sizeof(pausedSamples)));
 require(pausedBurst.fmqByteCount>=0&&pausedBurst.fmqByteCount<=sizeof(pausedSamples)&&pausedBurst.observable.frames==paused.observable.frames,"bounded paused queue without rendering");
 send(StreamDescriptor::Command::make<StreamDescriptor::Command::start>(Void{}));
 if(pausedBurst.fmqByteCount<sizeof(pausedSamples)){
  size_t left=sizeof(pausedSamples)-pausedBurst.fmqByteCount;
  require(data.write(reinterpret_cast<int8_t*>(pausedSamples)+pausedBurst.fmqByteCount,left),"paused backpressure resumed");
  auto r=send(StreamDescriptor::Command::make<StreamDescriptor::Command::burst>(left));require(r.fmqByteCount==left,"remaining paused samples accepted after resume");
 }
 auto drained=send(StreamDescriptor::Command::make<StreamDescriptor::Command::drain>(StreamDescriptor::DrainMode::DRAIN_ALL));
 auto status=send(StreamDescriptor::Command::make<StreamDescriptor::Command::getStatus>(Void{}));require(status.observable.frames>=beforeGap.observable.frames+10*480&&status.observable.frames<=(count+11)*480,"actual ALSA presentation advances after starvation and drain");
 send(StreamDescriptor::Command::make<StreamDescriptor::Command::standby>(Void{}));
 std::this_thread::sleep_for(std::chrono::milliseconds(120));
 send(StreamDescriptor::Command::make<StreamDescriptor::Command::start>(Void{}));
 int16_t restart[480*2];for(int n=0;n<480;n++){restart[2*n]=400;restart[2*n+1]=-600;}
 for(int n=0;n<8;n++){
  require(data.write(reinterpret_cast<int8_t*>(restart),sizeof(restart)),"PCM after standby");
  auto r=send(StreamDescriptor::Command::make<StreamDescriptor::Command::burst>(sizeof(restart)));
  require(r.fmqByteCount==sizeof(restart),"restart accepts frames");
 }
 send(StreamDescriptor::Command::make<StreamDescriptor::Command::drain>(StreamDescriptor::DrainMode::DRAIN_ALL));
 auto restarted=send(StreamDescriptor::Command::make<StreamDescriptor::Command::getStatus>(Void{}));
 require(restarted.observable.frames>=status.observable.frames+8*480,"presentation preserved over standby/reopen");
 // Exercise Android's actual standby sequence: pause -> flush -> standby,
 // including a prepared PCM after a completed drain (MCA has no hw pause).
 require(data.write(reinterpret_cast<int8_t*>(restart),sizeof(restart)),"last PCM before framework standby");
 send(StreamDescriptor::Command::make<StreamDescriptor::Command::burst>(sizeof(restart)));
 send(StreamDescriptor::Command::make<StreamDescriptor::Command::pause>(Void{}));
 send(StreamDescriptor::Command::make<StreamDescriptor::Command::flush>(Void{}));
 send(StreamDescriptor::Command::make<StreamDescriptor::Command::standby>(Void{}));
 std::this_thread::sleep_for(std::chrono::milliseconds(60));stop=true;reader.join();snd_pcm_close(capture);require(captureError==0,"capture no XRUN/error");
 auto expected=[](int16_t s){return int32_t(double(float(s)/32768.f)*0.92*2147483648.0);};size_t matched=0;
 for(size_t f=0;f+128<captured.size()/4;f++){
  size_t n=0;for(;n<128;n++){int32_t l=expected(1024+(n%127)),r=expected(-512-(n%93));auto* v=&captured[(f+n)*4];if(std::abs(int64_t(v[0])-l)>128||std::abs(int64_t(v[1])-r)>128||v[0]!=v[2]||v[1]!=v[3])break;}if(n==128){matched=n;break;}
 }
 require(matched==128,"real loopback samples/channel order match client");
 bool afterGapMatched=false,restartMatched=false;
 for(size_t f=0;f+128<captured.size()/4;f++){
  size_t n=0;for(;n<128;n++){int j=n%480;auto* v=&captured[(f+n)*4];if(std::abs(int64_t(v[0])-expected(700+(j%127)))>128||std::abs(int64_t(v[1])-expected(-900-(j%93)))>128||v[0]!=v[2]||v[1]!=v[3])break;}
  afterGapMatched|=n==128;
  n=0;for(;n<128;n++){auto* v=&captured[(f+n)*4];if(std::abs(int64_t(v[0])-expected(400))>128||std::abs(int64_t(v[1])-expected(-600))>128||v[0]!=v[2]||v[1]!=v[3])break;}restartMatched|=n==128;
 }
 require(afterGapMatched&&restartMatched,"real captured samples after XRUN and reopen");
 int fd=open("/tmp/owner-readonly-dump.txt",O_CREAT|O_TRUNC|O_RDWR,0600);require(fd>=0,"diagnostic dump file");
 require(AIBinder_dump(opened.stream->asBinder().get(),fd,nullptr,0)==STATUS_OK,"actual remote owner dump");
 require(lseek(fd,0,SEEK_SET)==0,"dump rewind");char diagnostic[16384]{};require(read(fd,diagnostic,sizeof(diagnostic)-1)>0,"actual dump content");close(fd);
 auto recovery=strstr(diagnostic,"xrun_recoveries=");require(recovery&&strtol(recovery+16,nullptr,10)>=1&&strstr(diagnostic,"last_error=0"),"actual XRUN recovery with no hidden error");
 printf("NATIVE_AUDIO_OWNER_DIAGNOSTICS %s",diagnostic);
std::shared_ptr<IStreamCommon> common;ok(opened.stream->getStreamCommon(&common),"common");ok(common->close(),"close");ok(m->resetAudioPatch(created.id),"remove route");
 printf("NATIVE_AUDIO_BINDER_FMQ_ALSA_PASS accepted=%d presented=%lld capture_frames=%zu matched=%zu xrun_and_standby_resume=PASS\n",(count+20)*480,(long long)restarted.observable.frames,captured.size()/4,matched);return 0;
}
