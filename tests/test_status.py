import os
import stat
import struct
import unittest
from unittest.mock import patch

from evofox.__main__ import FEATURE_COLLECTION
from evofox.status import (HIDIOCGFEATURE, HIDIOCGRAWINFO, HIDIOCGRDESC,
                           HIDIOCGRDESCSIZE, get_status, interpret_status)


class StatusTests(unittest.TestCase):
    def ioctl(self, fd, request, buf):
        self.calls.append(request)
        if request == HIDIOCGRAWINFO:
            struct.pack_into('=IHH', buf, 0, *self.info)
        elif request == HIDIOCGRDESCSIZE:
            struct.pack_into('=I', buf, 0, len(self.descriptor))
        elif request == HIDIOCGRDESC:
            buf[4:4 + len(self.descriptor)] = self.descriptor
        elif request == HIDIOCGFEATURE:
            self.assertEqual(bytes(buf), b'\x07' + b'\x00' * 7)
            buf[:] = b'\x07\x00\x62\x09\x10\x00\x23\x6b'
            return self.reply_length
        else:
            self.fail(f'unexpected ioctl {request:x}')
        return 0

    def setUp(self):
        self.calls = []
        self.info = (3, 0x30fa, 0x1440)
        self.descriptor = FEATURE_COLLECTION
        self.reply_length = 8
        self.open = patch('evofox.status.os.open', return_value=42).start()
        self.close = patch('evofox.status.os.close').start()
        self.fstat = patch('evofox.status.os.fstat').start()
        self.fstat.return_value.st_mode = stat.S_IFCHR
        self.mock_ioctl = patch('evofox.status.fcntl.ioctl', side_effect=self.ioctl).start()
        self.flock = patch('evofox.status.fcntl.flock').start()
        self.addCleanup(patch.stopall)

    def test_status_only_gets_one_report(self):
        result = get_status('/dev/hidraw2', confirmed=True)
        self.assertEqual(result.hex(), '070062091000236b')
        self.assertEqual(self.calls, [HIDIOCGRAWINFO, HIDIOCGRDESCSIZE, HIDIOCGRDESC, HIDIOCGFEATURE])
        self.flock.assert_called_once()
        self.assertEqual(self.open.call_args.args[1] & os.O_ACCMODE, os.O_RDONLY)
        self.close.assert_called_once_with(42)

    def test_requires_confirmation_and_valid_path(self):
        with self.assertRaises(ValueError):
            get_status('/dev/hidraw2')
        with self.assertRaises(ValueError):
            get_status('/tmp/hidraw2', confirmed=True)
        self.open.assert_not_called()

    def test_wrong_device_is_rejected_before_report(self):
        self.info = (3, 0x1234, 0x1440)
        with self.assertRaises(ValueError):
            get_status('/dev/hidraw2', confirmed=True)
        self.assertEqual(self.calls, [HIDIOCGRAWINFO])
        self.close.assert_called_once_with(42)

    def test_missing_descriptor_never_requests_feature(self):
        self.descriptor = b'not a match'
        with self.assertRaises(ValueError):
            get_status('/dev/hidraw2', confirmed=True)
        self.assertNotIn(HIDIOCGFEATURE, self.calls)

    def test_short_reply_rejected(self):
        self.reply_length = 3
        with self.assertRaises(ValueError):
            get_status('/dev/hidraw2', confirmed=True)
        self.close.assert_called_once_with(42)

    def test_report_from_user_provisional_decoding(self):
        self.assertEqual(interpret_status(bytes.fromhex('07 00 66 09 49 00 03 7b')),
                         {'polling_hz': 1000, 'profile_index': 0, 'lighting_effect_code': 7})

    def test_status_decoding_rejects_unknown_formats(self):
        self.assertIsNone(interpret_status(b''))
        self.assertIsNone(interpret_status(bytes.fromhex('07 00 66 08 49 00 03 7b')))
        self.assertIsNone(interpret_status(bytes.fromhex('07 00 66 09 49 00 43 7b')))
        self.assertIsNone(interpret_status(bytes.fromhex('07 00 66 09 49 00 13 7b')))

    def test_known_polling_codes(self):
        for raw, hz in [(0x03, 1000), (0x23, 500), (0x63, 250), (0xe3, 125)]:
            with self.subTest(raw=raw):
                reply = bytes([7, 0, 0, 9, 0, 0, raw | 0x0c, 0])
                self.assertEqual(interpret_status(reply)['polling_hz'], hz)
                self.assertEqual(interpret_status(reply)['profile_index'], 3)

    def test_regular_file_rejected(self):
        self.fstat.return_value.st_mode = stat.S_IFREG
        with self.assertRaises(ValueError):
            get_status('/dev/hidraw2', confirmed=True)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
