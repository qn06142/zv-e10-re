#!/bin/sh
# install_opengate.sh -- Installs 3:2 Open Gate unlock onto Sony ZV-E10
#
# Safe, non-destructive deployment via persistent /setting partition.
# No firmware flashing. Completely reversible.

say() { echo "== $*"; }
die() { echo "!! $*"; exit 1; }

say "Starting ZV-E10 3:2 Open Gate Installation..."

# 1. Check persistent partition
if ! mount | grep -q '/setting'; then
    die "/setting is not mounted! Cannot proceed."
fi

# 2. Source files location (e.g. from SD card or staged directory)
SRC_DIR=$(dirname "$0")
if [ ! -f "$SRC_DIR/opengate.so" ]; then
    die "opengate.so not found in $SRC_DIR"
fi

# 3. Copy binary and configuration to /setting
say "Installing opengate.so to /setting/opengate.so..."
cp "$SRC_DIR/opengate.so" /setting/opengate.so || die "Failed to copy opengate.so"
chmod 755 /setting/opengate.so

if [ -f "$SRC_DIR/opengate.conf" ]; then
    say "Installing config to /setting/opengate.conf..."
    cp "$SRC_DIR/opengate.conf" /setting/opengate.conf
fi

# 4. Configure Sony developer boot mode (dmode 3p + preload hook)
mkdir -p /setting/mode
say "Configuring /setting/mode/preload..."
echo "/setting/opengate.so" > /setting/mode/preload

say "Configuring /setting/mode/dmode..."
echo "3p" > /setting/mode/dmode

# 5. Flush writes to flash
say "Flushing buffers to eMMC..."
sync

# 6. Verification
say "Verification:"
ls -l /setting/opengate.so /setting/mode/preload /setting/mode/dmode
echo "dmode content:   $(cat /setting/mode/dmode)"
echo "preload content: $(cat /setting/mode/preload)"
md5sum /setting/opengate.so

say "=========================================================="
say "INSTALLATION COMPLETE!"
say "Reboot the camera to engage 3:2 Open Gate video recording."
say "Check /setting/opengate.log after boot to verify status."
say "=========================================================="
