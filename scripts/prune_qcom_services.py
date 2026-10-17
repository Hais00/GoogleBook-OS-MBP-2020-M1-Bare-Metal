#!/usr/bin/env python3
"""Remove Qualcomm-only services from an isolated native M1 image stage."""
import argparse
import hashlib
import json
from pathlib import Path
from project_paths import WORK

REMOVALS = {
    'HDCP provisioning': ['etc/init/hdcp-provisioning-service.rc', 'bin/hdcp-provisioning-service'],
    'Qualcomm perf2 and its vendor notifier': ['etc/init/init.qt-service.rc', 'bin/qt-service',
                                            'etc/vintf/manifest/vendor.qti.hardware.perf2.xml'],
    'Qualcomm display calibration': ['etc/init/qdcmss.rc', 'bin/qdcmss'],
    'Qualcomm display test service': ['etc/init/qttestservice.rc', 'bin/qttestservice'],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', type=Path, default=WORK/'vendor-linux-cleanup-stage')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    vendor = args.vendor.resolve()
    assert vendor.is_relative_to(WORK.resolve())
    assert vendor != (WORK/'vendor-egl-stage').resolve(), 'Keep the physical-trial candidate frozen'
    props = dict(line.split('=', 1) for line in (vendor/'build.prop').read_text().splitlines()
                 if line and not line.startswith('#') and '=' in line)
    assert props['ro.board.platform'] == 't8103' and props['ro.product.board'] == 'j293'
    assert props['ro.surface_flinger.protected_contents'] == 'false'
    changes = []
    for component, names in REMOVALS.items():
        for name in names:
            path = vendor/name
            if not path.exists():
                continue
            assert not path.is_symlink()
            changes.append({'component': component, 'path': name,
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    if args.apply:
        for change in changes:
            (vendor/change['path']).unlink()
    receipt = {'stage': str(vendor), 'applied': args.apply, 'removed': changes,
               'basis': 'Native DRM composer has no QTI display backend; no QTEE/HDCP provider; no Qualcomm CPU performance driver',
               'perf2_fragment_also_removed': 'com.android.desktop.power.IVendorNotifier/default',
               'kernel_or_framework_modified': False, 'physical_device_written': False,
               'qualcomm_removal_complete': False, 'hardware_verified': False}
    (WORK/'qcom-service-cleanup.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print('QCOM_PRIVATE_STAGE_CLEANUP', 'APPLIED' if args.apply else 'PLAN', len(changes), 'files')


if __name__ == '__main__':
    main()
