#!/usr/bin/env python3
"""Cross-build separate GPL Asahi speaker protector; never starts it or unlocks amps."""
import hashlib,json,os,shutil,subprocess
from pathlib import Path
from project_paths import BASE,WORK,NDK
SOURCE=WORK/'references/xerj-code/corpora/android-asahi-audio/speakersafetyd'
PIN='615674e75dc68639d550171e33ba3946538d03b0'
ROOT=Path('/opt/googlebook/kernel-build/speakersafetyd-android-615674e75dc6')
def main():
    assert subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()==PIN
    ROOT.mkdir(exist_ok=True)
    source=ROOT/'source'
    if not source.exists():shutil.copytree(SOURCE,source,ignore=shutil.ignore_patterns('.git','target'))
    # Android has no systemd /run directory. Keep the warm/cold-boot state in
    # an init-created tmpfs directory, recreated on each actual Linux boot.
    main=source/'src/main.rs'
    original=(SOURCE/'src/main.rs').read_text()
    updated=original.replace('"/run/speakersafetyd/speakersafetyd.flag"','"/dev/speakersafetyd/speakersafetyd.flag"')
    updated=updated.replace('/proc/device-tree/compatible','/sys/firmware/devicetree/base/compatible')
    assert updated!=original
    main.write_text(updated)
    patch=subprocess.run(['diff','-u',str(SOURCE/'src/main.rs'),str(main)],capture_output=True,text=True)
    assert patch.returncode==1
    (ROOT/'android-path.patch').write_text(patch.stdout)
    alsa=Path('/opt/googlebook/kernel-build/alsa-android-a47c8bc3fef1/stage/vendor')
    env=os.environ.copy()
    toolchain=Path.home()/'.rustup/toolchains/stable-aarch64-apple-darwin/bin'
    env['RUSTC']=str(toolchain/'rustc')
    env['PATH']=str(toolchain)+os.pathsep+env['PATH']
    env.update({'CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER':str(NDK/'bin/aarch64-linux-android35-clang'),
       'CC_aarch64_linux_android':str(NDK/'bin/aarch64-linux-android35-clang'),
       'AR_aarch64_linux_android':str(NDK/'bin/llvm-ar'),
       'PKG_CONFIG_ALLOW_CROSS':'1','PKG_CONFIG_LIBDIR':str(alsa/'lib64/pkgconfig'),
       'PKG_CONFIG_SYSROOT_DIR':str(alsa.parent),'CARGO_TARGET_DIR':str(ROOT/'target'),
       'CARGO_TARGET_AARCH64_LINUX_ANDROID_RUSTFLAGS':'-C link-arg=-Wl,-z,max-page-size=16384'})
    cmd=[str(toolchain/'cargo'),'build','--locked','--release','--target','aarch64-linux-android']
    with (ROOT/'build.log').open('w') as log:
        r=subprocess.run(cmd,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT)
    if r.returncode:raise RuntimeError((ROOT/'build.log').read_text()[-6000:])
    binary=ROOT/'target/aarch64-linux-android/release/speakersafetyd'
    receipt={'source':str(SOURCE),'commit':PIN,'license':'GPL-2.0-only; separate upstream derivative, source and COPYING retained',
      'binary':str(binary),'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
      'source_changes':{'src/main.rs':'FLAGFILE on /dev tmpfs and direct sysfs path to same DT compatible; same thermal model, ownership locks, V/I capture and timeout protocol'},
      'config':str(SOURCE/'conf/apple/j293.conf'),'physical_device_written':False,'amplifiers_unlocked':False,'hardware_tested':False,
      'command':cmd}
    (WORK/'speakersafetyd-android-build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('SPEAKERSAFETYD_ANDROID_BUILD_PASS',binary.stat().st_size)
if __name__=='__main__':main()
