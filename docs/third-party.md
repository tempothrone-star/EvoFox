# Third-party Blaze backend

`evofox_blaze/`, the tests `test_config_write.py`, `test_state_read.py`,
`test_feature_read.py` and their fixtures, and the two `docs/device-captures/`
fixtures and the button-related tests are from [Evofox-Blaze-Linux-Port](https://github.com/rahulbeyondcode/Evofox-Blaze-Linux-Port),
commit `7252a49b5b4f8b595a5aaa55418c99e5826a1d96`. Copyright 2026 R Rahul;
MIT license included at `evofox_blaze/LICENSE`.

The GUI exposes the fixed-block polling, enabled DPI-stage, and native-button read/change/restore workflows.
The backend matches USB ID, revision, interface and the *entire* report
 descriptor against the captured baseline; it locks the device cooperatively,
journals operations, backs up the affected eight bytes before a commit and
verifies readback. Staged reads themselves issue SET_FEATURE reports. Backups
are partial, not a complete image. The backend does not retry or automatically
roll back. The included capture is public third-party evidence, not a capture
of this user's settings. Source and tests are copied to allow offline builds;
no code is downloaded or executed at runtime.

The candidate stage-colour packing and inverted-channel interpretation are informed by [Mousekit GamePro](https://github.com/Athet-psl/mousekit-gamepro/blob/main/docs/GM500W-PROTOCOL.md), tested upstream on a different mouse model. Its MIT license and copyright notice are included in `docs/licenses/mousekit-gamepro-MIT.txt`. The fixed Blaze live frames are documented by [Aurora](https://github.com/rugbedbugg/aurora/blob/main/docs/protocol.txt). Neither source validates the new colour/brightness requests on this user’s mouse.
