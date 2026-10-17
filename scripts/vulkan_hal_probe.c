// Exercise the real Android Vulkan HAL without a loader or window-system dependency.
#include <dlfcn.h>
#include <hardware/hwvulkan.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vndksupport/linker.h>
#ifdef GOS_LOGCAT
#include <android/log.h>
#include <selinux/selinux.h>
#include <unistd.h>
#define printf(...) __android_log_print(ANDROID_LOG_INFO, "googlebook-vulkan", __VA_ARGS__)
#define fprintf(stream, ...) __android_log_print(ANDROID_LOG_ERROR, "googlebook-vulkan", __VA_ARGS__)
#endif

#define LOAD_I(name) PFN_##name name=(PFN_##name)hal->GetInstanceProcAddr(instance,#name); if(!name){fprintf(stderr,"Missing %s\n",#name);return 3;}
#define CHECK(expr) do{VkResult r=(expr);if(r!=VK_SUCCESS){fprintf(stderr,"VULKAN_SMOKE_FAIL: %s = %d\n",#expr,r);return 4;}}while(0)

int main(int argc,char** argv) {
#ifdef GOS_LOGCAT
    char *context = NULL;
    if (getcon(&context)) { fprintf(stderr,"VULKAN_SMOKE_FAIL: cannot read process context\n");return 10; }
    printf("VULKAN_PROBE_CONTEXT: uid=%u context=%s\n",(unsigned)getuid(),context);
    int valid_context = strcmp(context,"u:r:gpuservice:s0") == 0;
    freecon(context);
    if (!valid_context) { fprintf(stderr,"VULKAN_SMOKE_FAIL: diagnostic service has wrong domain\n");return 11; }
#endif
    const char* path=argc>1?argv[1]:"/vendor/lib64/hw/vulkan.pastel.so";
    void* library=android_load_sphal_library(path,RTLD_NOW|RTLD_LOCAL);
    if(!library){fprintf(stderr,"VULKAN_SMOKE_FAIL: dlopen: %s\n",dlerror());return 1;}
    hwvulkan_module_t* module=dlsym(library,"HMI");
    hw_device_t* device=NULL;
    if(!module||module->common.methods->open(&module->common,HWVULKAN_DEVICE_0,&device)){
        fprintf(stderr,"VULKAN_SMOKE_FAIL: open Android HAL\n");return 2;
    }
    hwvulkan_device_t* hal=(hwvulkan_device_t*)device;
    VkApplicationInfo app={.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,.pApplicationName="GoogleBook HAL probe",.apiVersion=VK_API_VERSION_1_1};
    VkInstanceCreateInfo ci={.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,.pApplicationInfo=&app};
    VkInstance instance; CHECK(hal->CreateInstance(&ci,NULL,&instance));
    LOAD_I(vkEnumeratePhysicalDevices);LOAD_I(vkGetPhysicalDeviceProperties);
    LOAD_I(vkGetPhysicalDeviceQueueFamilyProperties);LOAD_I(vkCreateDevice);
    LOAD_I(vkGetPhysicalDeviceMemoryProperties);LOAD_I(vkDestroyInstance);
    uint32_t count=0;CHECK(vkEnumeratePhysicalDevices(instance,&count,NULL));
    if(!count){fprintf(stderr,"VULKAN_SMOKE_FAIL: no physical device\n");return 5;}
    VkPhysicalDevice physical; count=1;CHECK(vkEnumeratePhysicalDevices(instance,&count,&physical));
    VkPhysicalDeviceProperties props;vkGetPhysicalDeviceProperties(physical,&props);
    printf("VULKAN_DEVICE: name=%s type=%d vendor=%x api=%x\n",props.deviceName,props.deviceType,props.vendorID,props.apiVersion);
#ifdef GOS_REQUIRE_APPLE_GPU
    LOAD_I(vkGetPhysicalDeviceProperties2);
    VkPhysicalDeviceDriverProperties driver={.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
    VkPhysicalDeviceProperties2 extended={.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2,.pNext=&driver};
    vkGetPhysicalDeviceProperties2(physical,&extended);
    printf("VULKAN_DRIVER: id=%u name=%s\n",driver.driverID,driver.driverName);
    /* Honeykrisp reports the Mesa Vulkan vendor ID, not Apple's PCI ID. */
    if (driver.driverID != VK_DRIVER_ID_MESA_HONEYKRISP || props.deviceType != VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU) {
        fprintf(stderr,"VULKAN_SMOKE_FAIL: native probe did not find an integrated Honeykrisp GPU\n");return 9;
    }
#endif
    uint32_t qcount=0;vkGetPhysicalDeviceQueueFamilyProperties(physical,&qcount,NULL);
    VkQueueFamilyProperties* families=calloc(qcount,sizeof(*families));
    vkGetPhysicalDeviceQueueFamilyProperties(physical,&qcount,families);
    uint32_t family=0;while(family<qcount&&!(families[family].queueFlags&VK_QUEUE_TRANSFER_BIT))family++;
    if(family==qcount){fprintf(stderr,"VULKAN_SMOKE_FAIL: no transfer queue family\n");return 6;}
    float priority=1;
    VkDeviceQueueCreateInfo qi={.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,.queueFamilyIndex=family,.queueCount=1,.pQueuePriorities=&priority};
    VkDeviceCreateInfo di={.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,.queueCreateInfoCount=1,.pQueueCreateInfos=&qi};
    VkDevice logical;CHECK(vkCreateDevice(physical,&di,NULL,&logical));
    LOAD_I(vkCreateBuffer);LOAD_I(vkGetBufferMemoryRequirements);LOAD_I(vkAllocateMemory);
    LOAD_I(vkBindBufferMemory);LOAD_I(vkMapMemory);LOAD_I(vkUnmapMemory);
    LOAD_I(vkGetDeviceQueue);LOAD_I(vkCreateCommandPool);LOAD_I(vkAllocateCommandBuffers);
    LOAD_I(vkBeginCommandBuffer);LOAD_I(vkCmdFillBuffer);LOAD_I(vkEndCommandBuffer);
    LOAD_I(vkQueueSubmit);LOAD_I(vkQueueWaitIdle);LOAD_I(vkDestroyBuffer);
    LOAD_I(vkFreeMemory);LOAD_I(vkDestroyCommandPool);LOAD_I(vkDestroyDevice);
    VkBufferCreateInfo bi={.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,.size=4096,.usage=VK_BUFFER_USAGE_TRANSFER_DST_BIT,.sharingMode=VK_SHARING_MODE_EXCLUSIVE};
    VkBuffer buffer;CHECK(vkCreateBuffer(logical,&bi,NULL,&buffer));
    VkMemoryRequirements req;vkGetBufferMemoryRequirements(logical,buffer,&req);
    VkPhysicalDeviceMemoryProperties mem;vkGetPhysicalDeviceMemoryProperties(physical,&mem);
    uint32_t type=0;for(;type<mem.memoryTypeCount;type++)if((req.memoryTypeBits&(1u<<type))&&(mem.memoryTypes[type].propertyFlags&VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT)&&(mem.memoryTypes[type].propertyFlags&VK_MEMORY_PROPERTY_HOST_COHERENT_BIT))break;
    if(type==mem.memoryTypeCount){fprintf(stderr,"VULKAN_SMOKE_FAIL: no host-visible coherent memory type\n");return 7;}
    VkMemoryAllocateInfo ai={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,.allocationSize=req.size,.memoryTypeIndex=type};
    VkDeviceMemory memory;CHECK(vkAllocateMemory(logical,&ai,NULL,&memory));CHECK(vkBindBufferMemory(logical,buffer,memory,0));
    uint32_t* mapped;CHECK(vkMapMemory(logical,memory,0,VK_WHOLE_SIZE,0,(void**)&mapped));
    memset(mapped,0,4096);
    VkCommandPoolCreateInfo pi={.sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,.queueFamilyIndex=family};
    VkCommandPool pool;CHECK(vkCreateCommandPool(logical,&pi,NULL,&pool));
    VkCommandBufferAllocateInfo cai={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,.commandPool=pool,.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY,.commandBufferCount=1};
    VkCommandBuffer command;CHECK(vkAllocateCommandBuffers(logical,&cai,&command));
    VkCommandBufferBeginInfo begin={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};CHECK(vkBeginCommandBuffer(command,&begin));
    vkCmdFillBuffer(command,buffer,0,4096,0x1234abcd);CHECK(vkEndCommandBuffer(command));
    VkQueue queue;vkGetDeviceQueue(logical,family,0,&queue);
    VkSubmitInfo submit={.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO,.commandBufferCount=1,.pCommandBuffers=&command};
    CHECK(vkQueueSubmit(queue,1,&submit,VK_NULL_HANDLE));CHECK(vkQueueWaitIdle(queue));
    for(unsigned i=0;i<1024;i++)if(mapped[i]!=0x1234abcd){fprintf(stderr,"VULKAN_SMOKE_FAIL: buffer result mismatch\n");return 8;}
    printf("VULKAN_SMOKE_PASS: Android HAL, device creation, allocation and submitted buffer execution verified\n");
    vkUnmapMemory(logical,memory);vkDestroyCommandPool(logical,pool,NULL);
    vkDestroyBuffer(logical,buffer,NULL);vkFreeMemory(logical,memory,NULL);vkDestroyDevice(logical,NULL);
    vkDestroyInstance(instance,NULL);device->close(device);free(families);android_unload_sphal_library(library);return 0;
}
