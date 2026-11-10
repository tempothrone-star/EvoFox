"""Experimental fixed live-lighting requests, not saved lighting configuration.

Two frames are documented by the independent Aurora Blaze protocol research:
https://github.com/rugbedbugg/aurora/blob/main/docs/protocol.txt
Nothing runs on import. No backup or restore command is known for live state.
"""
import argparse
import fcntl
import json
from pathlib import Path
import sys

from evofox_blaze.feature_read import Journal, check_host, load_baseline, select_target, validated_handle
from evofox_blaze.probe import enumerate_devices
from evofox_blaze.state_read import IDENTITY, SET_FEATURE
from .polling import BASELINE

# Literal frames only; no generic command encoder or arbitrary packet input.
FRAMES = {
    'light-on': bytes.fromhex('07 13 ff a2 0b 04 03 ff'),
    'light-off': bytes.fromhex('07 13 ff 52 0b 03 83 ff'),
}


def preview_once(target, mode, capture, recheck, *, accept_risk=False):
    """Send exactly one fixed live-effect frame after explicit risk opt-in.

    No GET, configuration-block write, backup, restore, retries or automatic
    reset. Although the published source describes these frames as live-only,
    their effect and persistence on this particular device are not established. Treat a failure after intent as an uncertain device state.
    """
    if accept_risk is not True:
        raise ValueError('Explicit live-lighting risk acknowledgement is required')
    if mode not in FRAMES:
        raise ValueError('Unsupported live-lighting frame')
    check_host()
    if target.identity() != IDENTITY:
        raise ValueError('Live preview requires the exact captured Blaze identity and descriptor')
    frame = FRAMES[mode]
    capture = Path(capture)
    capture.mkdir(parents=True, exist_ok=False)
    journal = Journal(capture / 'lighting-preview.jsonl')
    try:
        journal.record('lighting_session', identity=target.identity(), mode=mode,
                       scope='One experimental SET_FEATURE, no backup, readback, reset or retry',
                       accepted_live_lighting_risk=True)
        with validated_handle(target, journal.record, recheck, writable=True) as fd:
            journal.record('lighting_request_intent', ioctl=f'0x{SET_FEATURE:08x}', frame_hex=frame.hex(' '))
            buffer = bytearray(frame)
            try:
                returned = fcntl.ioctl(fd, SET_FEATURE, buffer, True)
            except OSError as error:
                journal.record('lighting_request_error', errno=error.errno, message=str(error))
                raise
            journal.record('lighting_request_result', returned_length=returned, buffer_hex_after=buffer.hex(' '))
            if type(returned) is not int or returned != 8 or buffer != frame:
                raise ValueError('Short or changed request result; lighting state may be uncertain')
        result = {'outcome': 'request-sent', 'mode': mode, 'frame_hex': frame.hex(' '),
                  'hardware_behavior_verified': False, 'original_lighting_backed_up': False,
                  'automatic_restore': False}
        journal.record('lighting_complete', **result)
        return result
    except (OSError, ValueError, TypeError, KeyError) as error:
        try:
            journal.record('lighting_failed', error_type=type(error).__name__, message=str(error),
                           recovery='No automatic retry, rollback or reset. State may be uncertain.')
        except OSError:
            pass
        raise
    finally:
        journal.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=tuple(FRAMES), required=True)
    parser.add_argument('--device', required=True)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--accept-live-lighting-risk', action='store_true', required=True,
                        help='authorize a single unverified SET_FEATURE with no backup or automatic restore')
    args = parser.parse_args(argv)
    try:
        baseline, _ = load_baseline(BASELINE)
        if baseline.identity() != IDENTITY:
            raise ValueError('Baseline differs from the exact captured Blaze')
        target = select_target(enumerate_devices(), baseline, args.device)
        def recheck(selected):
            if select_target(enumerate_devices(), baseline, selected.path) != selected:
                raise ValueError('Device changed before lighting preview')
        result = preview_once(target, args.mode, args.capture, recheck, accept_risk=True)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'Lighting preview failed: {exc}. No automatic retry or restore.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
