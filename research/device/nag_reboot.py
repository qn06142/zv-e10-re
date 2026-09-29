#!/usr/bin/env python3
"""nag_reboot.py - shared helper: block until the user confirms a device reboot.

Used by the RE probe scripts as a workflow gate: when a probe needs a fresh
MTP session (the W830 wedges after one), it calls nag_reboot() which shows an
always-on-top window and does NOT return until the user clicks OK. The caller
can then safely assume the camera was physically replugged/rebooted.

No pip deps: uses tkinter (ships with CPython).
"""
import sys

def show_nag(title="REBOOT CAMERA",
             msg="Reboot the Sony DSC W830.\nUnplug + replug (or power-cycle) the camera,\nthen click OK to confirm it's back."):
    import tkinter as tk
    root = tk.Tk()
    root.title(title)
    root.attributes('-topmost', True)
    root.resizable(False, False)
    frame = tk.Frame(root, padx=24, pady=18)
    frame.pack()
    tk.Label(frame, text=msg, justify='left', font=("Segoe UI", 10)).pack(pady=(0, 14))
    tk.Button(frame, text="OK, I rebooted it", font=("Segoe UI", 10),
              width=22, command=lambda: root.quit()).pack()
    root.update_idletasks()
    root.lift()
    root.focus_force()
    root.mainloop()
    root.destroy()

def nag_reboot():
    """Block until the user confirms a reboot via the nag window."""
    show_nag()

def main():
    # standalone: just show the nag and exit (used as a blocking tool)
    if '--check' in sys.argv:
        print("OK"); return
    nag_reboot()

if __name__ == '__main__':
    main()
