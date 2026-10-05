#!/bin/sh
# uninstall_opengate.sh -- Safely removes Open Gate hook and restores stock boot mode
#
# Completely reverts the camera to stock Sony factory behavior.

say() { echo "== $*"; }

say "Reverting ZV-E10 to Stock Sony Video Configuration..."

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
say "Removing /setting/opengate.so and /setting/opengate.conf..."
rm -f /setting/opengate.so /setting/opengate.conf /setting/opengate.log

# 4. Flush changes
say "Syncing storage..."
sync

say "=========================================================="
say "UNINSTALLATION COMPLETE!"
say "Camera will boot into standard factory 16:9 mode on reboot."
say "=========================================================="
