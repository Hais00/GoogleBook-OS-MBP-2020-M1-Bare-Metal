#!/bin/sh
set -eu
scripts_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
kernel_dir=${1:-/opt/googlebook/build/linux-asahi}
cd "$kernel_dir"
if git apply --check "$scripts_dir/kernel-macos-m1.patch" 2>/dev/null; then
    git apply "$scripts_dir/kernel-macos-m1.patch"
else
    git apply --reverse --check "$scripts_dir/kernel-macos-m1.patch"
fi
cp "$scripts_dir/kernel-host-include/elf.h" scripts/include/elf.h
cp "$scripts_dir/kernel-host-include/endian.h" scripts/include/endian.h
cp "$scripts_dir/kernel-host-include/byteswap.h" scripts/include/byteswap.h
cp "$scripts_dir/kernel-googlebook.config" .config
export PATH="/opt/googlebook/host/.cargo/bin:/opt/homebrew/opt/make/libexec/gnubin:/opt/homebrew/opt/gnu-sed/libexec/gnubin:/opt/homebrew/opt/llvm@19/bin:/opt/googlebook/host/android-ndk-r28/toolchains/llvm/prebuilt/darwin-x86_64/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LIBCLANG_PATH=/opt/homebrew/opt/llvm@19/lib
export RUSTUP_TOOLCHAIN=1.85.0
export LC_ALL=C
/opt/homebrew/bin/gmake ARCH=arm64 LLVM=1 HOSTCC=/usr/bin/clang HOSTCXX=/usr/bin/clang++ KRUSTFLAGS=-Aunknown_lints olddefconfig
exec /opt/homebrew/bin/gmake -j6 ARCH=arm64 LLVM=1 HOSTCC=/usr/bin/clang HOSTCXX=/usr/bin/clang++ KRUSTFLAGS=-Aunknown_lints Image dtbs
