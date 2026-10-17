import hashlib
from pathlib import Path
import stat
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from firmware_manifest import repair_firmware_entries


def member(name, data, links=1):
    values = [0]*13
    values[1] = stat.S_IFREG | 0o644
    values[4] = links
    return name, values, data


class FirmwareManifestTest(unittest.TestCase):
    def fixture(self, extra='LINK brcm/alias.bin brcm/base.bin\n'):
        data = b'actual firmware bytes'
        manifest = 'FILE brcm/base.bin SHA256 '+hashlib.sha256(data).hexdigest()+'\n'+extra
        names = {'lib/firmware/.vendorfw.manifest': member('lib/firmware/.vendorfw.manifest', manifest.encode()),
                 'lib/firmware/brcm/base.bin': member('lib/firmware/brcm/base.bin', data, 2),
                 'lib/firmware/brcm/alias.bin': member('lib/firmware/brcm/alias.bin', b'', 2)}
        return names

    def test_recovers_manifest_alias_and_preserves_input(self):
        names = self.fixture()
        fixed, note = repair_firmware_entries(names)
        self.assertEqual(fixed['lib/firmware/brcm/alias.bin'][2], b'actual firmware bytes')
        self.assertEqual(fixed['lib/firmware/brcm/alias.bin'][1][4], 1)
        self.assertEqual(names['lib/firmware/brcm/alias.bin'][2], b'')
        self.assertEqual(len(note['repaired_members']), 1)

    def test_recovers_data_stored_on_an_alias(self):
        names = self.fixture()
        names['lib/firmware/brcm/base.bin'] = member('lib/firmware/brcm/base.bin', b'', 2)
        names['lib/firmware/brcm/alias.bin'] = member('lib/firmware/brcm/alias.bin', b'actual firmware bytes', 2)
        fixed, _ = repair_firmware_entries(names)
        self.assertEqual(fixed['lib/firmware/brcm/base.bin'][2], b'actual firmware bytes')

    def test_rejects_changed_payload(self):
        names = self.fixture()
        names['lib/firmware/brcm/base.bin'] = member('lib/firmware/brcm/base.bin', b'wrong')
        with self.assertRaisesRegex(ValueError, 'differs'):
            repair_firmware_entries(names)

    def test_rejects_unsafe_path(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            repair_firmware_entries(self.fixture('LINK ../outside brcm/base.bin\n'))

    def test_rejects_cycle(self):
        with self.assertRaisesRegex(ValueError, 'cycle'):
            repair_firmware_entries(self.fixture('LINK brcm/alias.bin brcm/alias.bin\n'))

    def test_rejects_unknown_target(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            repair_firmware_entries(self.fixture('LINK brcm/alias.bin brcm/missing.bin\n'))

    def test_rejects_missing_verified_content(self):
        names = self.fixture()
        names['lib/firmware/brcm/base.bin'] = member('lib/firmware/brcm/base.bin', b'', 2)
        with self.assertRaisesRegex(ValueError, 'No verified bytes'):
            repair_firmware_entries(names)


if __name__ == '__main__':
    unittest.main()
