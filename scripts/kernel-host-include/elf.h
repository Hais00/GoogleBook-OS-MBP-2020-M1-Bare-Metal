/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _SCRIPTS_ELF_H_COMPAT
#define _SCRIPTS_ELF_H_COMPAT

#include <stdint.h>
#include <sys/types.h>

#include "/opt/googlebook/host/android-ndk-r28/toolchains/llvm/prebuilt/darwin-x86_64/sysroot/usr/include/bits/elf_common.h"

typedef uint16_t Elf32_Half;
typedef uint32_t Elf32_Word;
typedef uint32_t Elf32_Addr;
typedef uint32_t Elf32_Off;
typedef int32_t  Elf32_Sword;

typedef uint16_t Elf64_Half;
typedef uint32_t Elf64_Word;
typedef uint64_t Elf64_Addr;
typedef uint64_t Elf64_Off;
typedef int32_t  Elf64_Sword;
typedef int64_t  Elf64_Sxword;
typedef uint64_t Elf64_Xword;

#ifndef EI_NIDENT
#define EI_NIDENT 16
#endif

typedef struct {
	unsigned char e_ident[EI_NIDENT];
	Elf32_Half    e_type;
	Elf32_Half    e_machine;
	Elf32_Word    e_version;
	Elf32_Addr    e_entry;
	Elf32_Off     e_phoff;
	Elf32_Off     e_shoff;
	Elf32_Word    e_flags;
	Elf32_Half    e_ehsize;
	Elf32_Half    e_phentsize;
	Elf32_Half    e_phnum;
	Elf32_Half    e_shentsize;
	Elf32_Half    e_shnum;
	Elf32_Half    e_shstrndx;
} Elf32_Ehdr;

typedef struct {
	unsigned char e_ident[EI_NIDENT];
	Elf64_Half    e_type;
	Elf64_Half    e_machine;
	Elf64_Word    e_version;
	Elf64_Addr    e_entry;
	Elf64_Off     e_phoff;
	Elf64_Off     e_shoff;
	Elf64_Word    e_flags;
	Elf64_Half    e_ehsize;
	Elf64_Half    e_phentsize;
	Elf64_Half    e_phnum;
	Elf64_Half    e_shentsize;
	Elf64_Half    e_shnum;
	Elf64_Half    e_shstrndx;
} Elf64_Ehdr;

typedef struct {
	Elf32_Word sh_name;
	Elf32_Word sh_type;
	Elf32_Word sh_flags;
	Elf32_Addr sh_addr;
	Elf32_Off  sh_offset;
	Elf32_Word sh_size;
	Elf32_Word sh_link;
	Elf32_Word sh_info;
	Elf32_Word sh_addralign;
	Elf32_Word sh_entsize;
} Elf32_Shdr;

typedef struct {
	Elf64_Word  sh_name;
	Elf64_Word  sh_type;
	Elf64_Xword sh_flags;
	Elf64_Addr  sh_addr;
	Elf64_Off   sh_offset;
	Elf64_Xword sh_size;
	Elf64_Word  sh_link;
	Elf64_Word  sh_info;
	Elf64_Xword sh_addralign;
	Elf64_Xword sh_entsize;
} Elf64_Shdr;

typedef struct {
	Elf32_Word    st_name;
	Elf32_Addr    st_value;
	Elf32_Word    st_size;
	unsigned char st_info;
	unsigned char st_other;
	Elf32_Half    st_shndx;
} Elf32_Sym;

typedef struct {
	Elf64_Word    st_name;
	unsigned char st_info;
	unsigned char st_other;
	Elf64_Half    st_shndx;
	Elf64_Addr    st_value;
	Elf64_Xword   st_size;
} Elf64_Sym;

typedef struct {
	Elf32_Addr st_offset;
	Elf32_Word r_info;
} Elf32_Rel;

typedef struct {
	Elf64_Addr  r_offset;
	Elf64_Xword r_info;
} Elf64_Rel;

typedef struct {
	Elf32_Addr  r_offset;
	Elf32_Word  r_info;
	Elf32_Sword r_addend;
} Elf32_Rela;

typedef struct {
	Elf64_Addr   r_offset;
	Elf64_Xword  r_info;
	Elf64_Sxword r_addend;
} Elf64_Rela;

#ifndef ELF32_ST_BIND
#define ELF32_ST_BIND(i) ((i) >> 4)
#endif
#ifndef ELF64_ST_BIND
#define ELF64_ST_BIND(i) ((i) >> 4)
#endif

#ifndef ELF32_ST_TYPE
#define ELF32_ST_TYPE(i) ((i) & 0xf)
#endif
#ifndef ELF64_ST_TYPE
#define ELF64_ST_TYPE(i) ((i) & 0xf)
#endif

#ifndef ELF32_R_SYM
#define ELF32_R_SYM(i) ((i) >> 8)
#define ELF32_R_TYPE(i) ((unsigned char)(i))
#endif
#ifndef ELF64_R_SYM
#define ELF64_R_SYM(i) ((i) >> 32)
#define ELF64_R_TYPE(i) ((i) & 0xffffffff)
#endif

#ifndef R_ARM_NONE
#define R_ARM_NONE 0
#endif
#ifndef R_ARM_CALL
#define R_ARM_CALL 28
#endif
#ifndef R_ARM_JUMP24
#define R_ARM_JUMP24 29
#endif
#ifndef R_ARM_THM_JUMP24
#define R_ARM_THM_JUMP24 30
#endif
#ifndef R_ARM_MOVW_ABS_NC
#define R_ARM_MOVW_ABS_NC 43
#endif
#ifndef R_ARM_MOVT_ABS
#define R_ARM_MOVT_ABS 44
#endif
#ifndef R_ARM_THM_MOVW_ABS_NC
#define R_ARM_THM_MOVW_ABS_NC 47
#endif
#ifndef R_ARM_THM_MOVT_ABS
#define R_ARM_THM_MOVT_ABS 48
#endif
#ifndef R_ARM_THM_JUMP19
#define R_ARM_THM_JUMP19 51
#endif
#ifndef R_AARCH64_NONE
#define R_AARCH64_NONE 0
#endif

#endif /* _SCRIPTS_ELF_H_COMPAT */
