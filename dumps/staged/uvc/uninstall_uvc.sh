#!/bin/sh
# uninstall_uvc.sh -- Safely removes UVC webcam hook and restores stock boot mode
#
# Completely reverts the camera to stock Sony factory behavior.

say() { echo "== $*"; }

say "Reverting ZV-E10 to Stock Sony UVC Webcam Configuration..."

# 1. Revert boot mode to stock (dmode 3 = normal boot without preload)
if [ -f /setting/mode/dmode ]; then
    say "Restoring /setting/mode/dmode to 3 (stock)..."
    echo "3" > /setting/mode/dmode
fi

# 2. Remove preload hook pointer
if [ -f /setting/mode/preload ]; then
    say "Removing /setting/mode/preload..."
    rm -f /setting/mode/preload
fi

# 3. Remove binary and logs
say "Removing /setting/uvc_hook.so and /setting/uvc.conf..."
rm -f /setting/uvc_hook.so /setting/uvc.conf /setting/uvc.log

# 4. Flush changes
say "Syncing storage..."
sync

say "=========================================================="
say "UVC WEBCAM UNINSTALLATION COMPLETE!"
say "Camera will boot into standard factory 720p UVC mode on reboot."
say "=========================================================="
