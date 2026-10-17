// Execute a tiny ARM64 guest to distinguish KVM problems from Trusty setup.
#include <errno.h>
#include <fcntl.h>
#include <linux/kvm.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

static void finish(int failed, const char* step) {
    printf("KVM_EXECUTION_%s: %s (errno=%d %s)\n", failed ? "FAIL" : "PASS",
           step, failed ? errno : 0, failed ? strerror(errno) : "OK");
    fflush(stdout); reboot(RB_POWER_OFF); for (;;) pause();
}
static void require(int result, const char* step) {
    if (result < 0) finish(1, step);
    printf("KVM_STEP: %s\n", step); fflush(stdout);
}
static void setreg(int vcpu, uint64_t id, uint64_t value) {
    struct kvm_one_reg reg = {.id=id, .addr=(uintptr_t)&value};
    require(ioctl(vcpu, KVM_SET_ONE_REG, &reg), "set core register");
}
static void timeout(int sig) { (void)sig; errno=ETIMEDOUT; finish(1, "KVM_RUN timed out"); }
int main(void) {
    mkdir("/sys",0755); mount("sysfs","/sys","sysfs",0,NULL);
    unsigned major, minor; FILE* f=fopen("/sys/class/misc/kvm/dev","r");
    if (!f || fscanf(f,"%u:%u",&major,&minor)!=2) finish(1,"KVM device absent");
    fclose(f); mknod("/dev/kvm",S_IFCHR|0600,makedev(major,minor));
    int kvm=open("/dev/kvm",O_RDWR); require(kvm,"open KVM");
    int vm=ioctl(kvm,KVM_CREATE_VM,0); require(vm,"create VM");
    size_t size=64*1024;
    void* memory=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if (memory==MAP_FAILED) finish(1,"guest memory");
    uint32_t code[]={0xd2824680,0xd2820001,0xb9000020,0x14000000};
    memcpy(memory,code,sizeof(code));
    struct kvm_userspace_memory_region region={.slot=0,.guest_phys_addr=0x40000000,
        .memory_size=size,.userspace_addr=(uintptr_t)memory};
    require(ioctl(vm,KVM_SET_USER_MEMORY_REGION,&region),"map guest RAM");
    struct kvm_vcpu_init init={0};
    require(ioctl(vm,KVM_ARM_PREFERRED_TARGET,&init),"get ARM target");
    int vcpu=ioctl(vm,KVM_CREATE_VCPU,0); require(vcpu,"create VCPU");
    require(ioctl(vcpu,KVM_ARM_VCPU_INIT,&init),"initialize VCPU");
    struct kvm_create_device gic={.type=KVM_DEV_TYPE_ARM_VGIC_V3};
    require(ioctl(vm,KVM_CREATE_DEVICE,&gic),"create GICv3");
    uint64_t dist=0x08000000,redist=0x080a0000;
    struct kvm_device_attr attr={.group=KVM_DEV_ARM_VGIC_GRP_ADDR,
        .attr=KVM_VGIC_V3_ADDR_TYPE_DIST,.addr=(uintptr_t)&dist};
    require(ioctl(gic.fd,KVM_SET_DEVICE_ATTR,&attr),"GIC distributor");
    attr.attr=KVM_VGIC_V3_ADDR_TYPE_REDIST; attr.addr=(uintptr_t)&redist;
    require(ioctl(gic.fd,KVM_SET_DEVICE_ATTR,&attr),"GIC redistributor");
    attr.group=KVM_DEV_ARM_VGIC_GRP_CTRL;attr.attr=KVM_DEV_ARM_VGIC_CTRL_INIT;attr.addr=0;
    require(ioctl(gic.fd,KVM_SET_DEVICE_ATTR,&attr),"initialize GIC");
    setreg(vcpu,KVM_REG_ARM64|KVM_REG_SIZE_U64|KVM_REG_ARM_CORE|KVM_REG_ARM_CORE_REG(regs.pc),0x40000000);
    setreg(vcpu,KVM_REG_ARM64|KVM_REG_SIZE_U64|KVM_REG_ARM_CORE|KVM_REG_ARM_CORE_REG(regs.pstate),0x3c5);
    int map_size=ioctl(kvm,KVM_GET_VCPU_MMAP_SIZE,0); require(map_size,"VCPU mmap size");
    struct kvm_run* run=mmap(NULL,map_size,PROT_READ|PROT_WRITE,MAP_SHARED,vcpu,0);
    if (run==MAP_FAILED) finish(1,"map KVM run structure");
    signal(SIGALRM,timeout); alarm(5);
    require(ioctl(vcpu,KVM_RUN,0),"execute guest instructions"); alarm(0);
    uint32_t value=0; memcpy(&value,run->mmio.data,sizeof(value));
    printf("KVM_EXIT: reason=%u address=%llx write=%u len=%u value=%x\n",
        run->exit_reason,(unsigned long long)run->mmio.phys_addr,run->mmio.is_write,run->mmio.len,value);
    if (run->exit_reason!=KVM_EXIT_MMIO || run->mmio.phys_addr!=0x1000 ||
        !run->mmio.is_write || run->mmio.len!=4 || value!=0x1234) finish(1,"unexpected guest exit");
    finish(0,"ARM64 guest executed and wrote expected MMIO value");
}
