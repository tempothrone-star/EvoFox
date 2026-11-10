# Investigation notes

## Evidence from this repository

* `evofox.exe` (SHA-256 `c45662764d9847e3b14c34d19a745e6b6b34a7e966889be18814cd5513c47468`) is a 32-bit Inno Setup 5.5.7 installer, not the application itself.
* Its payload contains `Gaming Mouse 3.0.exe` (SHA-256 `9eec736ee629ff9d0684f787a270afe86d064fdcf23e7eb11f921dc7844eee55`), a 32-bit native Windows program. Its imports include `HidD_GetFeature`, `HidD_SetFeature`, `HidD_GetAttributes`, and Windows SetupAPI device enumeration functions. The presence of those imports does not tell us the report formats or which interface is used.
* `skins/config/config.ini` identifies the product as **EvoFox Blaze Gaming Mouse**, lists eight buttons, four named profiles, per-profile settings and a `ShareData` section. There is also a fifth `Config4` section, whose purpose has not been established. The config stores raw numeric values; their exact relationship to on-device values is not verified.
* The UI resources name button, performance, macro, and backlight pages. Other resources include default macro data and sound lighting. Their presence alone does not establish how their protocols work.

## Missing work before hardware control

A working Linux port needs the exact vendor/product IDs and HID interface, report descriptors and lengths, initialization/handshake, read and write commands, encoding of all options, error handling, and validation on the actual mouse. Macro layout, lighting, profile persistence, and the relation of shared settings to per-profile values are not yet understood. A graphical frontend and packaging also remain to be built. Do not create broad udev rules or transmit speculative feature reports.

To continue, connect the target mouse and capture `python3 -m evofox devices --all` output (redact `unique_id` if desired). If possible, provide the report descriptors from the matching `/sys/class/hidraw/hidrawN/device/report_descriptor` files and USB captures made while the Windows application reads settings and changes **one setting at a time**. Include a baseline and the exact before/after values for each capture, plus the model/revision. Captures may contain sensitive USB identifiers or keyboard input: review and redact them before sharing. These artifacts permit report formats to be inferred and subsequently verified on hardware; they cannot prove safety on their own.

## User-provided Linux descriptors

The user confirmed an EvoFox Blaze, model GM862, and reported a USB `30fa:1440` device named `INSTANT USB Gaming Mouse`, with USB device revision `0100` and two interfaces under the same physical USB path. The user reported interface numbers `00` and `01` respectively. `input0` (`hidraw1` in that session) has a mouse input report, ID 1. `input1` (`hidraw2`) contains keyboard and consumer-control input collections and a vendor-defined usage page `0xff01`, usage 1, **feature report ID 7 with seven 8-bit data fields**. HID API buffers conventionally include the report ID in addition to those data bytes. `hidraw` numbers can change when devices reconnect.

The inspector checks sysfs for the supplied feature collection byte sequence and shows a *candidate feature-report interface* hint for matching USB `30fa:1440` interfaces. This is a fingerprint, not a model identification or an authorization to send reports. Other devices share this VID/PID, and an equivalent descriptor may have a different byte representation. Failure to match does not prove a device is incompatible. The Devices tab and `devices` command do not open a HID node or issue feature reports. The separately invoked experimental `status` command does send one GET_FEATURE request, as described in the README.

Independent research is available in [Aurora](https://github.com/rugbedbugg/aurora), which describes a Blaze `30fa:1440` protocol. Its protocol notes describe report ID 7 on USB interface 1, usage page 0xff01, with an eight-byte buffer including the ID; those details match the supplied descriptor. The match is promising but does not establish firmware compatibility or behavior on this particular mouse. Verify against device-specific evidence and hardware before enabling control.

## Experimental status probe

`python3 -m evofox status` requires an explicit device and Blaze confirmation. It checks the opened character device using HIDIOCGRAWINFO and HIDIOCGRDESC before requesting report 7 with HIDIOCGFEATURE. No SET_FEATURE ioctl is implemented. The implementation checks the raw return length and ID. When known markers match, it displays a provisional interpretation of polling rate, profile index and lighting effect code based on Aurora; these values are not verified on this mouse and status can be stale. Even a GET_FEATURE request can affect an ongoing read transaction, so it must not be used concurrently with other configuration tools. The tests use mocked ioctls, not real hardware.

The user-supplied full report descriptors for interfaces 00 and 01 match byte-for-byte the [independent Blaze capture](https://github.com/rahulbeyondcode/Evofox-Blaze-Linux-Port/blob/main/docs/device-captures/2026-10-23-30fa-1440-0100/probe.json), which also lists revision `0100`. This supports protocol investigation but cannot uniquely identify the model or guarantee identical firmware behavior.

The user ran the probe on a confirmed EvoFox Blaze GM862, USB revision `0100`, and returned `07 00 66 09 49 00 03 7b`. This demonstrates a successful GET_FEATURE response, not that any particular decoded value or write protocol is correct. Based on Aurora, the last two bytes *suggest* 1000 Hz polling, profile index 0 and lighting effect code 7; compare with independently observed settings before relying on that interpretation.
