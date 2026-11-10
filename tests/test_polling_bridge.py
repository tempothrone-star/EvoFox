import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evofox.polling import build_command, run_operation


class PollingBridgeTests(unittest.TestCase):
    def test_commands_are_narrow_and_explicit(self):
        read = build_command('read', '/dev/hidraw2', Path('/tmp/capture'))
        self.assertIn('--accept-staged-read-risk', read)
        write = build_command('polling', '/dev/hidraw2', Path('/tmp/capture'), rate=500)
        self.assertIn('--accept-write-risk', write)
        self.assertIn('--polling', write)
        self.assertNotIn('--accept-activation-risk', write)
        restore = build_command('restore', '/dev/hidraw2', Path('/tmp/capture'), backup=Path('/tmp/original-state.json'))
        self.assertIn('--restore-backup', restore)
        for kwargs in ({'action':'polling','node':'/dev/hidraw2','rate': True},
                       {'action':'polling','node':'/dev/input/event0','rate': 500},
                       {'action':'read','node':'/dev/hidraw2','rate': 125}):
            with self.assertRaises(ValueError):
                build_command(capture=Path('/tmp/capture'), **kwargs)

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
