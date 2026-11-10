"""Narrow GUI bridge to the separately licensed, evidence-based Blaze backend."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone
from uuid import uuid4

from evofox_blaze.buttons import ACTION_CODES, BLOCK_SLOTS

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'docs/device-captures/2026-10-23-30fa-1440-0100/probe.json'
RATES = (125, 250, 500, 1000)


def state_root():
    state = os.environ.get('XDG_STATE_HOME')
    return (Path(state) if state and Path(state).is_absolute() else Path.home() / '.local/state') / 'evofox-blaze'


def build_command(action, node, capture, *, rate=None, backup=None, slot=None, button_action=None):
    if not re.fullmatch(r'/dev/hidraw[0-9]+', str(node)):
        raise ValueError('Select a /dev/hidrawN candidate interface')
    if action == 'read' and rate is None and backup is None and slot is None and button_action is None:
        arguments = ['evofox_blaze.state_read', '--read-state', '--accept-staged-read-risk']
    elif action == 'polling' and type(rate) is int and rate in RATES and backup is None and slot is None and button_action is None:
        arguments = ['evofox_blaze.config_write', '--polling', str(rate), '--accept-write-risk']
    elif action == 'restore' and rate is None and isinstance(backup, Path) and slot is None and button_action is None:
        arguments = ['evofox_blaze.config_write', '--restore-backup', str(backup), '--accept-write-risk']
    elif action == 'button-read' and rate is None and backup is None and slot is None and button_action is None:
        arguments = ['evofox_blaze.button_read', '--read-buttons', '--accept-staged-read-risk']
    elif (action == 'button-assign' and rate is None and backup is None and type(slot) is int
          and slot in BLOCK_SLOTS and isinstance(button_action, str) and button_action in ACTION_CODES):
        arguments = ['evofox_blaze.button_write', '--assign', f'{slot}={button_action}', '--accept-write-risk']
    elif action == 'button-restore' and rate is None and isinstance(backup, Path) and slot is None and button_action is None:
        arguments = ['evofox_blaze.button_write', '--restore-backup', str(backup), '--accept-write-risk']
    else:
        raise ValueError('Invalid operation or setting')
    return [sys.executable, '-m', *arguments, '--device', str(node), '--baseline', str(BASELINE), '--capture', str(capture)]


def run_operation(action, node, *, rate=None, backup=None, slot=None, button_action=None):
    """Run a fixed backend operation once, preserving its journal on failure."""
    root = state_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    capture = root / f'{stamp}-{action}-{uuid4().hex[:8]}'
    command = build_command(action, node, capture, rate=rate, backup=backup, slot=slot, button_action=button_action)
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f'{result.stderr.strip() or "Operation failed."}\nEvidence location: {capture}\n'
                           'Do not retry blindly; the device state may be uncertain.')
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f'Invalid backend result; inspect evidence at {capture}. Do not retry blindly.') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'Invalid backend result; inspect evidence at {capture}. Do not retry blindly.')
    return payload, capture
