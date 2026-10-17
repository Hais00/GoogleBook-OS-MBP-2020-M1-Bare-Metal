#!/usr/bin/env python3
"""Read back EROFS configuration labels and the board profile before install."""
import argparse
import ctypes
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile
from apple_graphics_policy import DRM_FILE_CONTEXTS

BASE = pathlib.Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=pathlib.Path)
    parser.add_argument('--profile', choices=['m1', 'virt'], required=True)
    parser.add_argument('--output', type=pathlib.Path,
                        default=BASE/'.work/vendor-vintf-label-validation.json')
    args = parser.parse_args()
    lib = ctypes.CDLL('libSystem.B.dylib', use_errno=True)
    lib.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                            ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    lib.getxattr.restype = ctypes.c_ssize_t
    directory = pathlib.Path(tempfile.mkdtemp(prefix='vendor-readback-', dir='/opt/googlebook/build'))
    try:
        checked = subprocess.run(['fsck.erofs', '--extract='+str(directory), '--xattrs',
                                  str(args.image)], capture_output=True, text=True)
        assert checked.returncode == 0, checked.stdout[-2000:]+checked.stderr[-2000:]
        profile_info = json.loads((directory/'etc/googlebook-profile.json').read_text())
        profile = profile_info['profile']
        assert profile == args.profile, 'Wrong graphics/board profile'
        props = dict(line.split('=', 1) for line in (directory/'build.prop').read_text().splitlines()
                     if line and not line.startswith('#') and '=' in line)
        assert props['ro.hardware.vulkan'] == ('asahi' if profile == 'm1' else 'pastel')
        assert props['ro.hardware.gralloc'] == 'cros'
        device_contexts = (directory/'etc/selinux/vendor_file_contexts').read_text()
        for pattern, label in DRM_FILE_CONTEXTS.items():
            assert pattern+' '+label in device_contexts, 'Missing generic DRM label: '+pattern
        composition_format = '1' if profile == 'm1' else '5'
        for key in ['ro.surface_flinger.default_composition_pixel_format',
                    'ro.surface_flinger.wcg_composition_pixel_format']:
            assert props[key] == composition_format, 'Wrong composition format: '+key
        files = sorted(set((directory/'etc/init').rglob('*.rc')) |
                       set((directory/'etc/vintf').rglob('*.xml')))
        assert files
        expected_labels = {path: b'u:object_r:vendor_configs_file:s0' for path in files}
        for rel in ['lib64/libgbm.so', 'lib64/libminigbm_gralloc.so', 'lib64/hw/mapper.minigbm.so',
                    'lib64/hw/gralloc.cros.so', 'lib64/hw/vulkan.asahi.so', 'lib64/hw/vulkan.pastel.so']:
            path = directory/rel
            if path.exists():
                expected_labels[path] = b'u:object_r:same_process_hal_file:s0'
        for rel, label in [
            ('bin/hw/googlebook-audio-hal', b'u:object_r:hal_audio_default_exec:s0'),
            ('bin/hw/android.hardware.graphics.allocator-service.minigbm',
             b'u:object_r:hal_graphics_allocator_default_exec:s0')]:
            expected_labels[directory/rel] = label
        for path, expected in expected_labels.items():
            buf = ctypes.create_string_buffer(256)
            size = lib.getxattr(str(path).encode(), b'security.selinux', buf, len(buf), 0, 1)
            assert size > 0, 'Missing SELinux xattr: '+str(path)
            assert buf.raw[:size].rstrip(b'\0') == expected, str(path)
        for root in ['etc/init', 'etc/vintf/manifest']:
            assert not list((directory/root).rglob('*.disabled')), 'Disabled files would still be parsed'
        with args.image.open('rb') as image:
            image_hash = hashlib.file_digest(image, 'sha256').hexdigest()
        result = {
            'vendor_image': str(args.image.resolve()),
            'vendor_image_sha256': image_hash,
            'board_profile': profile,
            'drm_trace_enabled': profile_info.get('drm_trace', False),
            'composition_pixel_format': int(composition_format),
            'all_drm_card_and_render_nodes_gpu_device': True,
            'vintf_and_init_configuration_labels': 'u:object_r:vendor_configs_file:s0',
            'checked_configuration_files': len(files),
            'same_process_graphics_dependency_labels_checked': len(expected_labels)-len(files),
            'disabled_init_files_outside_parsed_directory': True,
            'disabled_vintf_fragments_outside_manifest_directory': True,
            'method': 'EROFS full integrity check and actual extracted security.selinux xattrs'}
        args.output.write_text(json.dumps(result, indent=2)+'\n')
        print('VENDOR_READBACK_PASS:', profile, len(files), 'configuration labels;', args.output)
    finally:
        shutil.rmtree(directory)


if __name__ == '__main__':
    main()
