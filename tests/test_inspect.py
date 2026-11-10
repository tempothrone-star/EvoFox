import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from evofox.__main__ import FEATURE_COLLECTION, inspect_config, is_candidate, main, read_ini, scan_hid


class ConfigTests(unittest.TestCase):
    def test_vendor_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.ini'
            path.write_bytes('[Init]\r\nConfigName1_EN=Office\r\n[PRODUCTNAME]\r\nPRODUCTNAME_EN=EvoFox Blaze Gaming Mouse\r\n[KEYMAP]// comment\r\nK1_MAP=1//S0_R0\r\n[Config0]\r\nK0=1\r\n[ShareData]\r\nUSB_SPEED=2\r\n'.encode('gb18030'))
            before = path.read_bytes()
            result = inspect_config(path)
            self.assertEqual(result['profiles'][0]['name'], 'Office')
            self.assertEqual(result['key_mapping']['K1_MAP'], '1')
            self.assertEqual(result['shared_values']['USB_SPEED'], '2')
            self.assertEqual(path.read_bytes(), before)

    def test_utf16_repeated_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'lang.ini'
            path.write_text('[x]\na=first\n[x] // comment\na=second\n', encoding='utf-16')
            self.assertEqual(read_ini(path)['x']['a'], 'second')

    def test_invalid_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.ini'
            path.write_text('[Other]\nx=1\n')
            with self.assertRaises(ValueError):
                inspect_config(path)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['config', str(path)]), 1)


class DevicesTests(unittest.TestCase):
    def test_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            device = root / 'hidraw0' / 'device'
            device.mkdir(parents=True)
            (device / 'uevent').write_text('HID_ID=0003:00001234:0000ABCD\nHID_NAME=Test Mouse\nHID_PHYS=usb-test\n')
            (root / 'hidraw1').mkdir()  # disappeared device
            result = scan_hid(root)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['node'], '/dev/hidraw0')
            self.assertEqual(result[0]['vendor_id'], '1234')
            self.assertEqual(result[0]['product_id'], 'abcd')

    def test_user_interfaces_and_default_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for n in range(3):
                device = root / f'hidraw{n}' / 'device'
                device.mkdir(parents=True)
                vendor, product = ('30FA', '1440') if n < 2 else ('1234', '5678')
                (device / 'uevent').write_text(
                    f'HID_ID=0003:0000{vendor}:0000{product}\n'
                    'HID_NAME=INSTANT USB Gaming Mouse\n')
            (root / 'hidraw0/device/report_descriptor').write_bytes(bytes.fromhex('05 01 09 02'))
            (root / 'hidraw1/device/report_descriptor').write_bytes(bytes.fromhex('05 01') + FEATURE_COLLECTION)
            # An unrelated device with the same bytes must not be identified.
            (root / 'hidraw2/device/report_descriptor').write_bytes(FEATURE_COLLECTION)
            items = scan_hid(root)
            self.assertEqual(items[0]['interface_hint'], 'candidate; no matching feature collection')
            self.assertEqual(items[1]['interface_hint'], 'candidate feature-report interface')
            self.assertEqual(items[2]['interface_hint'], 'other')
            self.assertEqual([is_candidate(d) for d in items], [True, True, False])
            (root / 'hidraw1/device/report_descriptor').unlink()
            self.assertEqual(scan_hid(root)[1]['interface_hint'], 'candidate; descriptor unavailable')

    def test_main_devices_json(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['devices', '--all']), 0)
        self.assertIsInstance(json.loads(out.getvalue()), list)


class GuiModelTests(unittest.TestCase):
    def test_config_sections_include_unnamed_profile_and_shared_values(self):
        from evofox.gui import config_sections
        sections = dict(config_sections({'product': 'Test', 'initialization': {},
                                         'profiles': [{'index': 4, 'name': None, 'values': {'K0': '1'}}],
                                         'shared_values': {'USB_SPEED': '2'}}))
        self.assertEqual(sections['Profile 4 — Unnamed']['K0'], '1')
        self.assertEqual(sections['Shared settings (raw)']['USB_SPEED'], '2')


if __name__ == '__main__':
    unittest.main()
