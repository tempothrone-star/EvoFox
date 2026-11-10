"""Explicit, experimental GET_FEATURE status probe; never issues SET_FEATURE.

The request framing and status convention are described in Aurora's protocol
notes: https://github.com/rugbedbugg/aurora/blob/main/docs/protocol.txt
A shared VID/PID and descriptor cannot prove that firmware is compatible.
"""
import fcntl
import os
import re
import stat
import struct

from .__main__ import FEATURE_COLLECTION

REPORT_SIZE = 8
MAX_DESCRIPTOR_SIZE = 4096


def ioc(direction, number, size):
    # Linux asm-generic ioctl encoding, used on common x86/ARM Linux systems.
    return (direction << 30) | (size << 16) | (ord('H') << 8) | number


HIDIOCGRAWINFO = ioc(2, 0x03, 8)
HIDIOCGRDESCSIZE = ioc(2, 0x01, 4)
HIDIOCGRDESC = ioc(2, 0x02, 4 + MAX_DESCRIPTOR_SIZE)
HIDIOCGFEATURE = ioc(3, 0x07, REPORT_SIZE)


def interpret_status(reply):
    """Provisional decoding from Aurora's notes, not verified on this mouse.

    A GET may return data from an ongoing transaction rather than live status.
    Only attempt decoding when observed status marker bytes and reserved bits
    match. Unknown polling codes or unrecognized replies remain undecoded.
    """
    if (len(reply) != REPORT_SIZE or reply[0] != 7 or reply[3] != 9
            or reply[5] != 0 or (reply[6] & 0x13) != 0x03):
        return None
    polling = {0: 1000, 1: 500, 3: 250, 7: 125}.get(reply[6] >> 5)
    if polling is None:
        return None
    return {'polling_hz': polling, 'profile_index': (reply[6] >> 2) & 3,
            'lighting_effect_code': reply[7] >> 4}


def get_status(node, *, confirmed=False):
    """Issue exactly one GET_FEATURE only after checking the open device.

    Returns the raw reply; does not assert that the response has the status
    layout seen on other devices. Never decodes or modifies settings.
    """
    if not confirmed:
        raise ValueError('confirm that this is an EvoFox Blaze before probing')
    if not re.fullmatch(r'/dev/hidraw[0-9]+', str(node)):
        raise ValueError('device must be a /dev/hidrawN path')
    fd = os.open(str(node), os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        if not stat.S_ISCHR(os.fstat(fd).st_mode):
            raise ValueError('selected path is not a character device')
        info = bytearray(8)
        fcntl.ioctl(fd, HIDIOCGRAWINFO, info)
        bus, vendor, product = struct.unpack('=IHH', info)
        if (bus, vendor, product) != (3, 0x30fa, 0x1440):
            raise ValueError('selected device is not USB 30fa:1440')
        size_buf = bytearray(4)
        fcntl.ioctl(fd, HIDIOCGRDESCSIZE, size_buf)
        size = struct.unpack('=I', size_buf)[0]
        if not 0 < size <= MAX_DESCRIPTOR_SIZE:
            raise ValueError(f'invalid HID report descriptor size: {size}')
        descriptor = bytearray(4 + MAX_DESCRIPTOR_SIZE)
        struct.pack_into('=I', descriptor, 0, size)
        fcntl.ioctl(fd, HIDIOCGRDESC, descriptor)
        returned_size = struct.unpack_from('=I', descriptor)[0]
        if returned_size != size or FEATURE_COLLECTION not in descriptor[4:4 + size]:
            raise ValueError('selected interface does not match the known feature collection')
        reply = bytearray([7] + [0] * (REPORT_SIZE - 1))
        count = fcntl.ioctl(fd, HIDIOCGFEATURE, reply)
        if count != REPORT_SIZE or reply[0] != 7:
            raise ValueError(f'unexpected feature reply (length {count}, data {reply.hex(" ")})')
        return bytes(reply)
    finally:
        os.close(fd)
