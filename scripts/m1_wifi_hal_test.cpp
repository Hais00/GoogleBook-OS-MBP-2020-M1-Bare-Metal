// SPDX-License-Identifier: Apache-2.0
// CPU-only transport fixtures. This executable is never a production provider.
#include "m1_wifi_linux.h"
#include <hardware_legacy/wifi_hal.h>
#include <wifi_hal/driver_tool.h>
#include <linux/nl80211.h>
#include <dirent.h>
#include <atomic>
#include <android/log.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>
namespace n=googlebook::wifi;
static int transportError=0;static bool missingAck=false;
static std::vector<n::Interface> observed;
static n::Phy fixture;
static std::atomic<unsigned> callbacks{0};static unsigned expectedFdCount=0;
static unsigned cases=0;
static void check(bool ok,const char* why){++cases;if(!ok){fprintf(stderr,"WIFI_CPU_FIXTURE_FAIL: %s\n",why);exit(1);}}
static unsigned fdCount(){DIR*d=opendir("/proc/self/fd");if(!d)return 0;unsigned n=0;while(auto* e=readdir(d))if(e->d_name[0]!='.')++n;closedir(d);return n;}
namespace googlebook::wifi {
bool safeName(const std::string& s){return !s.empty()&&s.size()<16&&s.find('/')==std::string::npos;}
int interfaces(std::vector<Interface>& out){if(transportError)return transportError;out=observed;return 0;}
int physicalRadio(unsigned,Phy& out){if(transportError)return transportError;out=fixture;return 0;}
int nativeRadio(Interface& i,Phy& p){if(transportError)return transportError;if(observed.empty())return -19;i=observed[0];p=fixture;return 0;}
int createInterface(unsigned phy,const std::string& name,unsigned type){if(transportError)return transportError;if(!missingAck)observed.push_back({9,phy,type,name});return 0;}
int deleteInterface(unsigned index){for(auto it=observed.begin();it!=observed.end();++it)if(it->index==index){observed.erase(it);return 0;}return -19;}
int setInterfaceUp(const std::string&,bool){return transportError;}
int setCountry(const char[2]){return transportError;}
}
static void cleaned(wifi_handle){check(fdCount()==expectedFdCount,"worker FD closes before completion callback");++callbacks;}
static wifi_handle start(wifi_hal_fn& fn){wifi_handle h=nullptr;check(fn.wifi_initialize(&h)==WIFI_SUCCESS&&h,"real production initializer accepts a qualified transport fixture");return h;}
static void stop(wifi_hal_fn& fn,wifi_handle h,bool cleanupBeforeWorker){
 unsigned before=callbacks.load();std::thread worker;
 if(!cleanupBeforeWorker)worker=std::thread([&]{fn.wifi_event_loop(h);});
 fn.wifi_cleanup(h,cleaned);fn.wifi_cleanup(h,cleaned);
 if(cleanupBeforeWorker)worker=std::thread([&]{fn.wifi_event_loop(h);});
 worker.join();check(callbacks==before+1,"exactly one stop callback including repeated cleanup");
 check(fdCount()==expectedFdCount,"session teardown leaves no FD leak");
}
int main(){
 __android_log_print(ANDROID_LOG_INFO,"M1WifiHalTest","CPU-only transport fixtures");
 expectedFdCount=fdCount();check(expectedFdCount>0,"actual Bionic process FD census works");
 fixture.index=0;fixture.types=(1ull<<NL80211_IFTYPE_STATION)|(1ull<<NL80211_IFTYPE_AP);
 fixture.channels={{2412,false,false,false},{5260,false,false,true},{5180,false,false,false},{5745,true,false,false}};
 fixture.combinations={{2,1,{{1,1ull<<NL80211_IFTYPE_STATION},{1,1ull<<NL80211_IFTYPE_AP}}}};
 observed={{6,0,NL80211_IFTYPE_STATION,"fixture0"}};
 wifi_hal_fn fn{};check(init_wifi_vendor_hal_func_table(nullptr)==WIFI_ERROR_INVALID_ARGS,"null function table is rejected");
 check(init_wifi_vendor_hal_func_table(&fn)==WIFI_SUCCESS,"public AOSP function table is populated");
 check(!fn.wifi_start_gscan&&!fn.wifi_set_scanning_mac_oui,"unsupported operations are not replaced with successful no-ops");
 transportError=-19;wifi_handle h=reinterpret_cast<wifi_handle>(1);check(fn.wifi_initialize(&h)!=WIFI_SUCCESS&&h==nullptr,"missing device cannot produce a handle");
 transportError=-13;check(fn.wifi_wait_for_driver_ready()!=WIFI_SUCCESS,"permission failure cannot qualify driver readiness");transportError=0;
 android::wifi_hal::DriverTool driver;check(driver.LoadDriver(),"driver gate accepts observed fixture owner");
 h=start(fn);check(!driver.UnloadDriver(),"active owner prevents unload completion");
 int count=0;wifi_interface_handle* list=nullptr;check(fn.wifi_get_ifaces(h,&count,&list)==WIFI_SUCCESS&&count==1,"interface count comes from observed devices");
 auto primary=list[0];char name[32]{};check(fn.wifi_get_iface_name(primary,name,sizeof(name))==WIFI_SUCCESS&&!strcmp(name,"fixture0"),"actual observed name is retained");
 check(fn.wifi_get_iface_name(primary,name,2)==WIFI_ERROR_INVALID_ARGS,"short name destination is rejected");
 feature_set feature=0;check(fn.wifi_get_supported_feature_set(primary,&feature)==WIFI_SUCCESS&&(feature&WIFI_FEATURE_INFRA_5G),"enabled 5GHz channel qualifies 5GHz capability");
 check(!(feature&WIFI_FEATURE_P2P)&&!(feature&WIFI_FEATURE_LINK_LAYER_STATS),"unobserved P2P and unimplemented link statistics remain absent");
 wifi_channel frequencies[8];int total=0;check(fn.wifi_get_valid_channels(primary,2,8,frequencies,&total)==WIFI_SUCCESS&&total==1&&frequencies[0]==5180,"non-DFS band excludes DFS and disabled channels");
 check(fn.wifi_get_valid_channels(primary,4,8,frequencies,&total)==WIFI_SUCCESS&&total==1&&frequencies[0]==5260,"DFS-only band returns only actual DFS channels");
 wifi_iface_concurrency_matrix matrix{};check(fn.wifi_get_supported_iface_concurrency_matrix(h,&matrix)==WIFI_SUCCESS&&matrix.num_iface_combinations==1,"observed concurrency matrix is returned");
 check(matrix.iface_combinations[0].max_ifaces==2&&matrix.iface_combinations[0].num_iface_limits==2,"kernel limits are retained without widening");
 check(fn.wifi_get_supported_iface_name(h,WIFI_INTERFACE_TYPE_P2P,name,sizeof(name))==WIFI_ERROR_NOT_SUPPORTED,"unsupported role cannot advertise an interface name");
 transportError=-13;feature=~0ull;check(fn.wifi_get_supported_feature_set(primary,&feature)!=WIFI_SUCCESS&&feature==0,"dynamic provider failure revokes feature result");transportError=0;
 missingAck=true;check(fn.wifi_virtual_interface_create(h,"fixture-ap",WIFI_INTERFACE_TYPE_AP)!=WIFI_SUCCESS,"successful transport return without observed creation is rejected");missingAck=false;
 check(fn.wifi_virtual_interface_create(h,"fixture-ap",WIFI_INTERFACE_TYPE_AP)==WIFI_SUCCESS,"observed real creation path is accepted by the model");
 check(fn.wifi_virtual_interface_delete(h,"fixture-ap")==WIFI_SUCCESS&&observed.size()==1,"only owner-created secondary interface is deleted");
 stop(fn,h,true);check(driver.UnloadDriver(),"closed worker permits owner release");
 check(fn.wifi_get_ifaces(h,&count,&list)==WIFI_ERROR_UNINITIALIZED,"stopped session handle cannot enumerate interfaces");
 for(unsigned i=0;i<20;i++){h=start(fn);stop(fn,h,i%2);}
 puts("M1_WIFI_CPU_FIXTURES_PASS");printf("ASSERTIONS=%u callback_cycles=%u; simulated transport, no radio qualification\n",cases,callbacks.load());return 0;
}
