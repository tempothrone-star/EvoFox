# Investigation notes

## Evidence from this repository

* `evofox.exe` (SHA-256 `c45662764d9847e3b14c34d19a745e6b6b34a7e966889be18814cd5513c47468`) is a 32-bit Inno Setup 5.5.7 installer, not the application itself.
* Its payload contains `Gaming Mouse 3.0.exe` (SHA-256 `9eec736ee629ff9d0684f787a270afe86d064fdcf23e7eb11f921dc7844eee55`), a 32-bit native Windows program. Its imports include `HidD_GetFeature`, `HidD_SetFeature`, `HidD_GetAttributes`, and Windows SetupAPI device enumeration functions. The presence of those imports does not tell us the report formats or which interface is used.
* `skins/config/config.ini` identifies the product as **EvoFox Blaze Gaming Mouse**, lists eight buttons, four named profiles, per-profile settings and a `ShareData` section. There is also a fifth `Config4` section, whose purpose has not been established. The config stores raw numeric values; their exact relationship to on-device values is not verified.
* The UI resources name button, performance, macro, and backlight pages. Other resources include default macro data and sound lighting. Their presence alone does not establish how their protocols work.

## Missing work before hardware control

A working Linux port needs the exact vendor/product IDs and HID interface, report descriptors and lengths, initialization/handshake, read and write commands, encoding of all options, error handling, and validation on the actual mouse. Macro layout, lighting, profile persistence, and the relation of shared settings to per-profile values are not yet understood. A graphical frontend and packaging also remain to be built. Do not create broad udev rules or transmit speculative feature reports.

To continue, connect the target mouse and capture `python3 -m evofox devices --all` output (redact `unique_id` if desired). If possible, provide the report descriptors from the matching `/sys/class/hidraw/hidrawN/device/report_descriptor` files and USB captures made while the Windows application reads settings and changes **one setting at a time**. Include a baseline and the exact before/after values for each capture, plus the model/revision. Captures may contain sensitive USB identifiers or keyboard input: review and redact them before sharing. These artifacts permit report formats to be inferred and subsequently verified on hardware; they cannot prove safety on their own.
