// SPDX-License-Identifier: Apache-2.0
// Linux configfs/UDC ABI, adapted after reviewing production Pixel USB helpers.
#include "usb_linux_gadget_binding.h"
#include <algorithm>
#include <cerrno>
#include <cctype>
#include <dirent.h>
#include <fcntl.h>
#include <limits.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
#ifdef __linux__
#include <sys/vfs.h>
#endif

namespace googlebook::usb {
bool isKernelFilesystem(const std::string& path,unsigned magic) {
#ifdef __linux__
    struct statfs st;
    return statfs(path.c_str(),&st)==0 && static_cast<unsigned long>(st.f_type)==magic;
#else
    (void)path;(void)magic;return false;
#endif
}
GadgetBinding::GadgetBinding(GadgetPaths paths, Writer writer)
    : paths_(std::move(paths)), writer_(std::move(writer)) {}
bool GadgetBinding::validName(const std::string& name) {
    if (name.empty() || name.size()>255 || name=="." || name=="..") return false;
    for (unsigned char c : name)
        if (!std::isalnum(c) && c!='.' && c!='_' && c!='-' && c!=':') return false;
    return true;
}
bool GadgetBinding::eligible(const std::string& name) const {
    if (!validName(name)) return false;
    if(!paths_.filesystemFixture && !isKernelFilesystem(paths_.controllers,0x62656572))return false;
    char resolved[PATH_MAX];
    if (!realpath((paths_.controllers+"/"+name+"/device/driver").c_str(),resolved)) return false;
    std::string driver(resolved);
    auto slash=driver.find_last_of('/');
    // J293 uses the real DesignWare core. Never select dummy_udc merely
    // because it happens to be the first or only registered controller.
    return driver.substr(slash==std::string::npos?0:slash+1)=="dwc3";
}
BindingResult GadgetBinding::discover(std::string* controller,const std::string& preferred) const {
    controller->clear();
    if (!preferred.empty() && !validName(preferred)) return BindingResult::Invalid;
    if(!paths_.filesystemFixture && !isKernelFilesystem(paths_.controllers,0x62656572))return BindingResult::Unverified;
    DIR* directory=opendir(paths_.controllers.c_str());
    if (!directory) return errno==ENOENT?BindingResult::Missing:BindingResult::IoError;
    std::vector<std::string> found;
    errno=0;
    while (auto* entry=readdir(directory)) {
        if (eligible(entry->d_name)) found.emplace_back(entry->d_name);
        errno=0;
    }
    int error=errno; closedir(directory);
    if (error) return BindingResult::IoError;
    if (!preferred.empty()) {
        if (std::find(found.begin(),found.end(),preferred)==found.end()) return BindingResult::Unverified;
        *controller=preferred; return BindingResult::Ok;
    }
    if (found.empty()) return BindingResult::Missing;
    if (found.size()!=1) return BindingResult::Ambiguous;
    *controller=found[0]; return BindingResult::Ok;
}
bool GadgetBinding::read(const std::string& path,std::string* value) const {
    int fd=open(path.c_str(),O_RDONLY|O_CLOEXEC);
    if (fd<0) return false;
    char data[1025]; ssize_t count;
    do { count=::read(fd,data,sizeof(data)); } while(count<0 && errno==EINTR);
    int error=errno; close(fd); errno=error;
    if (count<0 || count==static_cast<ssize_t>(sizeof(data))) return false;
    value->assign(data,count);
    while (!value->empty() && std::isspace(static_cast<unsigned char>(value->back()))) value->pop_back();
    return true;
}
BindingResult GadgetBinding::current(std::string* controller) const {
    controller->clear();
    if(!paths_.filesystemFixture && !isKernelFilesystem(paths_.gadget,0x62656570))return BindingResult::Unverified;
    if (!read(paths_.gadget+"/UDC",controller)) return BindingResult::IoError;
    if (!controller->empty() && !validName(*controller)) return BindingResult::Invalid;
    return BindingResult::Ok;
}
bool GadgetBinding::write(const std::string& value) const {
    auto path=paths_.gadget+"/UDC";
    if (writer_) return writer_(path,value);
    int fd=open(path.c_str(),O_WRONLY|O_CLOEXEC|O_TRUNC);
    if (fd<0) return false;
    ssize_t count;
    do { count=::write(fd,value.data(),value.size()); } while (count<0 && errno==EINTR);
    int error=errno, closed=close(fd); errno=error;
    return count==static_cast<ssize_t>(value.size()) && closed==0;
}
BindingResult GadgetBinding::bind(const std::string& controller) {
    if (!validName(controller)) return BindingResult::Invalid;
    if (!eligible(controller)) return BindingResult::Unverified;
    std::string value; auto result=current(&value);
    if (result!=BindingResult::Ok) return result;
    if (value==controller) return BindingResult::Ok;
    if (!value.empty()) return BindingResult::Busy;
    if (!write(controller+"\n")) return BindingResult::IoError;
    return current(&value)==BindingResult::Ok && value==controller?BindingResult::Ok:BindingResult::IoError;
}
BindingResult GadgetBinding::unbind() {
    std::string value; auto result=current(&value);
    if (result!=BindingResult::Ok) return result;
    if (value.empty()) return BindingResult::Ok;
    // A nonempty write containing only newline reaches configfs' store
    // callback as an empty name. A zero-byte write would not disconnect it.
    if (!write("\n")) return BindingResult::IoError;
    return current(&value)==BindingResult::Ok && value.empty()?BindingResult::Ok:BindingResult::IoError;
}
BindingResult GadgetBinding::speed(std::string* value) const {
    value->clear(); std::string controller; auto result=current(&controller);
    if (result!=BindingResult::Ok) return result;
    if (controller.empty()) return BindingResult::Missing;
    if (!eligible(controller)) return BindingResult::Unverified;
    return read(paths_.controllers+"/"+controller+"/current_speed",value)?BindingResult::Ok:BindingResult::IoError;
}
}  // namespace googlebook::usb
