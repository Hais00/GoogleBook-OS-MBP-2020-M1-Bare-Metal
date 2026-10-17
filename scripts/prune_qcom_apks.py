#!/usr/bin/env python3
"""Remove identified Qualcomm APKs and their package-specific configuration."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from project_paths import WORK

PACKAGE = re.compile(r'^(com\.qualcomm\.|com\.qti\.|vendor\.qti\.)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', type=Path)
    args = parser.parse_args()
    stage = args.stage.resolve()
    assert stage.is_relative_to(WORK.resolve())
    assert stage.name in ['vendor-linux-cleanup-stage', 'system-ext-linux-cleanup-stage']
    aapt = WORK/'tools/aapt2'
    packages, removals = set(), []
    for area in ['app', 'priv-app']:
        for apk in sorted((stage/area).rglob('*.apk')):
            result = subprocess.run([str(aapt), 'dump', 'badging', str(apk)],
                                    capture_output=True, text=True)
            assert result.returncode == 0, str(apk)+': '+result.stderr
            match = re.search(r"^package: name='([^']+)'", result.stdout, re.M)
            assert match, str(apk)
            name = match[1]
            if not PACKAGE.match(name):
                continue
            tree = subprocess.run([str(aapt), 'dump', 'xmltree', '--file',
                                   'AndroidManifest.xml', str(apk)], capture_output=True, text=True)
            assert tree.returncode == 0, str(apk)
            assert not re.search(r'E: (?:library|static-library|sdk-library)\b', tree.stdout), (
                'Published APK libraries require a consumer audit before removal: '+name)
            directory = apk.parent
            assert directory.parent == stage/area, 'Unexpected nested/shared application directory'
            packages.add(name)
            removals.append({'package': name, 'directory': str(directory.relative_to(stage)),
                             'apk_sha256': hashlib.sha256(apk.read_bytes()).hexdigest()})
    changed = []
    for directory in ['etc/permissions', 'etc/sysconfig']:
        for path in sorted((stage/directory).glob('*.xml')):
            original = path.read_bytes()
            if not any(name.encode() in original for name in packages):
                continue
            tree = ET.ElementTree(ET.fromstring(original, parser=ET.XMLParser(
                target=ET.TreeBuilder(insert_comments=True))))
            removed_nodes = []
            for parent in list(tree.iter()):
                for node in list(parent):
                    if node.attrib.get('package') in packages:
                        removed_nodes.append({'element': node.tag, 'package': node.attrib['package']})
                        parent.remove(node)
            if removed_nodes:
                tree.write(path, encoding='utf-8', xml_declaration=True)
                ET.parse(path)
                changed.append({'file': str(path.relative_to(stage)), 'removed_nodes': removed_nodes,
                                'old_sha256': hashlib.sha256(original).hexdigest(),
                                'new_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    for record in removals:
        shutil.rmtree(stage/record['directory'])
    receipt = {'stage': str(stage), 'removed_packages': removals, 'configuration_updates': changed,
               'package_identity_verified_by': 'official aapt2 binary manifest',
               'published_apk_libraries_removed': False, 'physical_device_written': False,
               'hardware_verified': False, 'qualcomm_removal_complete': False}
    (WORK/(stage.name+'-apk-cleanup.json')).write_text(json.dumps(receipt, indent=2)+'\n')
    print('QCOM_APK_PRIVATE_STAGE_CLEANUP', stage.name, len(removals),
          'packages;', len(changed), 'package configuration files updated')


if __name__ == '__main__':
    main()
