// SPDX-License-Identifier: Apache-2.0
#include "m1_native_audio_pcm.h"
#include <algorithm>
#include <android-base/logging.h>
#include <arm_neon.h>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <limits>
#include <sstream>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

namespace m1audio {
namespace {
int64_t nowNs() { timespec t{}; clock_gettime(CLOCK_MONOTONIC, &t); return int64_t(t.tv_sec)*1000000000+t.tv_nsec; }
uint32_t u32(const uint8_t* p) { return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24; }
int readFilter(const char* path, std::vector<float>* output) {
 std::ifstream file(path,std::ios::binary); if(!file) return -ENOENT;
 std::vector<uint8_t> b((std::istreambuf_iterator<char>(file)),{});
 if(b.size()<44 || b.size()>1024*1024 || memcmp(b.data(),"RIFF",4) || memcmp(b.data()+8,"WAVE",4)) return -EINVAL;
 bool fmt=false;
 for(size_t o=12;o+8<=b.size();) {
  uint32_t n=u32(b.data()+o+4); if(n>b.size()-o-8) return -EINVAL;
  const auto* d=b.data()+o+8;
  if(!memcmp(b.data()+o,"fmt ",4)) {
   if(n<16 || d[0]!=3 || d[1]!=0 || d[2]!=1 || d[3]!=0 || u32(d+4)!=48000 || d[14]!=32 || d[15]!=0) return -EINVAL;
   fmt=true;
  } else if(!memcmp(b.data()+o,"data",4)) {
   if(!fmt || n%4 || !n || n/4>8192) return -EINVAL;
   output->resize(n/4);
   for(size_t i=0;i<n/4;i++){uint32_t raw=u32(d+4*i);float f;memcpy(&f,&raw,4);if(!std::isfinite(f)||std::abs(f)>32)return -EINVAL;(*output)[i]=f;}
   return 0;
  }
  o+=8+n+(n&1);
 }
 return -EINVAL;
}
}
Playback::Playback()=default;
Playback::~Playback(){standby();if(mCtl)snd_ctl_close(mCtl);}
int Playback::element(const char* name,snd_ctl_elem_info_t* info) {
 snd_ctl_elem_info_clear(info);snd_ctl_elem_info_set_interface(info,SND_CTL_ELEM_IFACE_MIXER);snd_ctl_elem_info_set_name(info,name);
 return snd_ctl_elem_info(mCtl,info);
}
int Playback::readInteger(const char* name,long* v) {
 snd_ctl_elem_info_t* i; snd_ctl_elem_info_alloca(&i);int rc=element(name,i);if(rc<0)return rc;
 auto type=snd_ctl_elem_info_get_type(i);if(type!=SND_CTL_ELEM_TYPE_INTEGER&&type!=SND_CTL_ELEM_TYPE_BOOLEAN)return -EINVAL;
 snd_ctl_elem_value_t* value;snd_ctl_elem_value_alloca(&value);snd_ctl_elem_value_set_numid(value,snd_ctl_elem_info_get_numid(i));
 rc=snd_ctl_elem_read(mCtl,value);if(rc<0)return rc;*v=snd_ctl_elem_value_get_integer(value,0);return 0;
}
int Playback::setBoolean(const char* name,bool v) {
 snd_ctl_elem_info_t* i;snd_ctl_elem_info_alloca(&i);int rc=element(name,i);if(rc<0)return rc;
 if(snd_ctl_elem_info_get_type(i)!=SND_CTL_ELEM_TYPE_BOOLEAN||snd_ctl_elem_info_get_count(i)!=1)return -EINVAL;
 snd_ctl_elem_value_t* val;snd_ctl_elem_value_alloca(&val);snd_ctl_elem_value_set_numid(val,snd_ctl_elem_info_get_numid(i));snd_ctl_elem_value_set_boolean(val,0,v);
 rc=snd_ctl_elem_write(mCtl,val);if(rc<0)return rc;long actual;rc=readInteger(name,&actual);return rc<0?rc:actual==v?0:-EIO;
}
int Playback::setEnum(const char* name,const char* choice) {
 snd_ctl_elem_info_t* i;snd_ctl_elem_info_alloca(&i);int rc=element(name,i);if(rc<0)return rc;
 if(snd_ctl_elem_info_get_type(i)!=SND_CTL_ELEM_TYPE_ENUMERATED)return -EINVAL;
 unsigned n=snd_ctl_elem_info_get_items(i);if(n>128)return -EOVERFLOW;
 for(unsigned x=0;x<n;x++) {
  snd_ctl_elem_info_set_item(i,x);if((rc=snd_ctl_elem_info(mCtl,i))<0)return rc;
  if(strcmp(choice,snd_ctl_elem_info_get_item_name(i)))continue;
  snd_ctl_elem_value_t* val;snd_ctl_elem_value_alloca(&val);snd_ctl_elem_value_set_numid(val,snd_ctl_elem_info_get_numid(i));snd_ctl_elem_value_set_enumerated(val,0,x);
  if((rc=snd_ctl_elem_write(mCtl,val))<0)return rc;
  if((rc=snd_ctl_elem_read(mCtl,val))<0)return rc;
  return snd_ctl_elem_value_get_enumerated(val,0)==x?0:-EIO;
 }
 return -ENOENT;
}
int Playback::loadFilters() {
#ifdef M1_AUDIO_LOCAL_ALSA_TEST
 mFront={1};mRear={1};
#else
 int rc=readFilter("/vendor/etc/m1-audio/j293/front-48.wav",&mFront);if(rc<0)return rc;
 rc=readFilter("/vendor/etc/m1-audio/j293/rear-48.wav",&mRear);if(rc<0)return rc;
#endif
 mTaps=std::max(mFront.size(),mRear.size());mFront.resize(mTaps);mRear.resize(mTaps);mLeft.assign(mTaps*2,0);mRight.assign(mTaps*2,0);return 0;
}
int Playback::discover() {
 std::lock_guard lock(mLock);if(mCtl)return -EALREADY;
#ifdef M1_AUDIO_LOCAL_ALSA_TEST
 if(access("/GOS_LOCAL_AUDIO_TEST",F_OK))return -EPERM;
 const char* expected="Loopback";const char* driver="Loopback";
#else
 const char* expected="AppleJ293";const char* driver="macaudio";
#endif
 for(int c=0;c<32;c++) {
  char hw[32];snprintf(hw,sizeof(hw),"hw:%d",c);snd_ctl_t* ctl=nullptr;
  if(snd_ctl_open(&ctl,hw,SND_CTL_NONBLOCK)<0)continue;
  snd_ctl_card_info_t* ci;snd_ctl_card_info_alloca(&ci);int rc=snd_ctl_card_info(ctl,ci);
  bool match=rc==0&&!strcmp(snd_ctl_card_info_get_id(ci),expected)&&!strcmp(snd_ctl_card_info_get_driver(ci),driver);
  if(!match){snd_ctl_close(ctl);continue;}mCard=c;mCtl=ctl;break;
 }
 if(!mCtl)return -ENODEV;
 int rc=loadFilters();if(rc<0)return rc;
#ifndef M1_AUDIO_LOCAL_ALSA_TEST
 // BSD Asahi UCM J293: Secondary PCM1, four speakers. No unlock/gain writes.
 if((rc=setEnum("Speaker Playback Mux","Secondary"))<0)return rc;
 if((rc=setBoolean("Speaker Switch",true))<0)return rc;
 long unlocked;if((rc=readInteger("Speaker Volume Unlock",&unlocked))<0)return rc;
#endif
 // Refine only: no samples, no DMA start, no amp protection bypass.
 char path[48];snprintf(path,sizeof(path),"hw:%d,%d",mCard,
#ifdef M1_AUDIO_LOCAL_ALSA_TEST
 0
#else
 1
#endif
 );snd_pcm_t* pcm=nullptr;if((rc=snd_pcm_open(&pcm,path,SND_PCM_STREAM_PLAYBACK,SND_PCM_NONBLOCK))<0)return rc;
 snd_pcm_hw_params_t* hw;snd_pcm_hw_params_alloca(&hw);
 rc=snd_pcm_hw_params_any(pcm,hw);
 if(rc>=0)rc=snd_pcm_hw_params_test_format(pcm,hw,SND_PCM_FORMAT_S32_LE);
 if(rc>=0)rc=snd_pcm_hw_params_test_channels(pcm,hw,4);
 if(rc>=0)rc=snd_pcm_hw_params_test_rate(pcm,hw,48000,0);
 snd_pcm_close(pcm);return rc;
}
int Playback::openPcm() {
 if(mPcm)return 0;char path[48];snprintf(path,sizeof(path),"hw:%d,%d",mCard,
#ifdef M1_AUDIO_LOCAL_ALSA_TEST
 0
#else
 1
#endif
 );int rc=snd_pcm_open(&mPcm,path,SND_PCM_STREAM_PLAYBACK,SND_PCM_NONBLOCK);if(rc<0){mPcm=nullptr;return rc;}
 rc=snd_pcm_set_params(mPcm,SND_PCM_FORMAT_S32_LE,SND_PCM_ACCESS_RW_INTERLEAVED,4,48000,0,40000);
 if(rc<0){closePcm();return rc;}
 snd_pcm_hw_params_t* hw;snd_pcm_hw_params_alloca(&hw);unsigned rate=0,channels=0; snd_pcm_format_t fmt;
 if((rc=snd_pcm_hw_params_current(mPcm,hw))<0||(rc=snd_pcm_hw_params_get_rate(hw,&rate,nullptr))<0||(rc=snd_pcm_hw_params_get_channels(hw,&channels))<0||(rc=snd_pcm_hw_params_get_format(hw,&fmt))<0){closePcm();return rc;}
 if(rate!=48000||channels!=4||fmt!=SND_PCM_FORMAT_S32_LE){closePcm();return -EINVAL;}
 snd_pcm_uframes_t buffer=0;if((rc=snd_pcm_hw_params_get_buffer_size(hw,&buffer))<0||buffer==0||buffer>48000){closePcm();return rc<0?rc:-EINVAL;}
 mBufferFrames=buffer;mHistory.clear();mHistory.reserve(buffer*4+480*4);mPending.clear();mPendingBootstrap=0;
 mPaused=false;return 0;
}
int Playback::recoverXrun() {
 // Only recover an actual kernel underrun. Do not hide disconnect, ownership,
 // protection, or other I/O failures. Keep the last observed presentation;
 // unobserved frames from the old ALSA timeline are not declared played.
 if(!mPcm||snd_pcm_state(mPcm)!=SND_PCM_STATE_XRUN)return -EBADFD;
 mBasePresented=mPresented;mWritten=mBootstrap=0;mHistory.clear();
 int rc=snd_pcm_prepare(mPcm);if(rc<0){mLastError=rc;return rc;}
 ++mXruns;LOG(WARNING)<<"M1 PCM recovered real XRUN count="<<mXruns;return 0;
}
int Playback::writeFrames(const int32_t* buffer,size_t frames,size_t* accepted) {
 *accepted=0;const int64_t deadline=nowNs()+2000000000;unsigned recoveries=0;
 while(*accepted<frames) {
  auto n=snd_pcm_writei(mPcm,buffer+*accepted*4,frames-*accepted);
  if(n>0){
   mHistory.insert(mHistory.end(),buffer+*accepted*4,buffer+(*accepted+n)*4);
   if(mHistory.size()>mBufferFrames*4)mHistory.erase(mHistory.begin(),mHistory.end()-mBufferFrames*4);
   *accepted+=n;mWritten+=n;mLastWriteNs=nowNs();continue;
  }
  if(n==-EINTR)continue;
  if(n==-EPIPE&&recoveries++<3&&nowNs()<deadline) {
   int rc=recoverXrun();if(rc<0)return mLastError=rc;
#ifndef M1_AUDIO_LOCAL_ALSA_TEST
   // Revalidate protection after restarting the hardware PCM clock. The HAL
   // never unlocks a speaker, writes a gain, or resumes unprotected samples.
   long unlocked=0;if((rc=readInteger("Speaker Volume Unlock",&unlocked))<0||unlocked!=1)return mLastError=rc<0?rc:-EACCES;
#endif
   continue;
  }
  if(n!=-EAGAIN&&n!=0)return mLastError=n<0?int(n):-EIO;
  if(nowNs()>=deadline)return mLastError=-ETIMEDOUT;
  int rc=snd_pcm_wait(mPcm,100);
  if(rc==-EPIPE)continue; // writei observes and qualifies the XRUN next iteration.
  if(rc<0&&rc!=-EINTR)return mLastError=rc;
 }
 return 0;
}
int Playback::protectionReady() {
#ifndef M1_AUDIO_LOCAL_ALSA_TEST
 // Start the actual V/I clock with zeros while the independent owner warms up.
 long unlocked=0;int rc=0;const auto until=nowNs()+1500000000;std::array<int32_t,480*4> zero{};
 while((rc=readInteger("Speaker Volume Unlock",&unlocked))==0&&unlocked!=1) {
  if(nowNs()>until)return -EACCES;
  size_t written=0;rc=writeFrames(zero.data(),480,&written);mBootstrap+=written;if(rc<0)return rc;
 }
 return rc;
#else
 return 0;
#endif
}
int Playback::resetStream() {std::lock_guard lock(mLock);if(mPcm)return -EBUSY;mWritten=mBootstrap=mBasePresented=mPresented=0;mXruns=0;mLastError=0;mInputPeak=mOutputPeak=0;mHead=0;std::fill(mLeft.begin(),mLeft.end(),0);std::fill(mRight.begin(),mRight.end(),0);return 0;}
int Playback::start() {
 std::lock_guard lock(mLock);if(mCard<0)return -ENODEV;int rc=openPcm();if(rc<0)return rc;
 if(mPaused){
  if((rc=snd_pcm_prepare(mPcm))<0)return mLastError=rc;
  if((rc=protectionReady())<0){closePcm();return mLastError=rc;}
  auto pending=std::move(mPending);size_t bootstrap=mPendingBootstrap;mPending.clear();mPendingBootstrap=0;
  size_t written=0;rc=writeFrames(pending.data(),pending.size()/4,&written);mBootstrap+=std::min(bootstrap,written);
  if(rc<0){closePcm();return mLastError=rc;}mPaused=false;
  return 0;
 }
 if(snd_pcm_state(mPcm)==SND_PCM_STATE_SETUP)if((rc=snd_pcm_prepare(mPcm))<0)return rc;
 if(snd_pcm_state(mPcm)==SND_PCM_STATE_XRUN)if((rc=recoverXrun())<0)return rc;
 if((rc=protectionReady())<0){closePcm();return mLastError=rc;}
 for(std::istringstream lines(diagnosticsLocked());;){std::string line;if(!std::getline(lines,line))break;LOG(INFO)<<line;}
 return 0;
}
void Playback::convert(const int16_t* input,size_t frames,int32_t* output) {
 for(size_t frame=0;frame<frames;frame++) {
  mInputPeak=std::max({mInputPeak,std::abs(double(input[2*frame])/32768.0),std::abs(double(input[2*frame+1])/32768.0)});
  mHead=(mHead+mTaps-1)%mTaps;mLeft[mHead]=mLeft[mHead+mTaps]=input[2*frame]/32768.f;mRight[mHead]=mRight[mHead+mTaps]=input[2*frame+1]/32768.f;
  float32x4_t fl=vdupq_n_f32(0),fr=fl,rl=fl,rr=fl;size_t k=0;
  for(;k+4<=mTaps;k+=4){auto l=vld1q_f32(mLeft.data()+mHead+k),r=vld1q_f32(mRight.data()+mHead+k),f=vld1q_f32(mFront.data()+k),b=vld1q_f32(mRear.data()+k);fl=vfmaq_f32(fl,l,f);fr=vfmaq_f32(fr,r,f);rl=vfmaq_f32(rl,l,b);rr=vfmaq_f32(rr,r,b);}
  float v[4]={vaddvq_f32(fl),vaddvq_f32(fr),vaddvq_f32(rl),vaddvq_f32(rr)};
  for(;k<mTaps;k++){v[0]+=mLeft[mHead+k]*mFront[k];v[1]+=mRight[mHead+k]*mFront[k];v[2]+=mLeft[mHead+k]*mRear[k];v[3]+=mRight[mHead+k]*mRear[k];}
  for(int c=0;c<4;c++){double x=std::clamp(double(v[c])*0.92,-0.125,0.125);mOutputPeak=std::max(mOutputPeak,std::abs(x));output[frame*4+c]=int32_t(std::clamp(x*2147483648.0,-2147483648.0,2147483647.0));}
 }
}
int Playback::write(const int16_t* stereo,size_t frames,size_t* accepted,int32_t* latency) {
 std::lock_guard lock(mLock);*accepted=0;*latency=0;if(!mPcm)return -EBADFD;
 if(mPaused){
  size_t n=std::min(frames,mBufferFrames-mPending.size()/4);size_t old=mPending.size();mPending.resize(old+n*4);
  if(n)convert(stereo,n,mPending.data()+old);*accepted=n;*latency=int32_t(mPending.size()/4*1000/48000);return 0;
 }
 int state=snd_pcm_state(mPcm);int ready=0;
 if(state==SND_PCM_STATE_XRUN)ready=recoverXrun();
 else if(state==SND_PCM_STATE_SETUP)ready=snd_pcm_prepare(mPcm);
 if(ready<0)return mLastError=ready;
 if((ready=protectionReady())<0){closePcm();return mLastError=ready;}
 std::array<int32_t,480*4> samples{};
 while(*accepted<frames){size_t n=std::min<size_t>(480,frames-*accepted);convert(stereo+*accepted*2,n,samples.data());size_t wrote=0;int rc=writeFrames(samples.data(),n,&wrote);*accepted+=wrote;if(rc<0)return rc;}
 snd_pcm_sframes_t delay=0;int rc=snd_pcm_delay(mPcm,&delay);if(rc==-EPIPE){rc=recoverXrun();delay=0;}if(rc<0)return mLastError=rc;*latency=int32_t(std::max<snd_pcm_sframes_t>(delay,0)*1000/48000);return 0;
}
int Playback::drain() {
 std::lock_guard lock(mLock);if(!mPcm)return 0;
 if(snd_pcm_state(mPcm)==SND_PCM_STATE_XRUN)return recoverXrun();
 // Issue DRAIN exactly once. ALSA's hw plugin appends drain silence; calling
 // DRAIN repeatedly while nonblocking would append silence on every attempt.
 int rc=snd_pcm_drain(mPcm);
 if(rc<0&&rc!=-EAGAIN&&rc!=-EINTR)return rc;
 const auto until=nowNs()+2000000000;
 while(rc<0) {
  auto state=snd_pcm_state(mPcm);
  if(state==SND_PCM_STATE_SETUP)break; // Kernel DRAINING -> SETUP completion.
  if(state==SND_PCM_STATE_XRUN)return -EPIPE;
  if(state==SND_PCM_STATE_DISCONNECTED)return -ENODEV;
  if(state!=SND_PCM_STATE_DRAINING)return -EBADFD;
  if(nowNs()>until)return -ETIMEDOUT;
  int waited=snd_pcm_wait(mPcm,100);
  if(waited<0&&waited!=-EINTR&&waited!=-EIO)return waited;
 }
 mPresented=std::max(mPresented,mBasePresented+std::max<int64_t>(0,mWritten-mBootstrap));
 mBasePresented=mPresented;mWritten=mBootstrap=0;return 0;
}
int Playback::pause(){
 std::lock_guard lock(mLock);if(!mPcm)return -EBADFD;if(mPaused)return 0;
 // MCA has no SNDRV_PCM_INFO_PAUSE. Stop the real PCM, then inspect its
 // frozen kernel pointers; preserve the unconsumed tail in our bounded queue.
 if(snd_pcm_state(mPcm)==SND_PCM_STATE_XRUN){int rc=recoverXrun();if(rc<0)return rc;}
 if(snd_pcm_state(mPcm)==SND_PCM_STATE_RUNNING){int rc=snd_pcm_hwsync(mPcm);if(rc<0&&rc!=-EPIPE)return mLastError=rc;}
 int rc=snd_pcm_drop(mPcm);if(rc<0)return mLastError=rc;
 snd_pcm_status_t* status;snd_pcm_status_alloca(&status);if((rc=snd_pcm_status(mPcm,status))<0)return mLastError=rc;
 if(snd_pcm_status_get_state(status)!=SND_PCM_STATE_SETUP)return mLastError=-EBADFD;
 auto avail=snd_pcm_status_get_avail(status);if(avail>mBufferFrames)return mLastError=-EIO;
 size_t queued=mBufferFrames-avail;if(queued>mHistory.size()/4)return mLastError=-EIO;
 mPending.assign(mHistory.end()-queued*4,mHistory.end());
 mPendingBootstrap=size_t(std::max<int64_t>(0,mBootstrap-(mWritten-int64_t(queued))));
 mPresented=std::max(mPresented,mBasePresented+std::max<int64_t>(0,mWritten-int64_t(queued)-mBootstrap));
 mBasePresented=mPresented;mWritten=mBootstrap=0;mHistory.clear();mPaused=true;return 0;
}
int Playback::flush(){
 std::lock_guard lock(mLock);if(!mPcm)return 0;
 if(!mPaused){snd_pcm_sframes_t delay=0;int rc=snd_pcm_delay(mPcm,&delay);if(rc<0&&rc!=-EPIPE)return mLastError=rc;
  if(rc>=0)mPresented=std::max(mPresented,mBasePresented+std::max<int64_t>(0,mWritten-std::max<snd_pcm_sframes_t>(delay,0)-mBootstrap));
  if((rc=snd_pcm_drop(mPcm))<0)return mLastError=rc;
 }
 mBasePresented=mPresented;mWritten=mBootstrap=0;mPaused=false;mPendingBootstrap=0;mPending.clear();mHistory.clear();
 std::fill(mLeft.begin(),mLeft.end(),0);std::fill(mRight.begin(),mRight.end(),0);return snd_pcm_prepare(mPcm);
}
int Playback::closePcm(){if(!mPcm)return 0;snd_pcm_sframes_t delay=0;if(snd_pcm_delay(mPcm,&delay)>=0)mPresented=std::max(mPresented,mBasePresented+std::max<int64_t>(0,mWritten-std::max<snd_pcm_sframes_t>(delay,0)-mBootstrap));mBasePresented=mPresented;mWritten=mBootstrap=0;int rc=snd_pcm_close(mPcm);mPcm=nullptr;mPaused=false;mPending.clear();mHistory.clear();mPendingBootstrap=0;return rc;}
int Playback::standby(){std::lock_guard lock(mLock);int rc=closePcm();LOG(INFO)<<diagnosticsLocked();return rc;}
int Playback::position(int64_t* presented,int64_t* ns){std::lock_guard lock(mLock);if(mPcm&&!mPaused&&snd_pcm_state(mPcm)!=SND_PCM_STATE_SETUP){snd_pcm_sframes_t delay=0;int rc=snd_pcm_delay(mPcm,&delay);if(rc<0)return rc;mPresented=std::max(mPresented,std::max<int64_t>(0,mBasePresented+std::max<int64_t>(0,mWritten-std::max<snd_pcm_sframes_t>(delay,0)-mBootstrap)));}*presented=mPresented;*ns=nowNs();return 0;}
std::string Playback::diagnostics() {std::lock_guard lock(mLock);return diagnosticsLocked();}
std::string Playback::diagnosticsLocked() {
 std::ostringstream out;
 out<<"M1_REAL_AUDIO card="<<mCard<<" pcm="<<(mPcm?snd_pcm_state_name(snd_pcm_state(mPcm)):"closed")
    <<" submitted="<<mWritten<<" observed_presented="<<mPresented<<" bootstrap="<<mBootstrap
    <<" xrun_recoveries="<<mXruns<<" last_error="<<mLastError<<" last_write_ns="<<mLastWriteNs
    <<" buffered_pause="<<mPaused<<" retained_frames="<<mPending.size()/4<<" input_peak="<<mInputPeak<<" output_peak="<<mOutputPeak<<" output_limit=0.125\n";
 if(mPcm){snd_pcm_sframes_t d=0;int rc=snd_pcm_delay(mPcm,&d);out<<"M1_REAL_PCM delay_rc="<<rc<<" delay_frames="<<(rc<0?0:d)<<"\n";}
 if(!mCtl)return out.str();
 snd_ctl_elem_list_t* list;snd_ctl_elem_list_alloca(&list);
 int rc=snd_ctl_elem_list(mCtl,list);if(rc<0){out<<"M1_MIXER list_error="<<rc<<"\n";return out.str();}
 unsigned count=snd_ctl_elem_list_get_count(list);if(count>256){out<<"M1_MIXER unexpected_control_count="<<count<<"\n";return out.str();}
 if((rc=snd_ctl_elem_list_alloc_space(list,count))<0){out<<"M1_MIXER allocation_error="<<rc<<"\n";return out.str();}
 if((rc=snd_ctl_elem_list(mCtl,list))>=0)for(unsigned n=0;n<snd_ctl_elem_list_get_used(list);n++){
  snd_ctl_elem_info_t* info;snd_ctl_elem_info_alloca(&info);snd_ctl_elem_info_set_numid(info,snd_ctl_elem_list_get_numid(list,n));
  if((rc=snd_ctl_elem_info(mCtl,info))<0){out<<"M1_MIXER info_error="<<rc<<"\n";continue;}
  out<<"M1_MIXER name=\""<<snd_ctl_elem_info_get_name(info)<<"\" owner="<<snd_ctl_elem_info_get_owner(info)<<" locked="<<snd_ctl_elem_info_is_locked(info);
  snd_ctl_elem_value_t* val;snd_ctl_elem_value_alloca(&val);snd_ctl_elem_value_set_numid(val,snd_ctl_elem_info_get_numid(info));
  if((rc=snd_ctl_elem_read(mCtl,val))<0){out<<" read_error="<<rc<<"\n";continue;}
  auto type=snd_ctl_elem_info_get_type(info);out<<" values=";
  for(unsigned c=0;c<std::min(16u,snd_ctl_elem_info_get_count(info));c++){
   if(c)out<<',';
   if(type==SND_CTL_ELEM_TYPE_INTEGER||type==SND_CTL_ELEM_TYPE_BOOLEAN)out<<snd_ctl_elem_value_get_integer(val,c);
   else if(type==SND_CTL_ELEM_TYPE_ENUMERATED){unsigned e=snd_ctl_elem_value_get_enumerated(val,c);out<<e;snd_ctl_elem_info_set_item(info,e);if(snd_ctl_elem_info(mCtl,info)>=0)out<<':'<<snd_ctl_elem_info_get_item_name(info);}
   else out<<"unreported_type_"<<int(type);
  }
  if(type==SND_CTL_ELEM_TYPE_INTEGER)out<<" min="<<snd_ctl_elem_info_get_min(info)<<" max="<<snd_ctl_elem_info_get_max(info);
  out<<"\n";
 }
 snd_ctl_elem_list_free_space(list);return out.str();
}

}
