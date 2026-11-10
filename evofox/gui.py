"""Native, read-only desktop inspector for EvoFox Blaze driver resources."""
import argparse
import sys
from pathlib import Path


def config_sections(config):
    """Build the display sections without interpreting undocumented codes."""
    sections = [('General', {'Product': config.get('product') or 'Unknown',
                             **config.get('initialization', {})}),
                ('Button mapping (raw)', config.get('key_mapping', {}))]
    for profile in config.get('profiles', []):
        name = profile.get('name') or 'Unnamed'
        sections.append((f"Profile {profile['index']} — {name}", profile['values']))
    sections.append(('Shared settings (raw)', config.get('shared_values', {})))
    return sections


def run():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        print('EvoFox: Tkinter is required for the desktop window. Install your distribution’s python3-tk package.', file=sys.stderr)
        return 1

    from .__main__ import inspect_config, scan_hid

    parser = argparse.ArgumentParser(description='EvoFox Blaze read-only desktop inspector')
    parser.add_argument('config', nargs='?', type=Path, help='extracted vendor config.ini')
    args = parser.parse_args()

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f'EvoFox: could not open a desktop window: {exc}', file=sys.stderr)
        return 1
    root.title('EvoFox Blaze — Linux Inspector')
    root.geometry('920x650')
    root.minsize(690, 470)
    style = ttk.Style(root)
    if 'clam' in style.theme_names():
        style.theme_use('clam')
    style.configure('Title.TLabel', font=('TkDefaultFont', 17, 'bold'))
    style.configure('Notice.TLabel', foreground='#855800')

    outer = ttk.Frame(root, padding=16)
    outer.pack(fill='both', expand=True)
    ttk.Label(outer, text='EvoFox Blaze', style='Title.TLabel').pack(anchor='w')
    ttk.Label(outer, text='Linux desktop inspector · early, read-only build').pack(anchor='w', pady=(2, 8))
    ttk.Label(outer, text='Mouse configuration, lighting and macros are not available yet. No settings are sent to the device.',
              style='Notice.TLabel', wraplength=860).pack(anchor='w', pady=(0, 12))

    tabs = ttk.Notebook(outer)
    tabs.pack(fill='both', expand=True)
    devices_tab = ttk.Frame(tabs, padding=12)
    config_tab = ttk.Frame(tabs, padding=12)
    tabs.add(devices_tab, text='Devices')
    tabs.add(config_tab, text='Configuration file')

    ttk.Label(devices_tab, text='HID interfaces on this computer', font=('TkDefaultFont', 11, 'bold')).pack(anchor='w')
    ttk.Label(devices_tab, text='The mouse may appear under a generic name or as several interfaces. This list is read from Linux sysfs.',
              wraplength=780).pack(anchor='w', pady=(4, 8))
    device_frame = ttk.Frame(devices_tab)
    device_frame.pack(fill='both', expand=True)
    device_list = ttk.Treeview(device_frame, columns=('node', 'name', 'vendor', 'product'), show='headings')
    for name, label, width in [('node', 'Device', 110), ('name', 'Name', 400), ('vendor', 'Vendor ID', 100), ('product', 'Product ID', 100)]:
        device_list.heading(name, text=label)
        device_list.column(name, width=width, minwidth=60, stretch=name == 'name')
    device_scroll = ttk.Scrollbar(device_frame, orient='vertical', command=device_list.yview)
    device_list.configure(yscrollcommand=device_scroll.set)
    device_list.pack(side='left', fill='both', expand=True)
    device_scroll.pack(side='right', fill='y')
    device_status = tk.StringVar()
    def refresh_devices():
        device_list.delete(*device_list.get_children())
        devices = scan_hid()
        for d in devices:
            device_list.insert('', 'end', values=(d['node'], d['name'], d['vendor_id'] or '', d['product_id'] or ''))
        device_status.set(f'{len(devices)} HID interface(s) found. Identification and device control are not yet verified.')
    controls = ttk.Frame(devices_tab)
    controls.pack(fill='x', pady=(8, 0))
    ttk.Button(controls, text='Refresh devices', command=refresh_devices).pack(side='left')
    ttk.Label(controls, textvariable=device_status, wraplength=650).pack(side='left', padx=10)

    cfg_path = tk.StringVar(value='No configuration file loaded')
    cfg_section = tk.StringVar()
    sections = {}
    header = ttk.Frame(config_tab)
    header.pack(fill='x')
    ttk.Label(header, textvariable=cfg_path, wraplength=600).pack(side='left', fill='x', expand=True)
    table_frame = ttk.Frame(config_tab)
    table_frame.pack(fill='both', expand=True, pady=(8, 0))
    table = ttk.Treeview(table_frame, columns=('key', 'value'), show='headings')
    table.heading('key', text='Setting')
    table.heading('value', text='Stored value (not a verified device command)')
    table.column('key', width=230)
    table.column('value', width=400)
    scroll = ttk.Scrollbar(table_frame, orient='vertical', command=table.yview)
    table.configure(yscrollcommand=scroll.set)
    table.pack(side='left', fill='both', expand=True)
    scroll.pack(side='right', fill='y')
    section_bar = ttk.Frame(config_tab)
    section_bar.pack(fill='x', pady=(8, 0))
    ttk.Label(section_bar, text='Section:').pack(side='left', padx=(0, 8))
    chooser = ttk.Combobox(section_bar, textvariable=cfg_section, state='readonly', width=35)
    chooser.pack(side='left')
    def show_section(event=None):
        table.delete(*table.get_children())
        for key, value in sections.get(cfg_section.get(), {}).items():
            table.insert('', 'end', values=(key, value))
    chooser.bind('<<ComboboxSelected>>', show_section)
    def load_config(path):
        try:
            data = inspect_config(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Could not load configuration', str(exc), parent=root)
            return
        sections.clear()
        sections.update(config_sections(data))
        cfg_path.set(str(path))
        chooser['values'] = tuple(sections)
        cfg_section.set(next(iter(sections)))
        show_section()
    def browse_config():
        path = filedialog.askopenfilename(parent=root, title='Open extracted vendor config.ini',
                                          filetypes=[('INI files', '*.ini'), ('All files', '*')])
        if path:
            load_config(Path(path))
    ttk.Button(header, text='Open config.ini…', command=browse_config).pack(side='right', padx=(8, 0))
    ttk.Label(config_tab, text='Extract the supplied installer with innoextract to obtain app/skins/config/config.ini. Values shown here are read-only.',
              wraplength=780).pack(anchor='w', pady=(10, 0))

    refresh_devices()
    if args.config:
        load_config(args.config)
        tabs.select(config_tab)
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(run())
