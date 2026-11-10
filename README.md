# EvoFox Blaze Linux investigation

This repository contains an EvoFox Blaze Gaming Mouse Windows installer, **not source code**. The Linux port is not complete. The current application includes **experimental polling-rate read/change/restore** for the exact Blaze revision and descriptor reported by the user. Button remapping, macros, lighting, DPI values and profiles are not implemented. Polling control uses independently developed, hardware-exercised research but has not been tested on this user’s physical mouse; an interrupted or incompatible operation could alter settings or make the mouse unusable.

The Linux desktop includes a device inspector and a limited experimental Performance tab. It starts without contacting a device. The separately confirmed Performance operations do send HID feature requests, and Apply and Restore write settings. The original Windows installer is extracted locally as reference data; it is not executable Linux source code.

## Launch the desktop window

Install Python 3 and Tkinter (for example, `sudo apt install python3 python3-tk` on Debian/Ubuntu), then run this on a Linux graphical desktop:

```sh
./evofox-desktop
```

Use **Refresh devices** to list HID interfaces. You can select the candidate feature-report interface and use **Read status…** to send an optional experimental GET_FEATURE request after confirmation (see the precautions below). To inspect the vendor settings, extract the installer as described below and choose **Open config.ini…** in the Configuration file tab, or launch `./evofox-desktop extracted/app/skins/config/config.ini`. The **Performance** tab provides explicit staged reads, polling changes, and scoped backup restore. See the safety notes below.

## Experimental polling control

The Performance tab targets only USB `30fa:1440`, revision `0100`, interface `01` and the exact descriptor in the bundled research baseline. Choose the candidate interface and explicitly confirm each operation. The **Read mouse state** operation sends SET_FEATURE staging requests as well as GET_FEATURE requests; it is not a passive read. **Apply polling** reads the eight-byte block, saves a durable partial backup, writes the block and checks readback. **Restore block backup** accepts an earlier `original-state.json` and refuses intervening changes. Backups cover only the affected block, not the entire mouse. Settings readback does not prove actual frequency or immediate activation; reconnecting may be required. There is no automatic retry or rollback. Close other configuration tools first; do not unplug the mouse during an operation. On failure, inspect the evidence path shown in the UI before taking further action. Evidence and partial backups are saved under `$XDG_STATE_HOME/evofox-blaze` or `~/.local/state/evofox-blaze`.

Performance operations need read **and write** access to the selected hidraw node. If needed, on systems with `setfacl`, temporarily grant only your user access to the confirmed candidate node (replace `N`): `sudo setfacl -m u:$(id -un):rw /dev/hidrawN`. This usually disappears on reconnect. Do not run the graphical program as root, and do not grant access to unrelated HID devices. Other applications do not necessarily honor the backend's cooperative lock. The backend currently supports Linux x86-64 and Python 3.10+ only. See [third-party attribution](docs/third-party.md) and [investigation notes](docs/reverse-engineering.md).

## Command-line inspection

The command-line tools require only Python 3:

```sh
python3 -m evofox devices --all
python3 -m evofox devices                 # candidate VID/PID or matching names
python3 -m evofox config /path/to/extracted/app/skins/config/config.ini
python3 -m unittest discover -s tests -v
```

The Devices tab labels a USB `30fa:1440` interface as a candidate feature-report interface if its descriptor contains the collection supplied by the user. This is not model verification and the same ID may be shared by other devices. Device names are not a reliable identification method: the mouse may have a generic name or multiple HID interfaces. `--all` is important when looking for it. Device lists may include serial/physical identifiers; review before sharing. The config command displays the stored raw codes, **not confirmed USB report values**. Profile-specific and shared fields are both shown; no attempt is made to infer which takes precedence. The parser is intended for inspection only, not round-trip editing or interpreting other vendor formats.

## Experimental device status probe

The optional `status` command is separate from the offline inspector. It opens a selected hidraw node **read-only** and sends exactly one HID GET_FEATURE request (report ID 7); it does not send SET_FEATURE or change settings. A GET still communicates with the mouse and can disturb an ongoing configuration exchange, so close the Windows utility, Wine, and other mouse configuration tools first. Only run it if you have confirmed your mouse is an EvoFox Blaze; other devices share the USB ID. The raw reply is displayed alongside a provisional interpretation of polling rate, profile index and lighting effect code when it matches the expected pattern. This interpretation is not verified and a reply can be stale.

Find the current candidate interface using `python3 -m evofox devices` and replace `N` with its number (the number can change after reconnecting):

```sh
python3 -m evofox status --device /dev/hidrawN --confirm-blaze
```

The tool validates the opened character device's USB ID and report descriptor before sending the request, and rejects malformed replies. Linux may deny access to the node. If so, you can temporarily grant your user read access to **that confirmed node only**, for example with `sudo setfacl -m u:$(id -un):r /dev/hidrawN` (requires `setfacl`). The permission usually disappears on disconnect. Do not grant access to unrelated HID devices. A single raw status request succeeded on the user's physical mouse; the meaning of the fields has not been verified on that mouse, and the protocol could differ by firmware.

## Extracting the installer

Install `innoextract` using your Linux distribution's package manager, then run:

```sh
./extract-evofox
python3 -m evofox config extracted/app/skins/config/config.ini
```

The script refuses to overwrite an existing `extracted/` directory. The desktop automatically loads the extracted `config.ini` when present. Extracted vendor files are kept out of Git; extracting does not convert the Windows executable to Linux source. See [the investigation notes](docs/reverse-engineering.md) for evidence, limitations, and what is needed to finish a safe port.
