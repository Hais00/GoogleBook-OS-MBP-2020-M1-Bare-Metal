// SPDX-License-Identifier: Apache-2.0
// Ordered configfs/FunctionFS setup follows the production Pixel USB model.
// Controller selection and readbacks use the actual mainline Linux ABI.
#include "usb_linux_gadget.h"
#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <dirent.h>
#include <fcntl.h>
#include <limits.h>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>

namespace googlebook::usb {
namespace {
bool directory(const std::string& path) { struct stat st; return stat(path.c_str(),&st)==0 && S_ISDIR(st.st_mode); }
bool canonical(const std::string& path,std::string* value) {
    char result[PATH_MAX]; if (!realpath(path.c_str(),result)) return false; *value=result; return true;
}
}
Gadget::Gadget(GadgetPaths paths,std::string ffs,GadgetBinding::Writer writer)
    : paths_(std::move(paths)),ffs_(std::move(ffs)),writer_(std::move(writer)),binding_(paths_,writer_) {}

bool Gadget::configuration(uint64_t functions,FunctionConfig* out) {
    *out={}; out->functions=functions;
    const bool adb=functions & function::Adb;
    switch (functions & ~function::Adb) {
      case 0:
        out->product=0x4ee7; out->description=adb?"adb":"none"; break;
      case function::Mtp:
        out->product=adb?0x4ee2:0x4ee1; out->description="mtp";out->instances={"ffs.mtp"};break;
      case function::Ptp:
        out->product=adb?0x4ee6:0x4ee5;out->description="ptp";out->instances={"ffs.ptp"};break;
      case function::Rndis:
        out->product=adb?0x4ee4:0x4ee3;out->network=true;out->description="rndis";out->instances={"rndis.gs4"};break;
      case function::Ncm:
        out->product=adb?0x4eec:0x4eeb;out->network=true;out->description="ncm";out->instances={"ncm.gs6"};break;
      default:return false;
    }
    if (adb) { out->instances.push_back("ffs.adb"); if(out->description!="adb")out->description+="_adb"; }
    return true;
}
bool Gadget::read(const std::string& path,std::string* value) const {
    int fd=open(path.c_str(),O_RDONLY|O_CLOEXEC);if(fd<0)return false;
    char data[2048];ssize_t count;
    do {count=::read(fd,data,sizeof(data));}while(count<0 && errno==EINTR);
    int error=errno;close(fd);errno=error;
    if(count<0 || count==static_cast<ssize_t>(sizeof(data)))return false;
    value->assign(data,count);
    while(!value->empty() && (value->back()=='\n' || value->back()=='\r'))value->pop_back();
    return true;
}
bool Gadget::write(const std::string& path,const std::string& value) const {
    if(writer_)return writer_(path,value);
    int fd=open(path.c_str(),O_WRONLY|O_CLOEXEC|O_TRUNC);if(fd<0)return false;
    ssize_t count;do{count=::write(fd,value.data(),value.size());}while(count<0&&errno==EINTR);
    int error=errno,closed=close(fd);errno=error;
    return count==static_cast<ssize_t>(value.size()) && closed==0;
}
bool Gadget::integer(const std::string& path,unsigned expected) const {
    std::string text;if(!read(path,&text) || text.empty())return false;
    char* end=nullptr;errno=0;unsigned long value=strtoul(text.c_str(),&end,0);
    return !errno && end==text.c_str()+text.size() && value==expected;
}
bool Gadget::links(std::vector<std::string>* names) const {
    names->clear();const std::string config=paths_.gadget+"/configs/b.1";
    DIR* dir=opendir(config.c_str());if(!dir)return false;
    std::string functions;
    if(!canonical(paths_.gadget+"/functions",&functions)){closedir(dir);return false;}
    errno=0;
    while(auto* entry=readdir(dir)) {
        if(std::string(entry->d_name)=="." || std::string(entry->d_name)=="..")continue;
        std::string path=config+"/"+entry->d_name;struct stat st;
        if(lstat(path.c_str(),&st)){closedir(dir);return false;}
        if(S_ISLNK(st.st_mode)) {
            std::string target;
            if(!canonical(path,&target) || target.compare(0,functions.size()+1,functions+"/")!=0) {
                closedir(dir);return false;
            }
            std::string name=target.substr(functions.size()+1);
            if(!GadgetBinding::validName(name)){closedir(dir);return false;}
            names->push_back(name);
        }
        errno=0;
    }
    int error=errno;closedir(dir);if(error)return false;
    std::sort(names->begin(),names->end());
    return std::adjacent_find(names->begin(),names->end())==names->end();
}
bool Gadget::clearLinks() const {
    std::vector<std::string> checked;if(!links(&checked))return false;
    const std::string root=paths_.gadget+"/configs/b.1";
    DIR* dir=opendir(root.c_str());if(!dir)return false;
    bool ok=true;errno=0;
    while(auto* entry=readdir(dir)) {
        if(std::string(entry->d_name)=="." || std::string(entry->d_name)=="..")continue;
        const std::string path=root+"/"+entry->d_name;struct stat st;
        if(lstat(path.c_str(),&st)){ok=false;break;}
        if(S_ISLNK(st.st_mode) && unlink(path.c_str())){ok=false;break;}
        errno=0;
    }
    int error=errno;closedir(dir);return ok && !error;
}
bool Gadget::installLinks(const FunctionConfig& config) const {
    for(size_t i=0;i<config.instances.size();++i) {
        std::string target;
        if(!canonical(paths_.gadget+"/functions/"+config.instances[i],&target) ||
           symlink(target.c_str(),(paths_.gadget+"/configs/b.1/f"+std::to_string(i+1)).c_str()))return false;
    }
    std::vector<std::string> actual,expected=config.instances;
    std::sort(expected.begin(),expected.end());
    return links(&actual) && actual==expected;
}
bool Gadget::endpointsReady(const FunctionConfig& config) const {
    for(const auto& name:config.instances) {
        if(name.compare(0,4,"ffs.")!=0)continue;
        std::string ready;
        // This is the FunctionFS kernel's descriptor-ready bit, not a
        // synthetic property or merely a surviving endpoint filename.
        if(!read(paths_.gadget+"/functions/"+name+"/ready",&ready) || ready!="1")return false;
        const auto base=ffs_+"/"+name.substr(4);
        if(!paths_.filesystemFixture && !isKernelFilesystem(base,0x0a647361))return false;
        unsigned endpoints=name=="ffs.adb"?2:3;
        for(unsigned i=1;i<=endpoints;++i)
            if(access((base+"/ep"+std::to_string(i)).c_str(),R_OK|W_OK))return false;
    }
    return true;
}
GadgetResult Gadget::observe(GadgetState* state) const {
    *state={};GadgetState observed;std::vector<std::string> names;if(!links(&names))return GadgetResult::IoError;
    for(const auto& name:names) {
        uint64_t bit=name=="ffs.adb"?function::Adb:name=="ffs.mtp"?function::Mtp:
                     name=="ffs.ptp"?function::Ptp:name=="rndis.gs4"?function::Rndis:
                     name=="ncm.gs6"?function::Ncm:0;
        if(!bit || (observed.functions&bit))return GadgetResult::Unsupported;
        observed.functions|=bit;
    }
    FunctionConfig config;if(!configuration(observed.functions,&config))return GadgetResult::Unsupported;
    std::string current;if(binding_.current(&current)!=BindingResult::Ok)return GadgetResult::IoError;
    if(!observed.functions){observed.applied=current.empty();*state=observed;return GadgetResult::Ok;}
    std::string verified;
    bool ffs=false;for(const auto& name:config.instances)if(name.compare(0,4,"ffs.")==0)ffs=true;
    std::string description;
    observed.applied=!current.empty() && binding_.discover(&verified,current)==BindingResult::Ok &&
                   integer(paths_.gadget+"/idVendor",0x18d1) && integer(paths_.gadget+"/idProduct",config.product) &&
                   integer(paths_.gadget+"/bDeviceClass",config.network?0xef:0) &&
                   integer(paths_.gadget+"/bDeviceSubClass",config.network?2:0) &&
                   integer(paths_.gadget+"/bDeviceProtocol",config.network?1:0) &&
                   integer(paths_.gadget+"/os_desc/use",ffs?1:0) &&
                   read(paths_.gadget+"/configs/b.1/strings/0x409/configuration",&description) &&
                   description==config.description &&
                   endpointsReady(config);
    *state=observed;
    return GadgetResult::Ok;
}
GadgetResult Gadget::waitAndBind(const FunctionConfig& config,std::chrono::milliseconds timeout) {
    const auto deadline=std::chrono::steady_clock::now()+timeout;
    do {
        if(endpointsReady(config)) {
            if(binding_.bind(controller_)!=BindingResult::Ok)return GadgetResult::IoError;
            GadgetState state;
            return observe(&state)==GadgetResult::Ok && state.functions==config.functions && state.applied?
                   GadgetResult::Ok:GadgetResult::IoError;
        }
        if(std::chrono::steady_clock::now()>=deadline)break;
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }while(true);
    return GadgetResult::NotReady;
}
GadgetResult Gadget::apply(uint64_t functions,std::chrono::milliseconds timeout) {
    FunctionConfig config;
    if(timeout.count()<0 || timeout>std::chrono::seconds(30))return GadgetResult::Invalid;
    if(!configuration(functions,&config))return GadgetResult::Unsupported;
    if(functions) {
        if(binding_.discover(&controller_)!=BindingResult::Ok)return GadgetResult::NotReady;
        for(const auto& name:config.instances)
            if(!directory(paths_.gadget+"/functions/"+name))return GadgetResult::Unsupported;
    }
    live_=false;
    if(binding_.unbind()!=BindingResult::Ok || !clearLinks())return GadgetResult::IoError;
    desired_=functions;
    if(!functions) {
        GadgetState state;return observe(&state)==GadgetResult::Ok && state.applied?GadgetResult::Ok:GadgetResult::IoError;
    }
    char product[16];snprintf(product,sizeof(product),"0x%04x",config.product);
    bool ffs=false;for(const auto& n:config.instances)if(n.compare(0,4,"ffs.")==0)ffs=true;
    if(!write(paths_.gadget+"/idVendor","0x18d1") || !write(paths_.gadget+"/idProduct",product) ||
       !write(paths_.gadget+"/bDeviceClass",config.network?"0xef":"0") ||
       !write(paths_.gadget+"/bDeviceSubClass",config.network?"2":"0") ||
       !write(paths_.gadget+"/bDeviceProtocol",config.network?"1":"0") ||
       !write(paths_.gadget+"/os_desc/use",ffs?"1":"0") ||
       !write(paths_.gadget+"/configs/b.1/strings/0x409/configuration",config.description) || !installLinks(config)) {
        binding_.unbind();clearLinks();return GadgetResult::IoError;
    }
    auto result=waitAndBind(config,timeout);
    if(result!=GadgetResult::Ok){binding_.unbind();clearLinks();return result;}
    live_=true;return GadgetResult::Ok;
}
GadgetResult Gadget::reset(std::chrono::milliseconds timeout) {
    GadgetState state;
    if(timeout.count()<0 || timeout>std::chrono::seconds(30))return GadgetResult::Invalid;
    if(observe(&state)!=GadgetResult::Ok || !state.functions || !state.applied)return GadgetResult::NotReady;
    FunctionConfig config;configuration(state.functions,&config);
    if(binding_.discover(&controller_)!=BindingResult::Ok)return GadgetResult::NotReady;
    live_=false;
    if(binding_.unbind()!=BindingResult::Ok)return GadgetResult::IoError;
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    auto result=waitAndBind(config,timeout);live_=result==GadgetResult::Ok;
    if(live_)desired_=state.functions;
    return result;
}
GadgetResult Gadget::adopt() {
    GadgetState state;
    if(observe(&state)!=GadgetResult::Ok || !state.applied)return GadgetResult::NotReady;
    if(state.functions && binding_.current(&controller_)!=BindingResult::Ok)return GadgetResult::IoError;
    desired_=state.functions;live_=state.functions!=0;
    return GadgetResult::Ok;
}
GadgetResult Gadget::reconcile() {
    if(!live_ || !desired_)return GadgetResult::Ok;
    FunctionConfig config;if(!configuration(desired_,&config)){live_=false;return GadgetResult::Invalid;}
    GadgetState state;
    if(observe(&state)!=GadgetResult::Ok || state.functions!=desired_){live_=false;return GadgetResult::IoError;}
    if(!endpointsReady(config)) {
        return binding_.unbind()==BindingResult::Ok?GadgetResult::NotReady:GadgetResult::IoError;
    }
    if(!state.applied)return waitAndBind(config,std::chrono::milliseconds(0));
    return GadgetResult::Ok;
}
}  // namespace googlebook::usb
