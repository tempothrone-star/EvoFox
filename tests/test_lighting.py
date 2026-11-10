import contextlib
from dataclasses import replace
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evofox.lighting import FRAMES, build_frame, preview_once
from evofox.polling import build_command
from evofox_blaze.feature_read import load_baseline
from evofox_blaze.state_read import SET_FEATURE

BASELINE = Path(__file__).resolve().parents[1] / 'docs/device-captures/2026-10-23-30fa-1440-0100/probe.json'


class LightingTests(unittest.TestCase):
    def setUp(self):
        self.target, _ = load_baseline(BASELINE)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.capture = Path(self.tmp.name) / 'capture'

    @contextlib.contextmanager
    def handle(self, target, record, recheck, *, writable=False):
        self.assertTrue(writable)
        self.assertEqual(target, self.target)
        recheck(target)
        yield 42

    def test_brightness_changes_only_observed_field(self):
        for level in range(8):
            frame = build_frame('brightness', brightness_code=level)
            self.assertEqual(frame[:5], FRAMES['light-on'][:5])
            self.assertEqual(frame[5], level)
            self.assertEqual(frame[6:], FRAMES['light-on'][6:])
        self.assertEqual(build_frame('brightness', brightness_code=4), FRAMES['light-on'])

    def test_stage_colour_packs_inverted_rgb(self):
        self.assertEqual(build_frame('stage-colour', stage=0, colour='#00ff00'), bytes.fromhex('07 14 00 ff 00 00 00 00'))
        self.assertEqual(build_frame('stage-colour', stage=1, colour='#ff0000'), bytes.fromhex('07 14 2f 0f 00 00 00 00'))
        self.assertEqual(build_frame('stage-colour', stage=5, colour='#ffffff'), bytes.fromhex('07 14 a0 00 00 00 00 00'))

    def test_invalid_light_parameters_fail_before_io(self):
        invalid = [
            ('brightness', {'brightness_code': True}), ('brightness', {'brightness_code': 8}),
            ('brightness', {'brightness_code': 4, 'colour': '#ffffff'}),
            ('stage-colour', {'stage': True, 'colour': '#ffffff'}),
            ('stage-colour', {'stage': 6, 'colour': '#ffffff'}),
            ('stage-colour', {'stage': 0, 'colour': '#gggggg'}),
            ('light-on', {'brightness_code': 4}), ('stage-colour', {'stage': 1}),
        ]
        for mode, params in invalid:
            with self.subTest(mode=mode, params=params), self.assertRaises(ValueError):
                build_frame(mode, **params)

    def test_parameterised_frame_sends_one_request(self):
        expected = build_frame('stage-colour', stage=1, colour='#ff0000')
        def ioctl(fd, request, buffer, mutate):
            self.assertEqual((fd, request, bytes(buffer)), (42, SET_FEATURE, expected))
            return 8
        with patch('evofox.lighting.validated_handle', self.handle), \
                patch('evofox.lighting.fcntl.ioctl', side_effect=ioctl) as call:
            result = preview_once(self.target, 'stage-colour', self.capture, lambda _: None,
                                  accept_risk=True, stage=1, colour='#ff0000')
            self.assertEqual(result['frame_hex'], expected.hex(' '))
            self.assertEqual(call.call_count, 1)

    def test_explicit_frames_only_and_intent_journaled(self):
        for mode in FRAMES:
            capture = self.capture.parent / mode
            def ioctl(fd, op, buf, mutate):
                self.assertEqual(fd, 42)
                self.assertEqual(op, SET_FEATURE)
                self.assertTrue(mutate)
                self.assertEqual(bytes(buf), FRAMES[mode])
                events = [json.loads(line)['event'] for line in (capture / 'lighting-preview.jsonl').read_text().splitlines()]
                self.assertEqual(events[-1], 'lighting_request_intent')
                return 8
            with self.subTest(mode=mode), patch('evofox.lighting.validated_handle', self.handle), \
                    patch('evofox.lighting.fcntl.ioctl', side_effect=ioctl) as mock:
                result = preview_once(self.target, mode, capture, lambda target: None, accept_risk=True)
                self.assertEqual(mock.call_count, 1)
                self.assertEqual(result['outcome'], 'request-sent')
                self.assertFalse(result['hardware_behavior_verified'])
                self.assertFalse(result['automatic_restore'])

    def test_requires_consent_and_rejects_arbitrary_modes_before_open(self):
        with patch('evofox.lighting.validated_handle') as handle:
            with self.assertRaises(ValueError):
                preview_once(self.target, 'light-on', self.capture, lambda _: None)
            with self.assertRaises(ValueError):
                preview_once(self.target, 'other', self.capture, lambda _: None, accept_risk=True)
            self.assertFalse(self.capture.exists())
            handle.assert_not_called()

    def test_incorrect_identity_refused_before_any_request(self):
        wrong = replace(self.target, revision='0200')
        with patch('evofox.lighting.validated_handle') as handle, patch('evofox.lighting.fcntl.ioctl') as ioctl:
            with self.assertRaises(ValueError):
                preview_once(wrong, 'light-on', self.capture, lambda _: None, accept_risk=True)
            handle.assert_not_called()
            ioctl.assert_not_called()
            self.assertFalse(self.capture.exists())

    def test_recheck_failure_never_sends_a_report(self):
        def fail(_):
            raise ValueError('Device changed')
        with patch('evofox.lighting.validated_handle', self.handle), patch('evofox.lighting.fcntl.ioctl') as ioctl:
            with self.assertRaises(ValueError):
                preview_once(self.target, 'light-on', self.capture, fail, accept_risk=True)
            ioctl.assert_not_called()

    def test_short_reply_does_not_retry_and_records_failure(self):
        with patch('evofox.lighting.validated_handle', self.handle), \
                patch('evofox.lighting.fcntl.ioctl', return_value=4) as ioctl:
            with self.assertRaises(ValueError):
                preview_once(self.target, 'light-on', self.capture, lambda _: None, accept_risk=True)
            self.assertEqual(ioctl.call_count, 1)
        events = [json.loads(line)['event'] for line in (self.capture / 'lighting-preview.jsonl').read_text().splitlines()]
        self.assertIn('lighting_failed', events)
        self.assertNotIn('lighting_complete', events)

    def test_failed_intent_log_prevents_feature_request(self):
        class FailingJournal:
            def __init__(self, path):
                self.path = path
            def record(self, event, **fields):
                if event == 'lighting_request_intent':
                    raise OSError('disk error')
            def close(self):
                pass
        with patch('evofox.lighting.validated_handle', self.handle), \
                patch('evofox.lighting.Journal', FailingJournal), patch('evofox.lighting.fcntl.ioctl') as ioctl:
            with self.assertRaises(OSError):
                preview_once(self.target, 'light-on', self.capture, lambda _: None, accept_risk=True)
            ioctl.assert_not_called()

    def test_changed_buffer_is_failure(self):
        def ioctl(fd, request, buffer, mutate):
            buffer[1] = 0
            return 8
        with patch('evofox.lighting.validated_handle', self.handle), \
                patch('evofox.lighting.fcntl.ioctl', side_effect=ioctl) as call:
            with self.assertRaises(ValueError):
                preview_once(self.target, 'light-on', self.capture, lambda _: None, accept_risk=True)
            self.assertEqual(call.call_count, 1)

    def test_bridge_restricts_options_and_has_explicit_ack(self):
        cmd = build_command('lighting', '/dev/hidraw2', self.capture, light_mode='light-off')
        self.assertIn('--accept-live-lighting-risk', cmd)
        colour = build_command('lighting', '/dev/hidraw2', self.capture,
                               light_mode='stage-colour', light_stage=1, light_colour='#ff0000')
        self.assertIn('#ff0000', colour)
        brightness = build_command('lighting', '/dev/hidraw2', self.capture,
                                   light_mode='brightness', light_level=3)
        self.assertIn('--brightness-code', brightness)
        with self.assertRaises(ValueError):
            build_command('lighting', '/dev/hidraw2', self.capture, light_mode='brightness', light_level=9)
        with self.assertRaises(ValueError):
            build_command('lighting', '/dev/hidraw2', self.capture, light_mode='00 00')
        with self.assertRaises(ValueError):
            build_command('read', '/dev/hidraw2', self.capture, light_mode='light-on')
