# EvoFox Blaze Linux investigation

This repository contains an EvoFox Blaze Gaming Mouse Windows installer, **not source code**. The Linux port is not complete. In particular, there is currently **no device configuration, macro recording, lighting control, or working mouse-control GUI**. Do not expect changes to the mouse from these tools. The USB feature-report protocol and the correct device/interface IDs have not yet been established or tested against hardware; sending guessed commands could alter device settings or make a mouse unusable.

The current native Linux program is a **read-only desktop inspector**, not yet a mouse configuration application. It lists HID interfaces through sysfs and displays the Windows driver's extracted configuration without changing it or opening a device node.

## Launch the desktop window

Install Python 3 and Tkinter (for example, `sudo apt install python3 python3-tk` on Debian/Ubuntu), then run this on a Linux graphical desktop:

```sh
./evofox-desktop
```

Use **Refresh devices** to list HID interfaces. To inspect the vendor settings, extract the installer as described below and choose **Open config.ini…** in the Configuration file tab, or launch `./evofox-desktop extracted/app/skins/config/config.ini`. This window cannot apply settings to the mouse.

## Command-line inspection

The command-line tools require only Python 3:

```sh
python3 -m evofox devices --all
python3 -m evofox devices                 # names containing EvoFox or Blaze only
python3 -m evofox config /path/to/extracted/app/skins/config/config.ini
python3 -m unittest discover -s tests -v
```

Device names are not a reliable identification method: the mouse may have a generic name or multiple HID interfaces. `--all` is important when looking for it. Device lists may include serial/physical identifiers; review before sharing. The config command displays the stored raw codes, **not confirmed USB report values**. Profile-specific and shared fields are both shown; no attempt is made to infer which takes precedence. The parser is intended for inspection only, not round-trip editing or interpreting other vendor formats.

## Extracting the installer

Install `innoextract` using your Linux distribution's package manager, then:

```sh
mkdir -p extracted
innoextract -d extracted evofox.exe
python3 -m evofox config extracted/app/skins/config/config.ini
```

Keep extracted files out of the repository. See [the investigation notes](docs/reverse-engineering.md) for evidence, limitations, and what is needed to finish a safe port.
