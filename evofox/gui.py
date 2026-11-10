"""Native Linux EvoFox inspector and experimental device controls."""
import argparse
import os
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


def parse_polling_choice(value):
    """Never interpret an empty or unknown target as the current setting."""
    if value not in ('125', '250', '500', '1000'):
        raise ValueError('Select a target polling rate first.')
    return int(value)


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
    from evofox_blaze.buttons import ACTION_CODES, ACTION_LABELS, BLOCK_SLOTS

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
    ttk.Label(outer, text='Linux desktop · experimental device controls').pack(anchor='w', pady=(2, 8))
    ttk.Label(outer, text='Polling, DPI stage, buttons and limited live lighting are experimental. Macros are not implemented.',
              style='Notice.TLabel', wraplength=860).pack(anchor='w', pady=(0, 12))

    if os.geteuid() == 0:
        ttk.Label(outer, text='Running as root: evidence will be saved under /root. Prefer running as your normal user; see README for device permissions.',
                  style='Notice.TLabel', wraplength=860).pack(anchor='w', pady=(0, 8))

    tabs = ttk.Notebook(outer)
    tabs.pack(fill='both', expand=True)
    devices_tab = ttk.Frame(tabs, padding=12)
    config_tab = ttk.Frame(tabs, padding=12)
    performance_tab = ttk.Frame(tabs, padding=12)
    buttons_tab = ttk.Frame(tabs, padding=12)
    lighting_tab = ttk.Frame(tabs, padding=12)
    tabs.add(devices_tab, text='Devices')
    tabs.add(buttons_tab, text='Buttons')
    tabs.add(performance_tab, text='Performance')
    tabs.add(lighting_tab, text='Lighting')
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
        button_device_box['values'] = candidates
        lighting_device_box['values'] = candidates
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

    ttk.Label(performance_tab, text='Performance · experimental', font=('TkDefaultFont', 11, 'bold')).pack(anchor='w')
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
    selected_rate = tk.StringVar(value='')
    ttk.Combobox(rate_row, state='readonly', textvariable=selected_rate, values=('125', '250', '500', '1000'), width=10).pack(side='left')
    ttk.Label(rate_row, text='Hz (choose target; not a current reading)').pack(side='left', padx=8)
    stage_row = ttk.Frame(performance_tab)
    stage_row.pack(fill='x', pady=8)
    ttk.Label(stage_row, text='Enabled DPI stage:').pack(side='left', padx=(0, 8))
    stage_var = tk.StringVar()
    stage_box = ttk.Combobox(stage_row, state='readonly', textvariable=stage_var, width=19)
    stage_box.pack(side='left')
    ttk.Label(stage_row, text='Read state first. Stage index is not a DPI value.').pack(side='left', padx=8)
    stage_read_node = None
    enabled_stages = ()
    def invalidate_stages(*_):
        nonlocal stage_read_node, enabled_stages
        stage_read_node = None
        enabled_stages = ()
        stage_box['values'] = ()
        stage_var.set('')
    selected_node.trace_add('write', invalidate_stages)
    perf_status = tk.StringVar(value='No operation performed. The mouse is not contacted at startup.')
    ttk.Label(performance_tab, textvariable=perf_status, wraplength=780, justify='left').pack(anchor='w', pady=12)
    perf_controls = ttk.Frame(performance_tab)
    perf_controls.pack(anchor='w', pady=8)

    def perform_polling(action):
        nonlocal stage_read_node, enabled_stages
        node = selected_node.get()
        if not node:
            messagebox.showerror('Select an interface', 'Refresh devices and choose the candidate feature interface.', parent=root)
            return
        backup = None
        dpi_stage = None
        rate = None
        if action == 'polling':
            try:
                rate = parse_polling_choice(selected_rate.get())
            except ValueError as exc:
                messagebox.showerror('Choose a polling rate', str(exc), parent=root)
                return
        if action == 'dpi-stage':
            options = {f'Stage {i + 1} (index {i})': i for i in enabled_stages}
            if stage_read_node != node or stage_var.get() not in options:
                messagebox.showerror('Read state first', 'Read the selected mouse state, then choose an enabled stage.', parent=root)
                return
            dpi_stage = options[stage_var.get()]
        if action == 'restore':
            path = filedialog.askopenfilename(parent=root, title='Select original-state.json backup',
                                              filetypes=[('JSON backup', '*.json'), ('All files', '*')])
            if not path:
                return
            backup = Path(path)
        warnings = {
            'read': 'A staged eight-byte read sends SET_FEATURE and GET_FEATURE requests, even though it does not commit a setting. Effects are experimental.',
            'polling': f'This will commit a polling setting of {selected_rate.get()} Hz. The backend makes a partial 8-byte backup and checks readback; it cannot guarantee recovery or measured frequency.',
            'dpi-stage': f'This will select DPI stage index {dpi_stage}, not change its DPI value. The backend makes a partial 8-byte backup and checks readback; behavior on this mouse has not been verified.',
            'restore': 'This will attempt to restore the selected partial backup. It will refuse intervening changes, but cannot guarantee recovery.'
        }
        if not messagebox.askyesno('Experimental device operation',
                f"{warnings[action]}\n\nConfirm {node} is your EvoFox Blaze GM862. Close all other mouse configuration tools. "
                'Do not unplug while the operation runs. Continue?', parent=root):
            return
        invalidate_stages()
        perf_status.set(f'Working on {node}. Keep the mouse connected…')
        def completed(result, error):
            nonlocal stage_read_node, enabled_stages
            if error:
                perf_status.set('Operation failed. Device state may be uncertain; do not retry blindly. See the error and journal.')
                messagebox.showerror('Device operation failed', error, parent=root)
                return
            payload, capture = result
            if action == 'read':
                stages = payload.get('enabled_stage_indices_candidate')
                if (selected_node.get() == node and isinstance(stages, list)
                        and all(type(i) is int and 0 <= i <= 5 for i in stages)
                        and len(set(stages)) == len(stages)):
                    enabled_stages = tuple(sorted(stages))
                    stage_read_node = node
                    stage_box['values'] = tuple(f'Stage {i + 1} (index {i})' for i in enabled_stages)
                    current = payload.get('dpi_stage_selector_candidate')
                    if type(current) is int and current in enabled_stages:
                        stage_var.set(f'Stage {current + 1} (index {current})')
                text = (f"Read block: {payload.get('collected_hex', 'unknown')}\n"
                        f"Candidate polling: {payload.get('polling_hz_candidate', 'unknown')} Hz; "
                        f"DPI stage index: {payload.get('dpi_stage_selector_candidate', 'unknown')}.")
            else:
                text = (f"Outcome: {payload.get('outcome', 'unknown')}. "
                        'Readback is not proof of physical polling frequency or immediate activation.')
                if payload.get('backup_file'):
                    text += f"\nPartial backup: {capture / payload['backup_file']}"
            perf_status.set(text + f'\nEvidence: {capture}')
        start_task(lambda: run_operation(action, node, rate=rate, backup=backup, dpi_stage=dpi_stage), completed)

    for label, action in [('Read mouse state…', 'read'), ('Apply polling…', 'polling'), ('Apply DPI stage…', 'dpi-stage'), ('Restore block backup…', 'restore')]:
        button = ttk.Button(perf_controls, text=label, command=lambda a=action: perform_polling(a))
        button.pack(side='left', padx=(0, 8))
        operation_buttons.append(button)
    ttk.Label(performance_tab, text='All device operations require confirmation. Staged reads also send SET_FEATURE. A backup covers one 8-byte block, not the whole mouse. '
              'No automatic retry or rollback. Activation may require reconnecting the mouse.', wraplength=780,
              style='Notice.TLabel').pack(anchor='w', pady=8)

    ttk.Label(buttons_tab, text='Native button assignments · experimental', font=('TkDefaultFont', 11, 'bold')).pack(anchor='w')
    ttk.Label(buttons_tab, text='Read the mouse first. Slot numbers and vendor UI positions are candidates, not verified physical button locations. '
              'Slot 9 is unsupported; macros and shortcut records are not editable.', wraplength=800).pack(anchor='w', pady=(4, 8))
    button_device_row = ttk.Frame(buttons_tab)
    button_device_row.pack(fill='x')
    ttk.Label(button_device_row, text='Feature interface:').pack(side='left', padx=(0, 8))
    button_device_box = ttk.Combobox(button_device_row, state='readonly', textvariable=selected_node, width=22)
    button_device_box.pack(side='left')
    ttk.Label(button_device_row, text='Shared with Performance tab.').pack(side='left', padx=10)
    button_table = ttk.Treeview(buttons_tab, columns=('slot', 'ui', 'raw', 'candidate'), show='headings', height=7, selectmode='browse')
    for column, label, width in [('slot', 'Native slot', 90), ('ui', 'Vendor UI position', 160), ('raw', 'Raw', 80), ('candidate', 'Candidate action', 250)]:
        button_table.heading(column, text=label)
        button_table.column(column, width=width, minwidth=60)
    button_table.pack(fill='both', expand=True, pady=(8, 0))
    assign_row = ttk.Frame(buttons_tab)
    assign_row.pack(fill='x', pady=(8, 0))
    ttk.Label(assign_row, text='New action:').pack(side='left', padx=(0, 8))
    action_var = tk.StringVar()
    action_names = {ACTION_LABELS[key]: key for key in ACTION_CODES}
    ttk.Combobox(assign_row, state='readonly', textvariable=action_var,
                 values=tuple(action_names), width=20).pack(side='left')
    button_message = tk.StringVar(value='Not read. No button settings are shown or changed at startup.')
    ttk.Label(buttons_tab, textvariable=button_message, wraplength=800, justify='left').pack(anchor='w', pady=(8, 0))
    button_controls = ttk.Frame(buttons_tab)
    button_controls.pack(anchor='w', pady=8)
    last_button_read_node = None

    def perform_button(action):
        nonlocal last_button_read_node
        node = selected_node.get()
        if not node:
            messagebox.showerror('Select an interface', 'Refresh devices and select a candidate feature interface.', parent=root)
            return
        backup = None
        slot = None
        new_action = None
        if action == 'button-assign':
            selection = button_table.selection()
            if last_button_read_node != node or len(selection) != 1:
                messagebox.showerror('Read and select a slot', 'Read this interface first, then select one supported native slot.', parent=root)
                return
            slot = int(button_table.item(selection[0], 'values')[0])
            if slot not in BLOCK_SLOTS or action_var.get() not in action_names:
                messagebox.showerror('Unsupported assignment', 'Select a supported slot and an action.', parent=root)
                return
            new_action = action_names[action_var.get()]
        elif action == 'button-restore':
            path = filedialog.askopenfilename(parent=root, title='Select button-backup.json',
                                              filetypes=[('JSON backup', '*.json'), ('All files', '*')])
            if not path:
                return
            backup = Path(path)
        warnings = {
            'button-read': 'This staged read sends SET_FEATURE and GET_FEATURE requests. Effects are experimental.',
            'button-assign': f'This commits native slot {slot} to {action_var.get()}. Physical button mapping is not verified. An eight-byte partial backup and readback will be made; recovery is not guaranteed.',
            'button-restore': 'This restores a partial button-block backup and refuses intervening edits. Recovery is not guaranteed.'
        }
        if not messagebox.askyesno('Experimental button operation',
                f"{warnings[action]}\n\nConfirm {node} is your EvoFox Blaze GM862. Close other mouse tools and do not unplug during the operation. Continue?", parent=root):
            return
        button_message.set(f'Working on {node}. Keep the mouse connected…')
        def completed(result, error):
            nonlocal last_button_read_node
            last_button_read_node = None
            if error:
                button_message.set('Operation failed. State may be uncertain. Do not retry blindly; inspect the evidence.')
                messagebox.showerror('Button operation failed', error, parent=root)
                return
            payload, capture = result
            if action == 'button-read':
                button_table.delete(*button_table.get_children())
                for row in payload.get('button_slots', []):
                    candidate = row.get('action_candidate')
                    button_table.insert('', 'end', values=(row['slot'], row.get('vendor_ui_button') or '—',
                        row.get('raw_hex', ''), ACTION_LABELS.get(candidate, 'Unknown / extension')))
                last_button_read_node = node
                button_message.set(f"Read block: {payload.get('collected_hex', 'unknown')}. Candidate labels are not verified.\nEvidence: {capture}")
            else:
                text = f"Outcome: {payload.get('outcome', 'unknown')}. Readback does not establish physical behavior; reconnecting may be required."
                if payload.get('backup_file'):
                    text += f"\nPartial button backup: {capture / payload['backup_file']}"
                button_message.set(text + f'\nEvidence: {capture}\nRead again before another change.')
        start_task(lambda: run_operation(action, node, backup=backup, slot=slot, button_action=new_action), completed)

    for label, action in [('Read buttons…', 'button-read'), ('Apply selected…', 'button-assign'), ('Restore button backup…', 'button-restore')]:
        button = ttk.Button(button_controls, text=label, command=lambda a=action: perform_button(a))
        button.pack(side='left', padx=(0, 8))
        operation_buttons.append(button)
    ttk.Label(buttons_tab, text='All operations require confirmation. Reads send SET_FEATURE staging. Backups cover one 8-byte block only. '
              'No automatic retry, rollback or activation.', wraplength=800, style='Notice.TLabel').pack(anchor='w', pady=4)

    ttk.Label(lighting_tab, text='Live lighting preview · experimental', font=('TkDefaultFont', 11, 'bold')).pack(anchor='w')
    ttk.Label(lighting_tab, text='Only two fixed live-effect requests are available. Color, brightness, saved lighting settings and macros cannot be configured here.',
              wraplength=800).pack(anchor='w', pady=(5, 12))
    light_device_row = ttk.Frame(lighting_tab)
    light_device_row.pack(fill='x')
    ttk.Label(light_device_row, text='Feature interface:').pack(side='left', padx=(0, 8))
    lighting_device_box = ttk.Combobox(light_device_row, state='readonly', textvariable=selected_node, width=22)
    lighting_device_box.pack(side='left')
    ttk.Label(light_device_row, text='Shared with Performance and Buttons.').pack(side='left', padx=10)
    light_row = ttk.Frame(lighting_tab)
    light_row.pack(fill='x', pady=12)
    ttk.Label(light_row, text='Request:').pack(side='left', padx=(0, 8))
    light_var = tk.StringVar()
    light_options = {'Light-on effect': 'light-on', 'Light-off effect': 'light-off'}
    ttk.Combobox(light_row, state='readonly', textvariable=light_var, values=tuple(light_options), width=20).pack(side='left')
    light_message = tk.StringVar(value='No request sent. The original lighting state is not read or backed up.')
    ttk.Label(lighting_tab, textvariable=light_message, wraplength=800, justify='left').pack(anchor='w', pady=(8, 0))

    def preview_lighting():
        nonlocal last_button_read_node
        node = selected_node.get()
        mode = light_options.get(light_var.get())
        if not node or not mode:
            messagebox.showerror('Choose device and effect', 'Select a candidate interface and one of the two live effects.', parent=root)
            return
        if not messagebox.askyesno('Experimental live-lighting request',
                f"Send a single {light_var.get()} SET_FEATURE request to {node}?\n\n"
                'Light-on was reported working on one GM862; light-off and behavior on other devices remain unverified. No original lighting backup, readback, or automatic restore is available. '
                'It may change lighting unexpectedly or persist. A power cycle restored lighting on another device, but that is not guaranteed here.\n\n'
                'Confirm this is your EvoFox Blaze GM862, close other mouse tools and keep the mouse connected. Continue?', parent=root):
            return
        invalidate_stages()
        last_button_read_node = None
        light_message.set(f'Sending one request to {node}. Keep the mouse connected…')
        def completed(result, error):
            if error:
                light_message.set('Request failed. Lighting state may be uncertain; do not retry blindly. Inspect the evidence.')
                messagebox.showerror('Lighting request failed', error, parent=root)
                return
            payload, capture = result
            light_message.set(f"Request sent: {payload.get('mode', 'unknown')}. Physical behavior and persistence are not verified.\n"
                              f"No backup or restore is available. Evidence: {capture}")
        start_task(lambda: run_operation('lighting', node, light_mode=mode), completed)

    light_button = ttk.Button(lighting_tab, text='Send live effect…', command=preview_lighting)
    light_button.pack(anchor='w', pady=(12, 8))
    operation_buttons.append(light_button)
    ttk.Label(lighting_tab, text='No lighting request is sent at startup. The request requires confirmation and has no automatic retry, reset or rollback.',
              wraplength=800, style='Notice.TLabel').pack(anchor='w')

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
