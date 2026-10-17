// SPDX-License-Identifier: Apache-2.0
// Enumerate actual selected framework components and read real V4L2 capabilities.
// No camera buffers, no codec configuration, no stream start, no video capture.
#include <media/NdkMediaCodec.h>
#include <android/binder_process.h>
#include <linux/videodev2.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <unistd.h>
#include <cstdio>
#include <cerrno>
#include <cstring>
int main(){
 setbuf(stdout,nullptr);ABinderProcess_setThreadPoolMaxThreadCount(4);ABinderProcess_startThreadPool();
 const char* mime[]={"video/avc","video/hevc","video/x-vnd.on2.vp9","video/av01"};
 for(auto type:mime)for(int encode=0;encode<2;encode++){
  AMediaCodec* c=encode?AMediaCodec_createEncoderByType(type):AMediaCodec_createDecoderByType(type);
  if(!c){printf("ANDROID_CODEC_SELECTED mime=%s direction=%s available=0\n",type,encode?"encode":"decode");continue;}
  char* name=nullptr;media_status_t r=AMediaCodec_getName(c,&name);
  printf("ANDROID_CODEC_SELECTED mime=%s direction=%s query_status=%d component=%s\n",type,encode?"encode":"decode",int(r),name?name:"<unavailable>");
  if(name)AMediaCodec_releaseName(c,name);AMediaCodec_delete(c);
 }
 for(int n=0;n<64;n++){
  char path[40];snprintf(path,sizeof(path),"/dev/video%d",n);int fd=open(path,O_RDONLY|O_NONBLOCK|O_CLOEXEC);
  if(fd<0){if(errno!=ENOENT)printf("V4L2_QUERY_ERROR path=%s errno=%d %s\n",path,errno,strerror(errno));continue;}
  v4l2_capability c{};if(ioctl(fd,VIDIOC_QUERYCAP,&c)<0){printf("V4L2_QUERY_ERROR path=%s errno=%d\n",path,errno);close(fd);continue;}
  printf("V4L2_ACTUAL_DEVICE path=%s driver=%s card=%s bus=%s capabilities=%x device_caps=%x\n",path,c.driver,c.card,c.bus_info,c.capabilities,c.device_caps);
  unsigned queueTypes[]={V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE,V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE};
  for(auto type:queueTypes)for(unsigned i=0;i<128;i++){
   v4l2_fmtdesc f{};f.index=i;f.type=type;if(ioctl(fd,VIDIOC_ENUM_FMT,&f)<0)break;
   printf("V4L2_ACTUAL_FORMAT path=%s queue=%u fourcc=%c%c%c%c description=%s flags=%x\n",path,unsigned(type),f.pixelformat&255,(f.pixelformat>>8)&255,(f.pixelformat>>16)&255,(f.pixelformat>>24)&255,f.description,f.flags);
  }
  close(fd);
 }
 puts("CODEC_INVENTORY_COMPLETE_NO_STREAM_STARTED");return 0;
}
