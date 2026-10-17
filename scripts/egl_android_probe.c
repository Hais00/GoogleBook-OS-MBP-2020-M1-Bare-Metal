/* Exercise Android's EGL/GLES loader and a real AHardwareBuffer on the M1. */
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <GLES2/gl2ext.h>
#include <android/hardware_buffer.h>
#include <android/log.h>
#include <android/sharedmem.h>
#include <media/NdkImageReader.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <linux/bpf.h>
#include <sys/syscall.h>
#include <sys/mman.h>
#include <unistd.h>

#define TAG "googlebook-egl"
#define INFO(...) do { __android_log_print(ANDROID_LOG_INFO,TAG,__VA_ARGS__); printf(__VA_ARGS__); puts(""); } while(0)
static int fail(const char *where) {
    __android_log_print(ANDROID_LOG_ERROR,TAG,"NATIVE_EGL_SMOKE_FAIL: %s egl=0x%x gl=0x%x",where,eglGetError(),glGetError());
    fprintf(stderr,"NATIVE_EGL_SMOKE_FAIL: %s\n",where);
    return 1;
}

static bool pixel_ok(const uint8_t *p) {
    const int wanted[4]={64,128,191,255};
    for(int i=0;i<4;i++) if((int)p[i]<wanted[i]-1 || (int)p[i]>wanted[i]+1) return false;
    return true;
}

static void inspect_gpu_bpf_map(void) {
    const char *path="/sys/fs/bpf/map_gpuMem_gpu_mem_total_map";
    union bpf_attr attr;
    memset(&attr,0,sizeof(attr));
    attr.pathname=(uint64_t)(uintptr_t)path;
    attr.file_flags=BPF_F_RDONLY;
    int fd=(int)syscall(__NR_bpf,BPF_OBJ_GET,&attr,sizeof(attr));
    if(fd<0) {
        INFO("GPU_BPF_MAP_OPEN_FAILED: errno=%d %s",errno,strerror(errno));
        return;
    }
    struct bpf_map_info info;
    memset(&info,0,sizeof(info));memset(&attr,0,sizeof(attr));
    attr.info.bpf_fd=fd;attr.info.info_len=sizeof(info);
    attr.info.info=(uint64_t)(uintptr_t)&info;
    if(syscall(__NR_bpf,BPF_OBJ_GET_INFO_BY_FD,&attr,sizeof(attr))<0) {
        INFO("GPU_BPF_MAP_INFO_FAILED: errno=%d %s",errno,strerror(errno));
    } else {
        INFO("GPU_BPF_MAP_INFO: type=%u key=%u value=%u flags=0x%x entries=%u",info.type,info.key_size,info.value_size,info.map_flags,info.max_entries);
    }
    close(fd);
}

static int shared_memory_check(void) {
    const size_t size=(size_t)getpagesize();
    int fd=ASharedMemory_create("googlebook-bitmap-test",size);
    if(fd<0) { INFO("ANDROID_SHARED_MEMORY_FAIL: create errno=%d %s",errno,strerror(errno));return 1; }
    uint8_t *p=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    if(p==MAP_FAILED) { close(fd);return 1; }
    memset(p,0x5a,size);munmap(p,size);
    if(ASharedMemory_getSize(fd)!=size || ASharedMemory_setProt(fd,PROT_READ)!=0) { close(fd);return 1; }
    p=mmap(NULL,size,PROT_READ,MAP_SHARED,fd,0);
    if(p==MAP_FAILED || p[0]!=0x5a || p[size-1]!=0x5a) { close(fd);return 1; }
    munmap(p,size);
    p=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    if(p!=MAP_FAILED) { munmap(p,size);close(fd);return 1; }
    close(fd);
    INFO("ANDROID_SHARED_MEMORY_PASS: real allocation, size, bytes and write seal verified");
    return 0;
}

static int window_surface_check(EGLDisplay display,EGLConfig config,EGLContext context,EGLSurface restore) {
    AImageReader *reader=NULL;
    if(AImageReader_newWithUsage(8,8,AIMAGE_FORMAT_RGBA_8888,
        AHARDWAREBUFFER_USAGE_GPU_COLOR_OUTPUT|AHARDWAREBUFFER_USAGE_CPU_READ_OFTEN,2,&reader)!=AMEDIA_OK)
        return fail("AImageReader window creation");
    ANativeWindow *window=NULL;
    if(AImageReader_getWindow(reader,&window)!=AMEDIA_OK) { AImageReader_delete(reader);return fail("AImageReader_getWindow"); }
    EGLSurface surface=eglCreateWindowSurface(display,config,window,NULL);
    if(surface==EGL_NO_SURFACE || !eglMakeCurrent(display,surface,surface,context)) { AImageReader_delete(reader);return fail("real Android EGL window surface"); }
    glViewport(0,0,8,8);glClearColor(.25f,.5f,.75f,1.f);glClear(GL_COLOR_BUFFER_BIT);glFinish();
    if(!eglSwapBuffers(display,surface)) return fail("Android window eglSwapBuffers");
    AImage *image=NULL;
    media_status_t status=AMEDIA_IMGREADER_NO_BUFFER_AVAILABLE;
    for(int i=0;i<100 && status==AMEDIA_IMGREADER_NO_BUFFER_AVAILABLE;i++) {
        status=AImageReader_acquireNextImage(reader,&image);
        if(status==AMEDIA_IMGREADER_NO_BUFFER_AVAILABLE) usleep(10000);
    }
    if(status!=AMEDIA_OK || image==NULL) return fail("Android window produced no image");
    AHardwareBuffer *buffer=NULL;void *pixels=NULL;
    if(AImage_getHardwareBuffer(image,&buffer)!=AMEDIA_OK ||
       AHardwareBuffer_lock(buffer,AHARDWAREBUFFER_USAGE_CPU_READ_OFTEN,-1,NULL,&pixels)!=0 || !pixel_ok(pixels))
        return fail("Android window GPU image readback");
    AHardwareBuffer_unlock(buffer,NULL);AImage_delete(image);
    eglMakeCurrent(display,restore,restore,context);eglDestroySurface(display,surface);AImageReader_delete(reader);
    INFO("NATIVE_EGL_WINDOW_PASS: real ImageReader window, swap, acquisition and GPU pixels verified");
    return 0;
}

int main(void) {
    setbuf(stdout,NULL);
    inspect_gpu_bpf_map();
    if(shared_memory_check()!=0) return fail("Android shared memory required by Bitmap");
    EGLDisplay display=eglGetDisplay(EGL_DEFAULT_DISPLAY);
    EGLint major=0,minor=0;
    if(display==EGL_NO_DISPLAY || !eglInitialize(display,&major,&minor)) return fail("eglInitialize via Android loader");
    INFO("NATIVE_EGL_DISPLAY: version=%d.%d vendor=%s extensions=%s",major,minor,
         eglQueryString(display,EGL_VENDOR),eglQueryString(display,EGL_EXTENSIONS));
    EGLint attribs[]={EGL_RENDERABLE_TYPE,EGL_OPENGL_ES3_BIT_KHR,
        EGL_SURFACE_TYPE,EGL_WINDOW_BIT|EGL_PBUFFER_BIT,EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,
        EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,8,EGL_NONE};
    EGLConfig configs[128];EGLint count=0;EGLConfig chosen=NULL;
    if(!eglChooseConfig(display,attribs,configs,128,&count) || count==0) return fail("RGBA8 GLES3 window/pbuffer EGLConfig");
    for(int i=0;i<count;i++) {
        EGLint visual=0,recordable=0;
        eglGetConfigAttrib(display,configs[i],EGL_NATIVE_VISUAL_ID,&visual);
        eglGetConfigAttrib(display,configs[i],EGL_RECORDABLE_ANDROID,&recordable);
        INFO("NATIVE_EGL_CONFIG: index=%d native_visual=%d recordable=%d",i,visual,recordable);
        if(visual==AHARDWAREBUFFER_FORMAT_R8G8B8A8_UNORM && chosen==NULL) chosen=configs[i];
    }
    if(chosen==NULL) return fail("no Android RGBA8888 native visual");
    if(!eglBindAPI(EGL_OPENGL_ES_API)) return fail("eglBindAPI");
    const EGLint context_attrs[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    EGLContext context=eglCreateContext(display,chosen,EGL_NO_CONTEXT,context_attrs);
    const EGLint surface_attrs[]={EGL_WIDTH,8,EGL_HEIGHT,8,EGL_NONE};
    EGLSurface surface=eglCreatePbufferSurface(display,chosen,surface_attrs);
    if(context==EGL_NO_CONTEXT || surface==EGL_NO_SURFACE || !eglMakeCurrent(display,surface,surface,context)) return fail("GLES3 pbuffer context");
    const char *renderer=(const char*)glGetString(GL_RENDERER);
    INFO("NATIVE_GLES_RENDERER: vendor=%s renderer=%s version=%s",glGetString(GL_VENDOR),renderer,glGetString(GL_VERSION));
    if(!renderer || (!strstr(renderer,"Apple") && !strstr(renderer,"Asahi") && !strstr(renderer,"AGX"))) return fail("renderer is not the Apple GPU");
    glViewport(0,0,8,8);glClearColor(.25f,.5f,.75f,1.f);glClear(GL_COLOR_BUFFER_BIT);glFinish();
    uint8_t pixel[4]={0};glReadPixels(0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
    if(glGetError()!=GL_NO_ERROR || !pixel_ok(pixel)) return fail("GPU pbuffer RGBA readback");
    INFO("NATIVE_EGL_PBUFFER_PASS: pixel=%u,%u,%u,%u",pixel[0],pixel[1],pixel[2],pixel[3]);

    PFNEGLGETNATIVECLIENTBUFFERANDROIDPROC get_buffer=(PFNEGLGETNATIVECLIENTBUFFERANDROIDPROC)eglGetProcAddress("eglGetNativeClientBufferANDROID");
    PFNEGLCREATEIMAGEKHRPROC create_image=(PFNEGLCREATEIMAGEKHRPROC)eglGetProcAddress("eglCreateImageKHR");
    PFNEGLDESTROYIMAGEKHRPROC destroy_image=(PFNEGLDESTROYIMAGEKHRPROC)eglGetProcAddress("eglDestroyImageKHR");
    PFNGLEGLIMAGETARGETTEXTURE2DOESPROC image_target=(PFNGLEGLIMAGETARGETTEXTURE2DOESPROC)eglGetProcAddress("glEGLImageTargetTexture2DOES");
    if(!get_buffer || !create_image || !destroy_image || !image_target) return fail("Android EGL image entrypoints");
    AHardwareBuffer_Desc desc={.width=8,.height=8,.layers=1,.format=AHARDWAREBUFFER_FORMAT_R8G8B8A8_UNORM,
        .usage=AHARDWAREBUFFER_USAGE_GPU_SAMPLED_IMAGE|AHARDWAREBUFFER_USAGE_GPU_COLOR_OUTPUT|AHARDWAREBUFFER_USAGE_CPU_READ_OFTEN};
    AHardwareBuffer *buffer=NULL;
    int result=AHardwareBuffer_allocate(&desc,&buffer);
    if(result || !buffer) { INFO("NATIVE_AHB_ALLOCATE: error=%d",result);return fail("AHardwareBuffer_allocate"); }
    EGLClientBuffer client=get_buffer(buffer);
    const EGLint image_attrs[]={EGL_IMAGE_PRESERVED_KHR,EGL_TRUE,EGL_NONE};
    EGLImageKHR image=create_image(display,EGL_NO_CONTEXT,EGL_NATIVE_BUFFER_ANDROID,client,image_attrs);
    if(image==EGL_NO_IMAGE_KHR) return fail("EGL import of AHardwareBuffer");
    GLuint texture=0,framebuffer=0;
    glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);
    image_target(GL_TEXTURE_2D,image);
    glGenFramebuffers(1,&framebuffer);glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
    if(glGetError()!=GL_NO_ERROR || glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE) return fail("AHardwareBuffer framebuffer");
    glViewport(0,0,8,8);glClearColor(.25f,.5f,.75f,1.f);glClear(GL_COLOR_BUFFER_BIT);glFinish();
    memset(pixel,0,sizeof(pixel));glReadPixels(0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
    if(glGetError()!=GL_NO_ERROR || !pixel_ok(pixel)) return fail("GPU AHardwareBuffer pixel readback");
    void *cpu=NULL;
    result=AHardwareBuffer_lock(buffer,AHARDWAREBUFFER_USAGE_CPU_READ_OFTEN,-1,NULL,&cpu);
    if(result || !cpu) { INFO("NATIVE_AHB_LOCK: error=%d",result);return fail("CPU read of GPU-written AHardwareBuffer"); }
    bool matches=pixel_ok(cpu);
    int unlock=AHardwareBuffer_unlock(buffer,NULL);
    if(!matches || unlock) return fail("AHardwareBuffer CPU pixel match/unlock");
    INFO("NATIVE_AHB_IMPORT_PASS: GPU rendering and CPU readback match");
    glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&framebuffer);glDeleteTextures(1,&texture);
    destroy_image(display,image);AHardwareBuffer_release(buffer);
    if(window_surface_check(display,chosen,context,surface)!=0) return 1;
    eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroySurface(display,surface);eglDestroyContext(display,context);eglTerminate(display);
    INFO("NATIVE_EGL_SMOKE_PASS: Android shared memory, Apple GLES3, GPU pixels, AHardwareBuffer and real window swap verified");
    return 0;
}
