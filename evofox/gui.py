"""Native, read-only desktop inspector for EvoFox Blaze driver resources."""
import argparse
import queue
import sys
import threading
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
    from .status import get_status, interpret_status
    from .polling import run_operation

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
    ttk.Label(outer, text='Linux desktop · experimental polling control').pack(anchor='w', pady=(2, 8))
    ttk.Label(outer, text='Experimental polling control is available. Lighting, buttons and macros are not implemented.',
              style='Notice.TLabel', wraplength=860).pack(anchor='w', pady=(0, 12))

    tabs = ttk.Notebook(outer)
    tabs.pack(fill='both', expand=True)
    devices_tab = ttk.Frame(tabs, padding=12)
    config_tab = ttk.Frame(tabs, padding=12)
    performance_tab = ttk.Frame(tabs, padding=12)
    tabs.add(devices_tab, text='Devices')
    tabs.add(performance_tab, text='Performance')
    tabs.add(config_tab, text='Configuration file')

    ttk.Label(devices_tab, text='HID interfaces on this computer', font=('TkDefaultFont', 11, 'bold')).pack(anchor='w')
    ttk.Label(devices_tab, text='The mouse may appear under a generic name or as several interfaces. This list is read from Linux sysfs.',
              wraplength=780).pack(anchor='w', pady=(4, 8))
    device_frame = ttk.Frame(devices_tab)
    device_frame.pack(fill='both', expand=True)
    device_list = ttk.Treeview(device_frame, columns=('node', 'name', 'vendor', 'product', 'hint'), show='headings')
    for name, label, width in [('node', 'Device', 110), ('name', 'Name', 220), ('vendor', 'Vendor ID', 80), ('product', 'Product ID', 80), ('hint', 'Interface hint', 260)]:
        device_list.heading(name, text=label)
        device_list.column(name, width=width, minwidth=60, stretch=name in ('name', 'hint'))
    device_scroll = ttk.Scrollbar(device_frame, orient='vertical', command=device_list.yview)
    device_list.configure(yscrollcommand=device_scroll.set)
    device_list.pack(side='left', fill='both', expand=True)
    device_scroll.pack(side='right', fill='y')
    device_status = tk.StringVar()
    busy = False
    operation_buttons = []
    def on_close():
        if busy:
            messagebox.showwarning('Operation in progress', 'Wait for the device operation to finish. Do not disconnect the mouse.', parent=root)
        else:
            root.destroy()
    root.protocol('WM_DELETE_WINDOW', on_close)
    def start_task(task, done):
        nonlocal busy
        if busy:
            return
        busy = True
        for button in operation_buttons:
            button.state(['disabled'])
        result_queue = queue.Queue(maxsize=1)
        def worker():
            try:
                result_queue.put((task(), None))
            except Exception as exc:
                result_queue.put((None, str(exc)))
        def poll_result():
            nonlocal busy
            try:
                result, error = result_queue.get_nowait()
            except queue.Empty:
                root.after(100, poll_result)
                return
            busy = False
            for button in operation_buttons:
                button.state(['!disabled'])
            done(result, error)
        threading.Thread(target=worker, daemon=True).start()
        root.after(100, poll_result)
    def refresh_devices():
        device_list.delete(*device_list.get_children())
        devices = scan_hid()
        for d in devices:
            device_list.insert('', 'end', values=(d['node'], d['name'], d['vendor_id'] or '', d['product_id'] or '', d['interface_hint']))
        candidates = [d['node'] for d in devices if d['interface_hint'] == 'candidate feature-report interface']
        candidate_box['values'] = candidates
        if selected_node.get() not in candidates:
            selected_node.set(candidates[0] if len(candidates) == 1 else '')
        device_status.set(f'{len(devices)} HID interface(s) found. Hints are not model verification.')
    controls = ttk.Frame(devices_tab)
    controls.pack(fill='x', pady=(8, 0))
    refresh_button = ttk.Button(controls, text='Refresh devices', command=refresh_devices)
    refresh_button.pack(side='left')
    operation_buttons.append(refresh_button)
    ttk.Label(controls, textvariable=device_status, wraplength=500).pack(side='left', padx=10)
    status_line = tk.StringVar(value='Select the candidate feature-report interface to request status.')
    ttk.Label(devices_tab, textvariable=status_line, wraplength=780, justify='left').pack(anchor='w', pady=(8, 0))

    def request_status():
        selected = device_list.selection()
        if len(selected) != 1:
            messagebox.showinfo('Select an interface', 'Select one candidate feature-report interface first.', parent=root)
            return
        node, _, _, _, hint = device_list.item(selected[0], 'values')
        if hint != 'candidate feature-report interface':
            messagebox.showerror('Wrong interface', 'Select the candidate feature-report interface.', parent=root)
            return
        if not messagebox.askyesno('Experimental status request',
                f'Confirm that {node} belongs to your EvoFox Blaze. Close other mouse configuration tools first.\n\n'
                'Send one GET_FEATURE request? No settings writes will be sent.', parent=root):
            return
        status_line.set(f'Requesting status from {node}…')
        def completed(reply, error):
            if error:
                status_line.set(f'Status request failed: {error}. See README for permissions.')
                return
            tentative = interpret_status(reply)
            text = f'{node} · raw report: {reply.hex(" ")}'
            if tentative is None:
                text += '\nReply does not match the known status pattern; no decoding is available.'
            else:
                text += (f"\nProvisional: {tentative['polling_hz']} Hz polling · "
                         f"profile index {tentative['profile_index']} · lighting code {tentative['lighting_effect_code']}")
            status_line.set(text + '\nInterpretation is unverified and the reply may be stale.')
        start_task(lambda: get_status(node, confirmed=True), completed)
    status_button = ttk.Button(controls, text='Read status…', command=request_status)
    status_button.pack(side='right')
    operation_buttons.append(status_button)

    ttk.Label(performance_tab, text='Polling rate · experimental', font=('TkDefaultFont', 11, 'bold')).pack(anchor='w')
    ttk.Label(performance_tab, text='Only USB 30fa:1440 revision 0100 with the exact known interface descriptor is supported. '
              'Each operation requires confirmation. Close other mouse tools first.', wraplength=780).pack(anchor='w', pady=(5, 12))
    device_row = ttk.Frame(performance_tab)
    device_row.pack(fill='x', pady=(0, 8))
    ttk.Label(device_row, text='Feature interface:').pack(side='left', padx=(0, 8))
    selected_node = tk.StringVar()
    candidate_box = ttk.Combobox(device_row, state='readonly', textvariable=selected_node, width=22)
    candidate_box.pack(side='left')
    ttk.Label(device_row, text='Refresh on the Devices tab if it changes.').pack(side='left', padx=10)
    rate_row = ttk.Frame(performance_tab)
    rate_row.pack(fill='x', pady=8)
    ttk.Label(rate_row, text='Target polling rate:').pack(side='left', padx=(0, 8))
    selected_rate = tk.StringVar(value='500')
    ttk.Combobox(rate_row, state='readonly', textvariable=selected_rate, values=('125', '250', '500', '1000'), width=10).pack(side='left')
    ttk.Label(rate_row, text='Hz (frequency is not independently measured)').pack(side='left', padx=8)
    perf_status = tk.StringVar(value='No operation performed. The mouse is not contacted at startup.')
    ttk.Label(performance_tab, textvariable=perf_status, wraplength=780, justify='left').pack(anchor='w', pady=12)
    perf_controls = ttk.Frame(performance_tab)
    perf_controls.pack(anchor='w', pady=8)

    def perform_polling(action):
        node = selected_node.get()
        if not node:
            messagebox.showerror('Select an interface', 'Refresh devices and choose the candidate feature interface.', parent=root)
            return
        backup = None
        if action == 'restore':
            path = filedialog.askopenfilename(parent=root, title='Select original-state.json backup',
                                              filetypes=[('JSON backup', '*.json'), ('All files', '*')])
            if not path:
                return
            backup = Path(path)
        warnings = {
            'read': 'A staged eight-byte read sends SET_FEATURE and GET_FEATURE requests, even though it does not commit a setting. Effects are experimental.',
            'polling': f'This will commit a polling setting of {selected_rate.get()} Hz. The backend makes a partial 8-byte backup and checks readback; it cannot guarantee recovery or measured frequency.',
            'restore': 'This will attempt to restore the selected partial backup. It will refuse intervening changes, but cannot guarantee recovery.'
        }
        if not messagebox.askyesno('Experimental device operation',
                f"{warnings[action]}\n\nConfirm {node} is your EvoFox Blaze GM862. Close all other mouse configuration tools. "
                'Do not unplug while the operation runs. Continue?', parent=root):
            return
        rate = int(selected_rate.get()) if action == 'polling' else None
        perf_status.set(f'Working on {node}. Keep the mouse connected…')
        def completed(result, error):
            if error:
                perf_status.set('Operation failed. Device state may be uncertain; do not retry blindly. See the error and journal.')
                messagebox.showerror('Device operation failed', error, parent=root)
                return
            payload, capture = result
            if action == 'read':
                text = (f"Read block: {payload.get('collected_hex', 'unknown')}\n"
                        f"Candidate polling: {payload.get('polling_hz_candidate', 'unknown')} Hz; "
                        f"DPI stage index: {payload.get('dpi_stage_selector_candidate', 'unknown')}.")
            else:
                text = (f"Outcome: {payload.get('outcome', 'unknown')}. "
                        'Readback is not proof of physical polling frequency or immediate activation.')
                if payload.get('backup_file'):
                    text += f"\nPartial backup: {capture / payload['backup_file']}"
            perf_status.set(text + f'\nEvidence: {capture}')
        start_task(lambda: run_operation(action, node, rate=rate, backup=backup), completed)

    for label, action in [('Read mouse state…', 'read'), ('Apply polling…', 'polling'), ('Restore block backup…', 'restore')]:
        button = ttk.Button(perf_controls, text=label, command=lambda a=action: perform_polling(a))
        button.pack(side='left', padx=(0, 8))
        operation_buttons.append(button)
    ttk.Label(performance_tab, text='All device operations require confirmation. Staged reads also send SET_FEATURE. A backup covers one 8-byte block, not the whole mouse. '
              'No automatic retry or rollback. Activation may require reconnecting the mouse.', wraplength=780,
              style='Notice.TLabel').pack(anchor='w', pady=8)

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
    else:
        extracted_config = Path(__file__).resolve().parents[1] / 'extracted/app/skins/config/config.ini'
        if extracted_config.is_file():
            load_config(extracted_config)
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(run())
