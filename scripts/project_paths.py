"""Canonical build paths for the Development checkout, independent of old home aliases."""
from pathlib import Path
import os

BASE = Path(__file__).resolve().parents[1]
WORK = BASE / '.agent-work'
BUILD_VOLUME = Path(os.environ.get('GOS_BUILD_VOLUME', '/opt/googlebook/build'))
NDK = BASE / 'android-ndk-r28/toolchains/llvm/prebuilt/darwin-x86_64'
VNDK = BUILD_VOLUME / 'aosp-vndk'
SYSTEM_ORIGINAL = BUILD_VOLUME / 'system-original/system'
GRAPHICS_OUT = WORK / 'graphics-out'
LARGE_WORK = Path(os.environ.get('GOS_LARGE_WORK', '/opt/googlebook/external/googlebook-bringup-20261016'))

def require_build_inputs():
    for path in (NDK/'bin/clang', VNDK, SYSTEM_ORIGINAL):
        if not path.exists():
            raise RuntimeError(f'Missing migrated build input: {path}')

