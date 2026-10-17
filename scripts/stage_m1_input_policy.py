#!/usr/bin/env python3
"""Reserve the actual Touch Bar sensor for its native function-row owner."""
import hashlib
import json
import xml.etree.ElementTree as ET
from project_paths import WORK, LARGE_WORK
from stage_native_egl import getlabel, lib


def main():
    vendor = WORK/'vendor-linux-cleanup-stage'
    target = vendor/'etc/excluded-input-devices.xml'
    name = 'MacBookPro17,1 Touch Bar'
    evidence = LARGE_WORK/'trial-native-egl-kernel21-owner-private-controls/virtual-uart.raw.log'
    assert "name='"+name+"'" in evidence.read_text(errors='replace')
    tree = ET.parse(target) if target.exists() else ET.ElementTree(ET.Element('devices'))
    root = tree.getroot()
    assert root.tag == 'devices'
    before = [dict(node.attrib) for node in root]
    if not any(node.tag == 'device' and node.get('name') == name for node in root):
        ET.SubElement(root, 'device', {'name': name})
    ET.indent(tree)
    tree.write(target, encoding='utf-8', xml_declaration=True)
    target.chmod(0o644)
    label = getlabel(vendor/'etc/init/allocator-minigbm.rc')
    assert lib.setxattr(str(target).encode(), b'security.selinux', label, len(label), 0, 1) == 0
    assert getlabel(target) == label
    after = [dict(node.attrib) for node in root]
    assert all(node in after for node in before)
    assert not any('Keyboard' in node.get('name', '') or 'Trackpad' in node.get('name', '')
                   for node in root if node.attrib not in before)
    (WORK/'m1-input-policy-stage.json').write_text(json.dumps({
        'file': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'excluded_physical_sensor': name, 'prior_entries_preserved': before,
        'reason': 'Actual Touch Bar was mapped as a touchscreen for the main display. Native row daemon consumes it and emits real uinput key events.',
        'framework_source': str(WORK/'references/android-input-native/provenance.json'),
        'native_owner_ready': False, 'hardware_verified': False, 'physical_device_written': False,
        'admission': 'Install only together with working native function-row owner; keyboard and trackpad stay with InputReader.'
    }, indent=2)+'\n')
    print('M1_TOUCH_BAR_INPUT_POLICY_STAGED', target)


if __name__ == '__main__':
    main()
