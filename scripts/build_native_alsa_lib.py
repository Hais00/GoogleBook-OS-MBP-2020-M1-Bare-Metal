#!/usr/bin/env python3
"""Cross-build separate upstream ALSA-lib for Bionic, retaining real hw PCM/CTL APIs."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import struct
from project_paths import WORK, NDK


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', action='store_true', help='Repair the existing logged build without discarding it')
    parser.add_argument('--verify-built', action='store_true', help='Verify already installed artifacts without rebuilding')
    options = parser.parse_args()
    if options.verify_built:
        options.resume = True
    upstream = WORK/'references/xerj-code/corpora/alsa-native-userspace/alsa-lib'
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upstream, text=True).strip()
    root = Path('/opt/googlebook/kernel-build')/('alsa-android-'+commit[:12])
    assert options.resume == root.exists(), 'Existing build requires --resume; a fresh build must not use it'
    root.mkdir(exist_ok=options.resume)
    source, tools, build, stage = [root/x for x in ['source', 'tools', 'build', 'stage']]
    if not options.resume:
        shutil.copytree(upstream, source, ignore=shutil.ignore_patterns('.git'))
    for directory in [tools, build, stage]:
        directory.mkdir(exist_ok=options.resume)
    compiler = tools/'cc'
    compiler.write_text('#!/bin/sh\nexec '+shlex.quote(str(NDK/'bin/clang'))+
                        ' --target=aarch64-linux-android35 "$@"\n')
    compiler.chmod(0o755)
    # Libtool expands binutils command variables; use paths without spaces for
    # all tools, including the NDK installed under "GoogleBook OS".
    binutils = {'AR': 'llvm-ar', 'RANLIB': 'llvm-ranlib', 'STRIP': 'llvm-strip',
                'NM': 'llvm-nm', 'LD': 'ld.lld', 'OBJDUMP': 'llvm-objdump', 'READELF': 'llvm-readelf'}
    for key, tool in binutils.items():
        wrapper = tools/key.lower()
        wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(NDK/'bin'/tool))+' "$@"\n')
        wrapper.chmod(0o755)
    # Bionic provides pthreads and clock_gettime in libc. Detect real linkable
    # symbols before considering separate pthread/rt libraries; never cache a
    # fabricated configure success or silently disable thread safety/monotonic time.
    configure = source/'configure.ac'
    text = configure.read_text()
    edits = [
        ('AC_CHECK_LIB([pthread], [pthread_join], [HAVE_LIBPTHREAD="yes"])',
         'AC_SEARCH_LIBS([pthread_join], [pthread], [HAVE_LIBPTHREAD="yes"])'),
        ('ALSA_DEPLIBS="$ALSA_DEPLIBS -lpthread"',
         'if test "$ac_cv_search_pthread_join" != "none required"; then\n'
         '      ALSA_DEPLIBS="$ALSA_DEPLIBS $ac_cv_search_pthread_join"\n    fi'),
        ('AC_CHECK_LIB([rt], [clock_gettime], [HAVE_LIBRT="yes"])',
         'AC_SEARCH_LIBS([clock_gettime], [rt], [HAVE_LIBRT="yes"])'),
        ('ALSA_DEPLIBS="$ALSA_DEPLIBS -lrt"',
         'if test "$ac_cv_search_clock_gettime" != "none required"; then\n'
         '      ALSA_DEPLIBS="$ALSA_DEPLIBS $ac_cv_search_clock_gettime"\n    fi')]
    for old, new in edits:
        if text.count(old) == 1:
            text = text.replace(old, new)
        else:
            assert options.resume and text.count(new) == 1, 'Upstream configure contract changed'
    configure.write_text(text)
    env = dict(os.environ)
    env.update(PATH='/opt/homebrew/opt/libtool/libexec/gnubin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
               CC=str(compiler), CFLAGS='-O2 -fPIC -D_GNU_SOURCE',
               LDFLAGS='-Wl,-z,max-page-size=16384')
    env.update({key: str(tools/key.lower()) for key in binutils})
    receipt = {'state': 'building', 'root': str(root), 'upstream': str(upstream), 'commit': commit,
               'license': 'Upstream LGPL-2.1-or-later; separate dependency build, original source/license preserved',
               'configure_change': 'Real pthread_join and clock_gettime link probes search libc first',
               'purpose': 'Native audio/standalone speaker protection; no hardware access in this build',
               'commands': [], 'physical_device_written': False, 'staged_into_vendor_image': False}
    report = WORK/'native-alsa-build.json'
    if options.resume:
        previous = json.loads(report.read_text())
        assert previous['root'] == str(root) and previous['state'] == 'failed'
        receipt['commands'] = previous['commands']
        receipt['build_attempts'] = previous.get('build_attempts', 1)+1
    else:
        receipt['build_attempts'] = 1
    logfile = root/('build.log' if not options.resume else 'build-attempt'+str(receipt['build_attempts'])+'.log')
    receipt['log'] = str(logfile)
    def save():
        report.write_text(json.dumps(receipt, indent=2)+'\n')
    save()
    with logfile.open('w') as log:
        def run(command, cwd):
            command = list(map(str, command))
            receipt['commands'].append({'argv': command, 'cwd': str(cwd)})
            save()
            log.write('\n'+shlex.join(command)+'\n'); log.flush()
            subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        try:
            if not options.resume:
                run(['/opt/homebrew/bin/autoreconf', '-fi'], source)
            if not options.verify_built:
                run([source/'configure', '--host=aarch64-linux-android', '--prefix=/vendor',
                 '--libdir=/vendor/lib64', '--with-configdir=/vendor/etc/alsa-m1',
                 '--with-plugindir=/vendor/lib64/alsa-m1', '--disable-static', '--enable-shared',
                 '--disable-aload', '--disable-python', '--disable-rawmidi', '--disable-seq',
                 '--disable-hwdep', '--disable-ucm', '--disable-topology',
                 '--with-pcm-plugins=', '--with-ctl-plugins='], build)
            config = (build/'include/config.h').read_text()
            for macro in ['HAVE_LIBPTHREAD', 'THREAD_SAFE_API', 'HAVE_CLOCK_GETTIME']:
                assert '#define '+macro+' ' in config, 'Required actual capability not detected: '+macro
            if not options.verify_built:
                run(['/opt/homebrew/bin/gmake', '-j6'], build)
                run(['/opt/homebrew/bin/gmake', 'install', 'DESTDIR='+str(stage)], build)
            # Android libtool intentionally uses an unversioned .so SONAME.
            libs = list((stage/'vendor/lib64').glob('libasound.so*'))
            assert libs
            for lib in libs:
                data = lib.read_bytes()
                assert data[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', data, 18)[0] == 183
                phoff = struct.unpack_from('<Q', data, 32)[0]
                stride, count = struct.unpack_from('<HH', data, 54)
                for i in range(count):
                    offset = phoff+i*stride
                    if struct.unpack_from('<I', data, offset)[0] == 1:
                        assert struct.unpack_from('<Q', data, offset+48)[0] >= 16384
                needed = json.loads(subprocess.check_output(
                    [str(NDK/'bin/llvm-readobj'), '--needed-libs', '--elf-output-style=JSON', str(lib)], text=True))[0]['NeededLibraries']
                assert set(needed) <= {'libc.so', 'libdl.so', 'libm.so'}, needed
            receipt.update(state='built', files={str(p.relative_to(stage)): hashlib.sha256(p.read_bytes()).hexdigest()
                                                for p in libs if not p.is_symlink()}, runtime_tested=False,
                           elf_aarch64_16k_checked=True)
        except Exception as error:
            receipt.update(state='failed', error=str(error), log=str(logfile))
            save()
            raise
    save()
    print('NATIVE_ALSA_LIB_BUILD_PASS', stage)


if __name__ == '__main__':
    main()
