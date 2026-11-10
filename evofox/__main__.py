"""Read-only inspection of the supplied EvoFox Blaze driver and Linux HID devices."""
import argparse
import json
import re
import sys
from pathlib import Path


# Feature collection supplied by the user for a 30fa:1440 interface.
# This is a conservative fingerprint, not evidence that every matching
# device has the same model or can safely accept the same commands.
FEATURE_COLLECTION = bytes.fromhex(
    '06 01 ff 09 01 a1 01 85 07 15 00 26 ff 00 '
    '09 20 95 07 75 08 b1 02 c0'
)


def identify_interface(bus, vendor_id, product_id, descriptor):
    if (bus, vendor_id, product_id) != ('0003', '30fa', '1440'):
        return 'other'
    if descriptor is None:
        return 'candidate; descriptor unavailable'
    if FEATURE_COLLECTION in descriptor:
        return 'candidate feature-report interface'
    return 'candidate; no matching feature collection'


def is_candidate(device):
    return ((device['bus'], device['vendor_id'], device['product_id']) ==
            ('0003', '30fa', '1440') or
            bool(re.search(r'evofox|blaze', device['name'], re.I)))


def read_ini(path):
    """Read vendor INI data without rewriting it or interpreting device codes.

    The included config.ini is an ANSI file with Chinese text, not UTF-8.  Use
    GB18030 for the included file and UTF-16 for the vendor's language files.
    Repeated sections/keys use the last value, as Windows INI access does.
    """
    data = Path(path).read_bytes()
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        text = data.decode('utf-16')
    elif data.startswith(b'\xef\xbb\xbf'):
        text = data.decode('utf-8-sig')
    else:
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            text = data.decode('gb18030', errors='replace')
    sections = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith((';', '#', '//')):
            continue
        match = re.match(r'^\[([^]]+)\]', line)
        if match:
            current = sections.setdefault(match.group(1), {})
        elif current is not None and '=' in line:
            key, value = line.split('=', 1)
            current[key.strip()] = value.split('//', 1)[0].strip()
    return sections


def inspect_config(path):
    sections = read_ini(path)
    if 'PRODUCTNAME' not in sections or 'Init' not in sections:
        raise ValueError('not a recognized vendor config.ini (missing PRODUCTNAME or Init)')
    names = sections['Init']
    profiles = []
    for section in sections:
        m = re.fullmatch(r'Config(\d+)', section)
        if not m:
            continue
        index = int(m.group(1))
        profiles.append({'index': index,
                         'name': names.get(f'ConfigName{index + 1}_EN'),
                         'values': sections[section]})
    profiles.sort(key=lambda item: item['index'])
    return {'product': sections['PRODUCTNAME'].get('PRODUCTNAME_EN'),
            'initialization': names,
            'key_mapping': sections.get('KEYMAP', {}),
            'profiles': profiles,
            'shared_values': sections.get('ShareData', {})}


def scan_hid(sys_class=Path('/sys/class/hidraw')):
    """Read sysfs metadata only; never open a HID node or issue reports."""
    found = []
    for entry in sorted(sys_class.glob('hidraw*')):
        try:
            metadata = {}
            for line in (entry / 'device' / 'uevent').read_text(errors='replace').splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    metadata[key] = value
            parts = metadata.get('HID_ID', '').split(':')
            bus = parts[0].lower() if len(parts) == 3 else None
            vendor = parts[1][-4:].lower() if len(parts) == 3 else None
            product = parts[2][-4:].lower() if len(parts) == 3 else None
            try:
                descriptor = (entry / 'device' / 'report_descriptor').read_bytes()
            except OSError:
                descriptor = None
            found.append({'node': '/dev/' + entry.name,
                          'name': metadata.get('HID_NAME', ''),
                          'bus': bus,
                          'vendor_id': vendor,
                          'product_id': product,
                          'physical_path': metadata.get('HID_PHYS', ''),
                          'unique_id': metadata.get('HID_UNIQ', ''),
                          'interface_hint': identify_interface(bus, vendor, product, descriptor)})
        except (OSError, UnicodeError):
            # A device can disappear while sysfs is being enumerated.
            continue
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only EvoFox Blaze investigation utilities')
    sub = parser.add_subparsers(dest='command', required=True)
    devices = sub.add_parser('devices', help='list Linux hidraw devices (no device I/O)')
    devices.add_argument('--all', action='store_true', help='include all HID interfaces')
    status = sub.add_parser('status', help='experimentally request one feature report from a confirmed mouse')
    status.add_argument('--device', required=True, help='explicit /dev/hidrawN feature interface')
    status.add_argument('--confirm-blaze', action='store_true', help='confirm that the selected mouse is an EvoFox Blaze')
    sub_config = sub.add_parser('config', help='inspect an extracted vendor config.ini')
    sub_config.add_argument('path', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'devices':
            result = scan_hid()
            if not args.all:
                result = [d for d in result if is_candidate(d)]
        elif args.command == 'status':
            from .status import get_status, interpret_status
            reply = get_status(args.device, confirmed=args.confirm_blaze)
            result = {'device': args.device, 'report_id': 7, 'raw_report_hex': reply.hex(' '),
                      'tentative': interpret_status(reply),
                      'note': 'Provisional decoding from external protocol research; reply may be stale or not status.'}
        else:
            result = inspect_config(args.path)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError) as exc:
        print(f'evofox: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
