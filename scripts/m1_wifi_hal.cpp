// SPDX-License-Identifier: Apache-2.0
// Native brcmfmac/nl80211 backend for the matching public AOSP Wi-Fi service.
// Scanning and association remain owned by wificond/wpa_supplicant.
#include "m1_wifi_linux.h"
#include <hardware_legacy/wifi_hal.h>
#include <wifi_hal/driver_tool.h>
#include <linux/nl80211.h>
#include <linux/ethtool.h>
#include <linux/sockios.h>
#include <net/if.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <sys/eventfd.h>
#include <android/log.h>
#include <poll.h>
#include <unistd.h>
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <map>
#include <memory>
#include <mutex>
#include <set>

namespace native=googlebook::wifi;
namespace {
constexpr char kTag[]="M1WifiHal";
struct Iface {native::Interface kernel;};
struct Session {
    native::Interface primary;native::Phy phy;
    std::map<std::string,std::unique_ptr<Iface>> ifaces;
    std::vector<wifi_interface_handle> handles;
    std::set<std::string> created;
    int cancel=-1;bool stopping=false,worker=false,primaryClaimed=false;
    wifi_cleaned_up_handler cleaned=nullptr;
    ~Session(){if(cancel>=0)close(cancel);}
};
std::mutex mutex;
std::shared_ptr<Session> current;
bool cleanupSucceeded=true;
wifi_error error(int e) {
    if(!e)return WIFI_SUCCESS;
    __android_log_print(ANDROID_LOG_ERROR,kTag,"Linux owner error=%d (%s)",e,strerror(-e));
    switch(-e){case EINVAL:return WIFI_ERROR_INVALID_ARGS;case ENODEV:case ENOENT:return WIFI_ERROR_NOT_AVAILABLE;
        case EOPNOTSUPP:return WIFI_ERROR_NOT_SUPPORTED;case EBUSY:return WIFI_ERROR_BUSY;
        case ETIMEDOUT:return WIFI_ERROR_TIMED_OUT;case ENOMEM:return WIFI_ERROR_OUT_OF_MEMORY;
        default:return WIFI_ERROR_UNKNOWN;}
}
bool valid(wifi_handle h){return current&&reinterpret_cast<wifi_handle>(current.get())==h&&!current->stopping;}
Iface* validIface(wifi_interface_handle h) {
    if(!current||current->stopping)return nullptr;
    for(auto& pair:current->ifaces)if(reinterpret_cast<wifi_interface_handle>(pair.second.get())==h)return pair.second.get();
    return nullptr;
}
int refresh(Session& s) {
    std::vector<native::Interface> observed;int e=native::interfaces(observed);if(e)return e;
    std::set<std::string> live;s.handles.clear();
    for(const auto& i:observed)if(i.phy==s.primary.phy){
        live.insert(i.name);auto& handle=s.ifaces[i.name];if(!handle)handle=std::make_unique<Iface>();
        handle->kernel=i;s.handles.push_back(reinterpret_cast<wifi_interface_handle>(handle.get()));
    }
    for(auto it=s.ifaces.begin();it!=s.ifaces.end();)if(!live.count(it->first))it=s.ifaces.erase(it);else ++it;
    auto p=s.ifaces.find(s.primary.name);if(p==s.ifaces.end()||p->second->kernel.index!=s.primary.index)return -ENODEV;
    return 0;
}
feature_set features(const native::Phy& phy) {
    auto type=[&](unsigned n){return n<64&&(phy.types&(uint64_t(1)<<n));};feature_set set=0;
    if(type(NL80211_IFTYPE_STATION))set|=WIFI_FEATURE_INFRA;
    if(type(NL80211_IFTYPE_AP))set|=WIFI_FEATURE_SOFT_AP;
    if(type(NL80211_IFTYPE_P2P_CLIENT)&&type(NL80211_IFTYPE_P2P_GO))set|=WIFI_FEATURE_P2P;
    if(std::any_of(phy.channels.begin(),phy.channels.end(),[](const auto& c){return !c.disabled&&c.mhz>=4900&&c.mhz<5900;}))set|=WIFI_FEATURE_INFRA_5G;
    return set;
}
unsigned typeMask(uint64_t types) {
    unsigned mask=0;
    if(types&(uint64_t(1)<<NL80211_IFTYPE_STATION))mask|=1u<<WIFI_INTERFACE_TYPE_STA;
    if(types&(uint64_t(1)<<NL80211_IFTYPE_AP))mask|=1u<<WIFI_INTERFACE_TYPE_AP;
    if(types&((uint64_t(1)<<NL80211_IFTYPE_P2P_CLIENT)|(uint64_t(1)<<NL80211_IFTYPE_P2P_GO)))mask|=1u<<WIFI_INTERFACE_TYPE_P2P;
    return mask;
}
wifi_error ready() {native::Interface i;native::Phy p;return error(native::nativeRadio(i,p));}
wifi_error initialize(wifi_handle* h) {
    if(!h)return WIFI_ERROR_INVALID_ARGS;*h=nullptr;std::lock_guard<std::mutex> lock(mutex);
    if(current||!cleanupSucceeded)return WIFI_ERROR_BUSY;
    auto s=std::make_shared<Session>();int e=native::nativeRadio(s->primary,s->phy);if(e)return error(e);
    s->cancel=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK);if(s->cancel<0)return error(-errno);
    if((e=refresh(*s)))return error(e);
    __android_log_print(ANDROID_LOG_INFO,kTag,"Kernel owner brcmfmac: %s ifindex=%u phy=%u types=%llx, channels=%zu combinations=%zu",
        s->primary.name.c_str(),s->primary.index,s->primary.phy,(unsigned long long)s->phy.types,s->phy.channels.size(),s->phy.combinations.size());
    current=s;*h=reinterpret_cast<wifi_handle>(s.get());return WIFI_SUCCESS;
}
void cleanup(wifi_handle h,wifi_cleaned_up_handler callback) {
    std::lock_guard<std::mutex> lock(mutex);
    if(!current||h!=reinterpret_cast<wifi_handle>(current.get())||current->stopping)return;
    current->stopping=true;current->cleaned=callback;
    uint64_t wake=1;ssize_t n;do{n=write(current->cancel,&wake,sizeof(wake));}while(n<0&&errno==EINTR);
    if(n!=sizeof(wake))__android_log_print(ANDROID_LOG_ERROR,kTag,"Stop notification failed: %s",strerror(errno));
}
void eventLoop(wifi_handle h) {
    std::shared_ptr<Session> s;
    {std::lock_guard<std::mutex> lock(mutex);if(!current||h!=reinterpret_cast<wifi_handle>(current.get())||current->worker)return;s=current;s->worker=true;}
    // No vendor asynchronous feature is advertised. This worker owns only the
    // cancellation FD; wificond and supplicant own their kernel event streams.
    for(;;){pollfd p{s->cancel,POLLIN,0};int n=poll(&p,1,-1);if(n<0&&errno==EINTR)continue;if(n<0||p.revents&(POLLIN|POLLERR|POLLHUP|POLLNVAL))break;}
    bool closed=true;
    for(const auto& name:s->created){
        std::vector<native::Interface> all;int e=native::interfaces(all);
        if(!e){auto i=std::find_if(all.begin(),all.end(),[&](const auto& i){return i.name==name&&i.phy==s->primary.phy;});if(i!=all.end())e=native::deleteInterface(i->index);}
        if(e){closed=false;error(e);}
    }
    wifi_cleaned_up_handler callback;
    {std::lock_guard<std::mutex> lock(mutex);callback=s->cleaned;cleanupSucceeded=closed;current.reset();close(s->cancel);s->cancel=-1;}
    // The owner callback follows actual worker/FD closure. The outer AOSP
    // event thread then reports its own completion to WifiLegacyHal::stop().
    if(callback)callback(h);
}
wifi_error getIfaces(wifi_handle h,int* count,wifi_interface_handle** list) {
    if(!count||!list)return WIFI_ERROR_INVALID_ARGS;std::lock_guard<std::mutex> lock(mutex);if(!valid(h))return WIFI_ERROR_UNINITIALIZED;
    int e=refresh(*current);if(e)return error(e);*count=static_cast<int>(current->handles.size());*list=current->handles.data();return WIFI_SUCCESS;
}
wifi_error getName(wifi_interface_handle h,char* name,size_t size) {
    if(!name||!size)return WIFI_ERROR_INVALID_ARGS;std::lock_guard<std::mutex> lock(mutex);auto* i=validIface(h);if(!i)return WIFI_ERROR_UNINITIALIZED;
    if(i->kernel.name.size()+1>size)return WIFI_ERROR_INVALID_ARGS;memcpy(name,i->kernel.name.c_str(),i->kernel.name.size()+1);return WIFI_SUCCESS;
}
wifi_error getFeatures(wifi_interface_handle h,feature_set* out) {
    if(!out)return WIFI_ERROR_INVALID_ARGS;*out=0;std::lock_guard<std::mutex> lock(mutex);if(!validIface(h))return WIFI_ERROR_UNINITIALIZED;
    native::Phy p;int e=native::physicalRadio(current->primary.phy,p);if(e)return error(e);*out=features(p);return WIFI_SUCCESS;
}
wifi_error chipFeatures(wifi_handle h,feature_set* out) {
    if(!out)return WIFI_ERROR_INVALID_ARGS;*out=0;std::lock_guard<std::mutex> lock(mutex);if(!valid(h))return WIFI_ERROR_UNINITIALIZED;
    native::Phy p;int e=native::physicalRadio(current->primary.phy,p);if(e)return error(e);*out=features(p);return WIFI_SUCCESS;
}
wifi_error matrix(wifi_handle h,wifi_iface_concurrency_matrix* out) {
    if(!out)return WIFI_ERROR_INVALID_ARGS;*out={};std::lock_guard<std::mutex> lock(mutex);if(!valid(h))return WIFI_ERROR_UNINITIALIZED;
    native::Phy p;int e=native::physicalRadio(current->primary.phy,p);if(e)return error(e);
    for(const auto& c:p.combinations){
        wifi_iface_combination result{};unsigned sum=0;
        for(const auto& l:c.limits){unsigned mask=typeMask(l.types);if(!mask)continue;
            if(result.num_iface_limits>=MAX_IFACE_LIMITS)return WIFI_ERROR_NOT_SUPPORTED;
            result.iface_limits[result.num_iface_limits++]={l.maximum,mask};sum+=l.maximum;
        }
        if(!result.num_iface_limits)continue;result.max_ifaces=std::min(c.maximum,sum);
        if(out->num_iface_combinations>=MAX_IFACE_COMBINATIONS)return WIFI_ERROR_NOT_SUPPORTED;
        out->iface_combinations[out->num_iface_combinations++]=result;
    }
    // Kernel reports only concurrency combinations. A single supported type is
    // independently permitted even if no multi-interface combination exists.
    if(!out->num_iface_combinations){unsigned mask=typeMask(p.types);if(!mask)return WIFI_ERROR_NOT_SUPPORTED;
        auto& c=out->iface_combinations[out->num_iface_combinations++];c.max_ifaces=1;c.num_iface_limits=1;c.iface_limits[0]={1,mask};}
    return WIFI_SUCCESS;
}
wifi_error supportedName(wifi_handle h,u32 type,char* out,size_t bytes) {
    if(!out||!bytes)return WIFI_ERROR_INVALID_ARGS;std::lock_guard<std::mutex> lock(mutex);if(!valid(h))return WIFI_ERROR_UNINITIALIZED;
    feature_set supported=features(current->phy);
    if ((type==WIFI_INTERFACE_TYPE_STA&&!(supported&WIFI_FEATURE_INFRA)) ||
        (type==WIFI_INTERFACE_TYPE_AP&&!(supported&WIFI_FEATURE_SOFT_AP)) ||
        (type==WIFI_INTERFACE_TYPE_P2P&&!(supported&WIFI_FEATURE_P2P))) return WIFI_ERROR_NOT_SUPPORTED;
    std::string name;
    if(type==WIFI_INTERFACE_TYPE_STA&&!current->primaryClaimed)name=current->primary.name;
    else if(type==WIFI_INTERFACE_TYPE_P2P)name=current->primary.name; // supplicant uses its physical parent
    else if(type==WIFI_INTERFACE_TYPE_STA||type==WIFI_INTERFACE_TYPE_AP){
        const char* prefix=type==WIFI_INTERFACE_TYPE_STA?"wlan":"ap";
        for(unsigned n=0;n<32;++n){std::string candidate=std::string(prefix)+std::to_string(n);if(!if_nametoindex(candidate.c_str())){name=candidate;break;}}
    }else return WIFI_ERROR_NOT_SUPPORTED;
    if(name.empty()||name.size()+1>bytes)return WIFI_ERROR_NOT_AVAILABLE;memcpy(out,name.c_str(),name.size()+1);return WIFI_SUCCESS;
}
wifi_error create(wifi_handle h,const char* requested,wifi_interface_type type) {
    if(!requested||!native::safeName(requested))return WIFI_ERROR_INVALID_ARGS;std::lock_guard<std::mutex> lock(mutex);if(!valid(h))return WIFI_ERROR_UNINITIALIZED;
    unsigned kernelType;
    if(type==WIFI_INTERFACE_TYPE_STA)kernelType=NL80211_IFTYPE_STATION;
    else if(type==WIFI_INTERFACE_TYPE_AP)kernelType=NL80211_IFTYPE_AP;
    else return WIFI_ERROR_NOT_SUPPORTED;
    if(!(current->phy.types&(uint64_t(1)<<kernelType)))return WIFI_ERROR_NOT_SUPPORTED;
    int e=refresh(*current);if(e)return error(e);auto existing=current->ifaces.find(requested);
    if(existing!=current->ifaces.end()){
        if(existing->second->kernel.type!=kernelType)return WIFI_ERROR_NOT_AVAILABLE;
        if(existing->first==current->primary.name)current->primaryClaimed=true;return WIFI_SUCCESS;
    }
    if((e=native::createInterface(current->primary.phy,requested,kernelType)))return error(e);
    // Track immediately after the kernel ACK so failed readback still cleans
    // up this exact owner-created interface at session shutdown.
    current->created.insert(requested);if((e=refresh(*current)))return error(e);
    auto i=current->ifaces.find(requested);if(i==current->ifaces.end()||i->second->kernel.type!=kernelType)return WIFI_ERROR_UNKNOWN;
    return WIFI_SUCCESS;
}
wifi_error remove(wifi_handle h,const char* requested) {
    if(!requested||!native::safeName(requested))return WIFI_ERROR_INVALID_ARGS;std::lock_guard<std::mutex> lock(mutex);if(!valid(h))return WIFI_ERROR_UNINITIALIZED;
    int e=refresh(*current);if(e)return error(e);
    auto i=current->ifaces.find(requested);if(i==current->ifaces.end())return WIFI_ERROR_NOT_AVAILABLE;
    if(i->first==current->primary.name){
        // This interface is kernel-created, not a dynamic interface to delete.
        if((e=native::setInterfaceUp(i->first,false)))return error(e);current->primaryClaimed=false;return WIFI_SUCCESS;
    }
    if(!current->created.count(requested))return WIFI_ERROR_NOT_AVAILABLE;
    if((e=native::deleteInterface(i->second->kernel.index)))return error(e);
    current->created.erase(requested);return error(refresh(*current));
}
wifi_error country(wifi_interface_handle h,const char* code) {
    if(!code||strlen(code)!=2)return WIFI_ERROR_INVALID_ARGS;std::lock_guard<std::mutex> lock(mutex);if(!validIface(h))return WIFI_ERROR_UNINITIALIZED;
    return error(native::setCountry(code));
}
wifi_error channels(wifi_interface_handle h,int band,int maximum,wifi_channel* out,int* count) {
    if(!out||!count||maximum<=0||band<=0||band>7)return WIFI_ERROR_INVALID_ARGS;*count=0;
    std::lock_guard<std::mutex> lock(mutex);if(!validIface(h))return WIFI_ERROR_UNINITIALIZED;
    native::Phy p;int e=native::physicalRadio(current->primary.phy,p);if(e)return error(e);
    for(auto c:p.channels){if(c.disabled)continue;bool selected=(c.mhz>=2400&&c.mhz<2500&&(band&1))||(c.mhz>=4900&&c.mhz<5900&&(band&(c.radar?4:2)));
        if(!selected)continue;if(*count==maximum)return WIFI_ERROR_TOO_MANY_REQUESTS;out[(*count)++]=c.mhz;}
    return WIFI_SUCCESS;
}
wifi_error version(wifi_interface_handle h,char* out,int maximum,bool firmware) {
    if(!out||maximum<=0)return WIFI_ERROR_INVALID_ARGS;std::lock_guard<std::mutex> lock(mutex);auto* i=validIface(h);if(!i)return WIFI_ERROR_UNINITIALIZED;
    int fd=socket(AF_INET,SOCK_DGRAM|SOCK_CLOEXEC,0);if(fd<0)return error(-errno);
    ifreq request{};memcpy(request.ifr_name,i->kernel.name.c_str(),i->kernel.name.size()+1);ethtool_drvinfo info{};info.cmd=ETHTOOL_GDRVINFO;request.ifr_data=reinterpret_cast<char*>(&info);
    int e=ioctl(fd,SIOCETHTOOL,&request)<0?-errno:0;close(fd);if(e)return error(e);
    const char* text=firmware?info.fw_version:info.version;size_t length=strnlen(text,32);if(!length||length>=32||length+1>size_t(maximum))return WIFI_ERROR_NOT_AVAILABLE;
    memcpy(out,text,length+1);return WIFI_SUCCESS;
}
wifi_error firmwareVersion(wifi_interface_handle h,char* out,int maximum){return version(h,out,maximum,true);}
wifi_error driverVersion(wifi_interface_handle h,char* out,int maximum){return version(h,out,maximum,false);}
}
extern "C" wifi_error init_wifi_vendor_hal_func_table(wifi_hal_fn* fn) {
    if(!fn)return WIFI_ERROR_INVALID_ARGS;
    // The matching AOSP service already installs error-returning stubs for
    // unsupported operations. Do not overwrite beyond this source ABI/table.
    fn->wifi_initialize=initialize;fn->wifi_wait_for_driver_ready=ready;fn->wifi_cleanup=cleanup;fn->wifi_event_loop=eventLoop;
    fn->wifi_get_ifaces=getIfaces;fn->wifi_get_iface_name=getName;fn->wifi_get_supported_feature_set=getFeatures;
    fn->wifi_get_chip_feature_set=chipFeatures;fn->wifi_get_supported_iface_concurrency_matrix=matrix;
    fn->wifi_get_supported_iface_name=supportedName;fn->wifi_virtual_interface_create=create;fn->wifi_virtual_interface_delete=remove;
    fn->wifi_set_country_code=country;fn->wifi_get_valid_channels=channels;
    fn->wifi_get_firmware_version=firmwareVersion;fn->wifi_get_driver_version=driverVersion;
    return WIFI_SUCCESS;
}
namespace android::wifi_hal {
const int DriverTool::kFirmwareModeSta=0;const int DriverTool::kFirmwareModeAp=1;const int DriverTool::kFirmwareModeP2p=2;
bool DriverTool::LoadDriver(){std::lock_guard<std::mutex> lock(mutex);return cleanupSucceeded&&ready()==WIFI_SUCCESS;}
bool DriverTool::IsDriverLoaded(){return ready()==WIFI_SUCCESS;}
bool DriverTool::UnloadDriver(){std::lock_guard<std::mutex> lock(mutex);return !current&&cleanupSucceeded;}
bool DriverTool::IsFirmwareModeChangeNeeded(int){return false;}
bool DriverTool::ChangeFirmwareMode(int mode){
    native::Interface i;native::Phy p;if(native::nativeRadio(i,p))return false;
    unsigned type;if(mode==kFirmwareModeSta)type=NL80211_IFTYPE_STATION;else if(mode==kFirmwareModeAp)type=NL80211_IFTYPE_AP;
    else if(mode==kFirmwareModeP2p)type=NL80211_IFTYPE_P2P_CLIENT;else return false;
    return (p.types&(uint64_t(1)<<type))!=0; // one kernel-managed firmware image, no path switch
}
}
