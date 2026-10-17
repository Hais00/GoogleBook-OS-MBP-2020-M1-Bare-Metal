// SPDX-License-Identifier: Apache-2.0
// Linux nl80211 transport. libnl owns message/TLV validation and sequencing.
#include "m1_wifi_linux.h"
#include <netlink/netlink.h>
#include <netlink/socket.h>
#include <netlink/msg.h>
#include <netlink/attr.h>
#include <netlink/genl/genl.h>
#include <netlink/genl/ctrl.h>
#include <linux/nl80211.h>
#include <linux/if.h>
#include <linux/ethtool.h>
#include <linux/sockios.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <poll.h>
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <functional>
#include <memory>

namespace googlebook::wifi {
namespace {
struct SockDelete { void operator()(nl_sock* p) const { nl_socket_free(p); } };
struct MsgDelete { void operator()(nl_msg* p) const { nlmsg_free(p); } };
struct CbDelete { void operator()(nl_cb* p) const { nl_cb_put(p); } };
using Attrs=std::vector<nlattr*>;
int parseAttrs(nl_msg* message, Attrs& attrs) {
    nlmsghdr* header=nlmsg_hdr(message);
    if (!genlmsg_valid_hdr(header, 0)) return -EBADMSG;
    auto* generic=static_cast<genlmsghdr*>(nlmsg_data(header));
    attrs.assign(NL80211_ATTR_MAX+1,nullptr);
    if (nla_parse(attrs.data(),NL80211_ATTR_MAX,genlmsg_attrdata(generic,0),genlmsg_attrlen(generic,0),nullptr)<0) return -EBADMSG;
    return 0;
}
bool u32(nlattr* a) { return a && nla_len(a)==int(sizeof(uint32_t)); }
struct Reply {
    bool done=false; int error=0;
    std::function<int(nl_msg*)> valid;
};
int validReply(nl_msg* m,void* arg) {
    auto& r=*static_cast<Reply*>(arg);int e=r.valid?r.valid(m):0;
    if(e){r.error=e;r.done=true;return NL_STOP;}return NL_OK;
}
int finished(nl_msg*,void* arg) { static_cast<Reply*>(arg)->done=true;return NL_STOP; }
int failed(sockaddr_nl*,nlmsgerr* e,void* arg) {
    auto& r=*static_cast<Reply*>(arg);r.error=e->error?e->error:-EIO;r.done=true;return NL_STOP;
}
int transfer(int command, bool dump, const std::function<int(nl_msg*)>& fill,
             std::function<int(nl_msg*)> valid={}) {
    std::unique_ptr<nl_sock,SockDelete> socket(nl_socket_alloc());
    std::unique_ptr<nl_msg,MsgDelete> message(nlmsg_alloc());
    std::unique_ptr<nl_cb,CbDelete> callbacks(nl_cb_alloc(NL_CB_DEFAULT));
    if(!socket||!message||!callbacks)return -ENOMEM;
    if(genl_connect(socket.get())<0)return errno?-errno:-EIO;
    int family=genl_ctrl_resolve(socket.get(),"nl80211");if(family<0)return -ENODEV;
    int flags=dump?NLM_F_DUMP:0;
    if(!genlmsg_put(message.get(),NL_AUTO_PORT,NL_AUTO_SEQ,family,0,flags,command,0))return -ENOMEM;
    int error=fill?fill(message.get()):0;if(error)return error;
    Reply reply;reply.valid=std::move(valid);
    nl_cb_set(callbacks.get(),NL_CB_VALID,NL_CB_CUSTOM,validReply,&reply);
    nl_cb_set(callbacks.get(),NL_CB_FINISH,NL_CB_CUSTOM,finished,&reply);
    // A dump terminates at NLMSG_DONE; an ACK must not truncate its data.
    if(!dump)nl_cb_set(callbacks.get(),NL_CB_ACK,NL_CB_CUSTOM,finished,&reply);
    nl_cb_err(callbacks.get(),NL_CB_CUSTOM,failed,&reply);
    if(nl_send_auto_complete(socket.get(),message.get())<0)return -EIO;
    if(nl_socket_set_nonblocking(socket.get())<0)return -EIO;
    auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(3);
    while(!reply.done) {
        auto remaining=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-std::chrono::steady_clock::now()).count();
        if(remaining<=0)return -ETIMEDOUT;
        pollfd poller{nl_socket_get_fd(socket.get()),POLLIN,0};
        int n=poll(&poller,1,static_cast<int>(remaining));
        if(n<0&&errno==EINTR)continue;if(n<0)return -errno;if(n==0)return -ETIMEDOUT;
        if(poller.revents&(POLLHUP|POLLERR|POLLNVAL))return -EIO;
        int result=nl_recvmsgs(socket.get(),callbacks.get());
        if(result<0&&result!=-NLE_AGAIN)return reply.error?reply.error:-EBADMSG;
    }
    return reply.error;
}
int addU32(nl_msg* m,int key,unsigned v) { return nla_put_u32(m,key,v)<0?-ENOMEM:0; }
int nestedTypes(nlattr* root,uint64_t& types) {
    nlattr* a;int left;nla_for_each_nested(a,root,left){unsigned bit=nla_type(a);if(bit<64)types|=uint64_t(1)<<bit;}
    return left==0?0:-EBADMSG;
}
int arrayU32(nlattr* a,std::vector<uint32_t>& out) {
    if(nla_len(a)%sizeof(uint32_t))return -EBADMSG;
    const unsigned char* p=static_cast<const unsigned char*>(nla_data(a));
    for(int i=0;i<nla_len(a);i+=sizeof(uint32_t)){uint32_t value;memcpy(&value,p+i,sizeof(value));if(std::find(out.begin(),out.end(),value)==out.end())out.push_back(value);}
    return 0;
}
}
bool safeName(const std::string& name) {
    return !name.empty()&&name.size()<IFNAMSIZ&&std::all_of(name.begin(),name.end(),[](unsigned char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-'||c=='.';});
}
int interfaces(std::vector<Interface>& out) {
    std::vector<Interface> found;
    int error=transfer(NL80211_CMD_GET_INTERFACE,true,{},[&](nl_msg* m){
        Attrs a;int e=parseAttrs(m,a);if(e)return e;
        if(!u32(a[NL80211_ATTR_IFINDEX])||!u32(a[NL80211_ATTR_WIPHY])||!u32(a[NL80211_ATTR_IFTYPE])||!a[NL80211_ATTR_IFNAME])return 0;
        auto* n=static_cast<const char*>(nla_data(a[NL80211_ATTR_IFNAME]));int length=nla_len(a[NL80211_ATTR_IFNAME]);
        if(length<=1||length>IFNAMSIZ||n[length-1]!=0)return -EBADMSG;
        Interface i;i.index=nla_get_u32(a[NL80211_ATTR_IFINDEX]);i.phy=nla_get_u32(a[NL80211_ATTR_WIPHY]);i.type=nla_get_u32(a[NL80211_ATTR_IFTYPE]);i.name=n;
        if(!safeName(i.name)||!i.index)return -EBADMSG;found.push_back(i);return 0;
    });
    if(!error)out=std::move(found);return error;
}
int physicalRadio(unsigned index, Phy& out) {
    Phy found;found.index=index;bool seen=false;
    int error=transfer(NL80211_CMD_GET_WIPHY,true,[](nl_msg* m){return nla_put_flag(m,NL80211_ATTR_SPLIT_WIPHY_DUMP)<0?-ENOMEM:0;},[&](nl_msg* m){
        Attrs a;int e=parseAttrs(m,a);if(e)return e;
        if(!u32(a[NL80211_ATTR_WIPHY])||nla_get_u32(a[NL80211_ATTR_WIPHY])!=index)return 0;seen=true;
        if(a[NL80211_ATTR_SUPPORTED_IFTYPES]&&(e=nestedTypes(a[NL80211_ATTR_SUPPORTED_IFTYPES],found.types)))return e;
        if(a[NL80211_ATTR_CIPHER_SUITES]&&(e=arrayU32(a[NL80211_ATTR_CIPHER_SUITES],found.ciphers)))return e;
        if(a[NL80211_ATTR_AKM_SUITES]&&(e=arrayU32(a[NL80211_ATTR_AKM_SUITES],found.akms)))return e;
        if(a[NL80211_ATTR_EXT_FEATURES]){auto* p=static_cast<unsigned char*>(nla_data(a[NL80211_ATTR_EXT_FEATURES]));found.extendedFeatures.assign(p,p+nla_len(a[NL80211_ATTR_EXT_FEATURES]));}
        if(a[NL80211_ATTR_WIPHY_BANDS]){
            nlattr* band;int left;nla_for_each_nested(band,a[NL80211_ATTR_WIPHY_BANDS],left){
                nlattr* b[NL80211_BAND_ATTR_MAX+1]{};if(nla_parse_nested(b,NL80211_BAND_ATTR_MAX,band,nullptr)<0)return -EBADMSG;
                if(!b[NL80211_BAND_ATTR_FREQS])continue;
                nlattr* freq;int remain;nla_for_each_nested(freq,b[NL80211_BAND_ATTR_FREQS],remain){
                    nlattr* f[NL80211_FREQUENCY_ATTR_MAX+1]{};if(nla_parse_nested(f,NL80211_FREQUENCY_ATTR_MAX,freq,nullptr)<0)return -EBADMSG;
                    if(!u32(f[NL80211_FREQUENCY_ATTR_FREQ]))return -EBADMSG;
                    Channel c;c.mhz=nla_get_u32(f[NL80211_FREQUENCY_ATTR_FREQ]);c.disabled=f[NL80211_FREQUENCY_ATTR_DISABLED];c.noInitiate=f[NL80211_FREQUENCY_ATTR_NO_IR];c.radar=f[NL80211_FREQUENCY_ATTR_RADAR];found.channels.push_back(c);
                }if(remain)return -EBADMSG;
            }if(left)return -EBADMSG;
        }
        if(a[NL80211_ATTR_INTERFACE_COMBINATIONS]){
            nlattr* combo;int left;nla_for_each_nested(combo,a[NL80211_ATTR_INTERFACE_COMBINATIONS],left){
                nlattr* c[MAX_NL80211_IFACE_COMB+1]{};if(nla_parse_nested(c,MAX_NL80211_IFACE_COMB,combo,nullptr)<0)return -EBADMSG;
                if(!u32(c[NL80211_IFACE_COMB_MAXNUM])||!u32(c[NL80211_IFACE_COMB_NUM_CHANNELS])||!c[NL80211_IFACE_COMB_LIMITS])return -EBADMSG;
                Combination combination;combination.maximum=nla_get_u32(c[NL80211_IFACE_COMB_MAXNUM]);combination.channels=nla_get_u32(c[NL80211_IFACE_COMB_NUM_CHANNELS]);
                nlattr* limit;int remain;nla_for_each_nested(limit,c[NL80211_IFACE_COMB_LIMITS],remain){
                    nlattr* l[MAX_NL80211_IFACE_LIMIT+1]{};if(nla_parse_nested(l,MAX_NL80211_IFACE_LIMIT,limit,nullptr)<0)return -EBADMSG;
                    if(!u32(l[NL80211_IFACE_LIMIT_MAX])||!l[NL80211_IFACE_LIMIT_TYPES])return -EBADMSG;
                    Limit item;item.maximum=nla_get_u32(l[NL80211_IFACE_LIMIT_MAX]);if(nestedTypes(l[NL80211_IFACE_LIMIT_TYPES],item.types))return -EBADMSG;combination.limits.push_back(item);
                }if(remain)return -EBADMSG;found.combinations.push_back(combination);
            }if(left)return -EBADMSG;
        }
        return 0;
    });
    if(error)return error;if(!seen||!found.types)return -ENODEV;out=std::move(found);return 0;
}
int nativeRadio(Interface& primary,Phy& phy) {
    std::vector<Interface> all;int error=interfaces(all);if(error)return error;unsigned count=0;
    for(const auto& i:all){
        if(i.type!=NL80211_IFTYPE_STATION)continue;
        // Ask the kernel for the bound driver through the existing network
        // owner API; traversing platform sysfs is unnecessary.
        int fd=socket(AF_INET,SOCK_DGRAM|SOCK_CLOEXEC,0);if(fd<0)return -errno;
        ifreq request{};memcpy(request.ifr_name,i.name.c_str(),i.name.size()+1);
        ethtool_drvinfo driver{};driver.cmd=ETHTOOL_GDRVINFO;request.ifr_data=reinterpret_cast<char*>(&driver);
        int result=ioctl(fd,SIOCETHTOOL,&request);int saved=errno;close(fd);
        if(result<0){if(saved==EACCES||saved==EPERM)return -saved;continue;}
        if(strnlen(driver.driver,sizeof(driver.driver))==sizeof(driver.driver)||strcmp(driver.driver,"brcmfmac"))continue;
        primary=i;++count;
    }
    if(count!=1)return -ENODEV;return physicalRadio(primary.phy,phy);
}
int createInterface(unsigned phy,const std::string& name,unsigned type) {
    if(!safeName(name))return -EINVAL;
    return transfer(NL80211_CMD_NEW_INTERFACE,false,[&](nl_msg* m){if(addU32(m,NL80211_ATTR_WIPHY,phy)||addU32(m,NL80211_ATTR_IFTYPE,type)||nla_put_string(m,NL80211_ATTR_IFNAME,name.c_str())<0)return -ENOMEM;return 0;});
}
int deleteInterface(unsigned index) { if(!index)return -EINVAL;return transfer(NL80211_CMD_DEL_INTERFACE,false,[&](nl_msg* m){return addU32(m,NL80211_ATTR_IFINDEX,index);}); }
int setCountry(const char country[2]) {
    if(!country||country[0]<'A'||country[0]>'Z'||country[1]<'A'||country[1]>'Z')return -EINVAL;
    char code[]={country[0],country[1],0};return transfer(NL80211_CMD_REQ_SET_REG,false,[&](nl_msg* m){return nla_put_string(m,NL80211_ATTR_REG_ALPHA2,code)<0?-ENOMEM:0;});
}
int setInterfaceUp(const std::string& name,bool up) {
    if(!safeName(name))return -EINVAL;int fd=socket(AF_INET,SOCK_DGRAM|SOCK_CLOEXEC,0);if(fd<0)return -errno;
    ifreq request{};memcpy(request.ifr_name,name.c_str(),name.size()+1);
    int error=ioctl(fd,SIOCGIFFLAGS,&request)<0?-errno:0;
    if(!error){request.ifr_flags=up?(request.ifr_flags|IFF_UP):(request.ifr_flags&~IFF_UP);if(ioctl(fd,SIOCSIFFLAGS,&request)<0)error=-errno;}
    close(fd);return error;
}
}
