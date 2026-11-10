# EvoFox Blaze Linux investigation

This repository contains an EvoFox Blaze Gaming Mouse Windows installer, **not source code**. The Linux port is not complete. In particular, there is currently **no device configuration, macro recording, lighting control, or working mouse-control GUI**. Do not expect changes to the mouse from these tools. The USB feature-report protocol has not yet been verified against this physical mouse; sending guessed commands could alter device settings or make a mouse unusable.

The current native Linux program is a **read-only desktop inspector**, not yet a mouse configuration application. It lists HID interfaces through sysfs and displays the Windows driver's extracted configuration without changing it or opening a device node.

## Launch the desktop window

Install Python 3 and Tkinter (for example, `sudo apt install python3 python3-tk` on Debian/Ubuntu), then run this on a Linux graphical desktop:

```sh
./evofox-desktop
```

Use **Refresh devices** to list HID interfaces. You can select the candidate feature-report interface and use **Read status…** to send an optional experimental GET_FEATURE request after confirmation (see the precautions below). To inspect the vendor settings, extract the installer as described below and choose **Open config.ini…** in the Configuration file tab, or launch `./evofox-desktop extracted/app/skins/config/config.ini`. This window cannot apply settings to the mouse.

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

Install `innoextract` using your Linux distribution's package manager, then:

```sh
mkdir -p extracted
innoextract -d extracted evofox.exe
python3 -m evofox config extracted/app/skins/config/config.ini
```

Keep extracted files out of the repository. See [the investigation notes](docs/reverse-engineering.md) for evidence, limitations, and what is needed to finish a safe port.
