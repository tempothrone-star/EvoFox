import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evofox.polling import build_command, run_operation
from evofox_blaze.config_write import plan_change


class PollingBridgeTests(unittest.TestCase):
    def test_commands_are_narrow_and_explicit(self):
        read = build_command('read', '/dev/hidraw2', Path('/tmp/capture'))
        self.assertIn('--accept-staged-read-risk', read)
        write = build_command('polling', '/dev/hidraw2', Path('/tmp/capture'), rate=500)
        self.assertIn('--accept-write-risk', write)
        self.assertIn('--polling', write)
        self.assertNotIn('--accept-activation-risk', write)
        stage = build_command('dpi-stage', '/dev/hidraw2', Path('/tmp/capture'), dpi_stage=4)
        self.assertEqual(stage[stage.index('--dpi-stage') + 1], '4')
        self.assertIn('--accept-write-risk', stage)
        self.assertNotIn('--accept-activation-risk', stage)
        restore = build_command('restore', '/dev/hidraw2', Path('/tmp/capture'), backup=Path('/tmp/original-state.json'))
        self.assertIn('--restore-backup', restore)
        read_buttons = build_command('button-read', '/dev/hidraw2', Path('/tmp/capture'))
        self.assertIn('--accept-staged-read-risk', read_buttons)
        assign = build_command('button-assign', '/dev/hidraw2', Path('/tmp/capture'), slot=4, button_action='back')
        self.assertIn('4=back', assign)
        self.assertNotIn('--accept-activation-risk', assign)
        restore_buttons = build_command('button-restore', '/dev/hidraw2', Path('/tmp/capture'), backup=Path('/tmp/button-backup.json'))
        self.assertIn('--restore-backup', restore_buttons)
        for kwargs in ({'action':'polling','node':'/dev/hidraw2','rate': True},
                       {'action':'polling','node':'/dev/input/event0','rate': 500},
                       {'action':'read','node':'/dev/hidraw2','rate': 125},
                       {'action':'button-assign','node':'/dev/hidraw2','slot': 9,'button_action':'back'},
                       {'action':'button-assign','node':'/dev/hidraw2','slot': 4,'button_action':'arbitrary'},
                       {'action':'dpi-stage','node':'/dev/hidraw2','dpi_stage': True},
                       {'action':'dpi-stage','node':'/dev/hidraw2','dpi_stage': 6},
                       {'action':'dpi-stage','node':'/dev/hidraw2','dpi_stage': 1,'rate': 500},
                       {'action':'read','node':'/dev/hidraw2','dpi_stage': 1}):
            with self.assertRaises(ValueError):
                build_command(capture=Path('/tmp/capture'), **kwargs)

    def test_user_staged_read_produces_no_change_at_1000_hz(self):
        data = bytes.fromhex('19 3f 32 00 f3 ff 00 00')
        self.assertEqual(plan_change(data, 'polling', 1000), data)
        self.assertEqual(plan_change(data, 'polling', 500)[6], 1)

    def test_user_stage_preserves_other_bytes_and_refuses_disabled(self):
        data = bytes.fromhex('19 3f 32 00 f3 ff 00 00')
        self.assertEqual(plan_change(data, 'dpi-stage', 1), data)
        changed = plan_change(data, 'dpi-stage', 4)
        self.assertEqual(changed, bytes.fromhex('1c 3f 32 00 f3 ff 00 00'))
        with self.assertRaises(ValueError):
            plan_change(bytes.fromhex('19 02 32 00 f3 ff 00 00'), 'dpi-stage', 4)

    def test_backend_success_and_failure_preserve_evidence_location(self):
        with tempfile.TemporaryDirectory() as tmp, patch('evofox.polling.state_root', return_value=Path(tmp)):
            with patch('evofox.polling.subprocess.run', return_value=subprocess.CompletedProcess([], 0, json.dumps({'outcome':'no-change'}), '')) as run:
                data, capture = run_operation('polling', '/dev/hidraw2', rate=500)
                self.assertEqual(data['outcome'], 'no-change')
                self.assertEqual(capture.parent, Path(tmp))
                self.assertNotIn('shell', run.call_args.kwargs)
            with patch('evofox.polling.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'failure')):
                with self.assertRaisesRegex(RuntimeError, 'Do not retry blindly'):
                    run_operation('read', '/dev/hidraw2')
