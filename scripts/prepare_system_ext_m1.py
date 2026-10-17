#!/usr/bin/env python3
"""Adapt the platform init definitions while preserving original Android xattrs."""
import ctypes
import argparse
import json
import pathlib
import stat
import shutil
import subprocess
from apple_graphics_policy import graphics_cil

ORIGINAL = pathlib.Path('/opt/googlebook/build/system-ext-original')
WORK = pathlib.Path('/opt/googlebook/build/system-ext-work')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--debug-console', action='store_true',
                        help='Enable only the Trusty launcher console permissions for this diagnostic image')
    parser.add_argument('--trace-vm', action='store_true', help='Trace only this VM launcher and its children in the diagnostic image')
    keymint_mode = parser.add_mutually_exclusive_group()
    keymint_mode.add_argument('--keymint-tipc', action='store_true',
                        help='Diagnose the provided nonsecure KeyMint HAL over the VM TIPC bridge')
    keymint_mode.add_argument('--software-keymint', action='store_true',
                             help='Use the original AOSP software crypto backend, reporting SOFTWARE security')
    parser.add_argument('--one-cpu', action='store_true',
                        help='Diagnose the Trusty guest with a single vCPU')
    parser.add_argument('--software-vulkan', action='store_true',
                        help='Allow only boot animation to execute private shader JIT memory for the bundled CPU renderer')
    args = parser.parse_args()
    if args.trace_vm:
        args.debug_console = True
    assert ORIGINAL.is_dir()
    if not WORK.exists():
        subprocess.run(['/bin/cp', '-a', '-c', str(ORIGINAL), str(WORK)], check=True)
    probe = pathlib.Path('/opt/googlebook/build/graphics-out/googlebook-vkprobe')
    if probe.exists():
        shutil.copy2(probe, WORK/'bin/googlebook-vkprobe')
    label_probe = pathlib.Path('/opt/googlebook/build/graphics-out/googlebook-labelprobe')
    if label_probe.exists():
        shutil.copy2(label_probe, WORK/'bin/googlebook-labelprobe')
    native_probe = pathlib.Path('/opt/googlebook/build/graphics-out/googlebook-native-vkprobe')
    if native_probe.exists():
        shutil.copy2(native_probe, WORK/'bin/googlebook-native-vkprobe')
        (WORK/'etc/init/googlebook-gpu-probe.rc').write_text('''# One real GPU job, opt-in development capture, original GPU-service domain.
service googlebook.gpu-probe /system_ext/bin/googlebook-native-vkprobe /vendor/lib64/hw/vulkan.asahi.so
    class core
    user gpu_service
    group graphics
    disabled
    oneshot
    timeout_period 25

on boot && property:ro.boot.googlebook.debug=1 && property:ro.hardware.vulkan=asahi
    start googlebook.gpu-probe
''')
    props_rel = 'etc/build.prop'
    props = [line for line in (ORIGINAL/props_rel).read_text().splitlines()
             if not line.startswith('ro.logd.size=')]
    (WORK/props_rel).write_text('\n'.join(props)+'\nro.logd.size=16M\n')
    rel = 'etc/init/desktop-trusty_security_vm_launcher.rc'
    # Route lazy RPC accessors to the supported VM too; the OEM file assigns
    # them only to the protected launcher, which is not present on this board.
    services = json.loads((ORIGINAL/'etc/vm/trusty_vm/desktop-security_vm_rpc_services.json').read_text())
    interfaces = ''.join('    interface aidl '+s['accessor_name']+'\n' for s in services)
    content = '''# GoogleBook M1 non-protected Trusty VM and its original RPC services.
service trusty_security_vm_launcher /system_ext/bin/trusty_security_vm_launcher --kernel /system_ext/etc/vm/trusty_vm/desktop_trusty_ext_boot_signed.elf --memory-size-mib 200 --cpu-topology match-host --rpc-services-config /system_ext/etc/vm/trusty_vm/desktop-security_vm_rpc_services.json --vm-instance-id /system_ext/etc/vm/trusty_vm/desktop_trusty_security_vm_instance_id --disable-secretkeeper
    disabled
    user system
    group system virtualmachine
    capabilities IPC_LOCK NET_BIND_SERVICE SYS_RESOURCE SYS_NICE
    stdio_to_kmsg
''' + interfaces + '''
on init && property:trusty.security_vm.enabled=1 && property:ro.boot.hypervisor.protected_vm.supported=0
    setprop trusty.security_vm.nonsecure_vm_ready 1
    setprop trusty.security_vm.vm_cid 200
    start trusty_security_vm_launcher
'''
    tracer = WORK/'bin/googlebook-strace'
    if args.trace_vm:
        shutil.copy2('/opt/googlebook/build/strace-android-build/src/strace', tracer)
        tracer.chmod(0o755)
        content = content.replace(
            'service trusty_security_vm_launcher /system_ext/bin/trusty_security_vm_launcher ',
            'service trusty_security_vm_launcher /system_ext/bin/googlebook-strace -f -tt -s 80 -e kvm=vcpu+ -e trace=ioctl /system_ext/bin/trusty_security_vm_launcher ', 1)
        content = content.replace('capabilities IPC_LOCK NET_BIND_SERVICE SYS_RESOURCE SYS_NICE',
                                  'capabilities IPC_LOCK NET_BIND_SERVICE SYS_RESOURCE SYS_NICE SYS_PTRACE', 1)
    elif tracer.exists():
        tracer.unlink()
    # Development capture: the user build does not create /dev/kmsg_debug,
    # so stdio_to_kmsg would silently discard this VM's console and stderr.
    # Keep non-TTY stdio, matching the original service. The diagnostic board
    # action below provides the debug log endpoint on this user build.
    content += '''
# M1 non-protected VM profile, using the original RPC and TIPC endpoints.
on init && property:trusty.security_vm.enabled=1 && property:ro.boot.hypervisor.protected_vm.supported=0
    setprop trusty.security_vm.keymint.enabled 1
    setprop ro.hardware.trusty_ipc_dev.gatekeeper VSOCK:200:0
    setprop storageproxyd_system.trusty_ipc_dev VSOCK:200:0
'''
    (WORK/rel).write_text(content)
    if args.one_cpu:
        (WORK/rel).write_text(content.replace('--cpu-topology match-host', '--cpu-topology one-cpu'))
    storage_rel='etc/init/rpmb_dev.desktop.system.rc'
    storage=(ORIGINAL/storage_rel).read_text()
    storage=storage.replace('property:ro.boot.boot_source=internal','property:ro.boot.hypervisor.protected_vm.supported=1')
    storage=storage.replace('property:ro.boot.boot_source=external','property:ro.boot.hypervisor.protected_vm.supported=0')
    storage=storage.replace('/dev/block/by-name/desktop_security_','/dev/block/mapper/desktop_security_')
    (WORK/storage_rel).write_text(storage)
    km_binary = 'bin/hw/android.hardware.security.keymint-service.trusty_system_vm'
    km_rc = 'etc/init/android.hardware.security.keymint-service.desktop_trusty_system_vm.rc'
    manifest_rel = 'etc/vintf/manifest.xml'
    manifest = (ORIGINAL/manifest_rel).read_text()
    if args.keymint_tipc or args.software_keymint:
        binary = ('/opt/googlebook/build/graphics-out/android.hardware.security.keymint-service.googlebook-software'
                  if args.software_keymint else
                  '/opt/googlebook/build/vendor-original/bin/hw/android.hardware.security.keymint-service.trusty_tee.nonsecure')
        shutil.copy2(binary, WORK/km_binary)
        rc = (ORIGINAL/km_rc).read_text().replace('--skip-hal shared-secret',
                     '' if args.software_keymint else '--dev VSOCK:200:0')
        (WORK/km_rc).write_text(rc)
        # This HAL exposes shared-secret/default itself; remove the protected
        # VM accessor rather than declaring an unavailable second provider.
        import re
        manifest = re.sub(r'<hal format="aidl" exclusive-to="virtual-machine">\s*'
                          r'<name>android.hardware.security.sharedsecret</name>.*?</hal>',
                          '<hal format="aidl"><name>android.hardware.security.sharedsecret</name>'
                          '<fqname>ISharedSecret/default</fqname></hal>', manifest, flags=re.S)
    else:
        shutil.copy2(ORIGINAL/km_binary, WORK/km_binary)
        shutil.copy2(ORIGINAL/km_rc, WORK/km_rc)
    (WORK/manifest_rel).write_text(manifest)
    (WORK/'etc/init/googlebook-board.rc').write_text('''# This Apple board has no Google TPM-backed GSC.
service android.system.desktop.security.gscd /system/bin/gscd
    override
    class early_hal
    user hsm
    group hsm
    disabled

# Retain early Android diagnostics across noisy hardware-service retries.
on property:ro.persistent_properties.ready=true
    setprop persist.logd.size 16M
    start logd-reinit
''')
    if args.debug_console:
        with (WORK/'etc/init/googlebook-board.rc').open('a') as out:
            out.write('''
on early-init && property:ro.boot.googlebook.debug=1
    symlink /dev/kmsg /dev/kmsg_debug
''')
    cil_rel = 'etc/selinux/system_ext_sepolicy.cil'
    policy = (ORIGINAL/cil_rel).read_text()
    policy += graphics_cil()
    if args.software_vulkan:
        policy += '\n; The bundled software Vulkan driver compiles CPU shaders in boot animation.\n'
        policy += '(allow bootanim self (process (execmem)))\n'
    if args.keymint_tipc:
        # The stock RPC client inherits a connected socket from its accessor.
        # The nonsecure TIPC client must create its own VSOCK connection.
        policy += '\n(allow hal_keymint_system self (vsock_socket (read write create getattr setattr ioctl connect getopt setopt shutdown)))\n'
    if args.debug_console:
        policy += '\n; M1 diagnostic capture: only this VM launcher family may write its debug log.\n'
        for domain in ['trusty_security_vm_launcher', 'trusty_security_vm_launcher_early_virtmgr',
                       'trusty_security_vm_launcher_early_virtmgr_crosvm']:
            policy += f'(allow {domain} kmsg_device (chr_file (write open getattr ioctl)))\n'
    if args.trace_vm:
        policy += '(allow trusty_security_vm_launcher trusty_security_vm_launcher (capability (sys_ptrace)))\n'
        policy += '(allow trusty_security_vm_launcher trusty_security_vm_launcher_exec (file (read open getattr map execute execute_no_trans)))\n'
        for domain in ['trusty_security_vm_launcher', 'trusty_security_vm_launcher_early_virtmgr',
                       'trusty_security_vm_launcher_early_virtmgr_crosvm']:
            policy += f'(allow trusty_security_vm_launcher {domain} (process (ptrace)))\n'
            policy += f'(allow trusty_security_vm_launcher {domain} (file (read open getattr)))\n'
            policy += f'(allow trusty_security_vm_launcher {domain} (dir (read open getattr search)))\n'
            policy += f'(allow trusty_security_vm_launcher {domain} (lnk_file (read getattr)))\n'
    (WORK/cil_rel).write_text(policy)
    lib = ctypes.CDLL('libSystem.B.dylib', use_errno=True)
    lib.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    lib.getxattr.restype = ctypes.c_ssize_t
    lib.setxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    lib.setxattr.restype = ctypes.c_int
    for target in [WORK] + list(WORK.rglob('*')):
        original = ORIGINAL/target.relative_to(WORK)
        for attr in ['security.selinux', 'security.capability']:
            buf = ctypes.create_string_buffer(4096)
            n = lib.getxattr(str(original).encode(), attr.encode(), buf, len(buf), 0, 1)
            if n < 0:
                if attr != 'security.selinux':
                    continue
                data = b'u:object_r:system_file:s0\0'
            else:
                data = buf.raw[:n]
            if attr == 'security.selinux' and target.relative_to(WORK).as_posix() in ['bin/googlebook-vkprobe', 'bin/googlebook-labelprobe']:
                data = b'u:object_r:shell_exec:s0\0'
            if attr == 'security.selinux' and target.relative_to(WORK).as_posix() == 'bin/googlebook-native-vkprobe':
                data = b'u:object_r:gpuservice_exec:s0\0'
            if attr == 'security.selinux' and target.relative_to(WORK).as_posix() == 'bin/googlebook-strace':
                data = b'u:object_r:trusty_security_vm_launcher_exec:s0\0'
            mode = stat.S_IMODE(target.lstat().st_mode)
            if not target.is_symlink():
                target.chmod(mode | stat.S_IWUSR)
            try:
                if lib.setxattr(str(target).encode(), attr.encode(), data, len(data), 0, 1):
                    raise OSError(ctypes.get_errno(), str(target))
            finally:
                if not target.is_symlink():
                    target.chmod(mode)
    print('Prepared system_ext platform init and preserved Android security labels.')


if __name__ == '__main__':
    main()
