#!/usr/bin/env python3
"""Build pinned M1 AVD firmware and prove its actual Cortex-M3 reset vector layout."""
import argparse,hashlib,json,struct,subprocess
from pathlib import Path
from project_paths import BASE,WORK
PIN='220b1e70c9d7dcccbf66d5194e372300aa3c5a32'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-directory',type=Path,default=WORK/'avd-fw-vectors-canonical');a=p.parse_args();out=a.output_directory;assert not out.exists();out.mkdir()
 src=WORK/'references/asahi-avd-fw';assert subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip()==PIN
 assert not subprocess.check_output(['git','-C',str(src),'diff','--name-only'],text=True).strip(),'Pinned firmware sources must remain unchanged'
 clang=Path('/opt/homebrew/opt/llvm@19/bin/clang');objcopy=clang.with_name('llvm-objcopy');ld=BASE/'scripts/avd-cm3-vectors.ld';commands=[];objects=[]
 def run(cmd):
  r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);commands.append(list(map(str,cmd)));assert r.returncode==0,r.stderr
 for name in ['util','irq','avd']:
  obj=out/(name+'.o');run([clang,'-Wall','-O2','-nostdlib','-mthumb','-mcpu=cortex-m3','--target=arm-none-eabi','-DAVD_VER=2','-DAVD_TIER=0','-c',src/'src'/(name+'.c'),'-o',obj]);objects.append(obj)
 elf=out/'avd-fw-v2-t0.elf';binary=out/'avd-fw-v2-t0.bin';run([clang,'-fuse-ld=lld','--target=arm-none-eabi','-nostdlib','-mthumb','-mcpu=cortex-m3','-Wl,--entry=_start','-T',ld,'-o',elf]+objects);run([objcopy,'-O','binary','--strip-debug','--pad-to=0xc000',elf,binary])
 b=elf.read_bytes();shoff=struct.unpack_from('<I',b,32)[0];ent,n,strings=struct.unpack_from('<HHH',b,46);sections=[struct.unpack_from('<IIIIIIIIII',b,shoff+i*ent) for i in range(n)];ss=sections[strings];names=b[ss[4]:ss[4]+ss[5]];sec={names[s[0]:].split(b'\0',1)[0].decode():s for s in sections};assert sec['.vectors'][3]==0 and sec['.vectors'][5]>=8
 raw=binary.read_bytes();sp,reset=struct.unpack_from('<II',raw);assert sp==0x1000c000 and reset&1 and len(raw)==49152;assert sec['.text'][3]<=(reset&~1)<sec['.text'][3]+sec['.text'][5]
 previous=json.loads((WORK/'avd-fw-build.json').read_text()) if (WORK/'avd-fw-build.json').exists() else {}
 if previous.get('vectors_address')==0:assert digest(binary)==previous['sha256'],'Reproduction differs from recorded vector-fixed firmware'
 r={'source':'https://github.com/AsahiLinux/avd-fw','commit':PIN,'license':'MIT','target':'M1 t8103 AVD v2 tier0','file':str(binary),'bytes':len(raw),'sha256':digest(binary),'commands':commands,'linker_script':str(ld),'linker_script_sha256':digest(ld),'vectors_address':sec['.vectors'][3],'initial_stack_pointer':hex(sp),'reset_vector_thumb':hex(reset),'reset_vector_in_executable_text':True,'upstream_firmware_sources_unchanged':True,'reproduces_previous_vector_fixed_bytes':previous.get('sha256')==digest(binary),'hardware_tested':False}
 (out/'build.json').write_text(json.dumps(r,indent=2)+'\n');(WORK/'avd-fw-build.json').write_text(json.dumps(r,indent=2)+'\n');print('M1_AVD_RESET_VECTORS_REPRODUCED_PASS',r['sha256'])
if __name__=='__main__':main()
