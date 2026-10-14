#!/bin/sh
# install_uvc.sh -- Installs High-Speed UVC Webcam Unlock onto Sony ZV-E10
#
# Safe, non-destructive deployment via persistent /setting partition.
# No firmware flashing. Completely reversible.

say() { echo "== $*"; }
die() { echo "!! $*"; exit 1; }

say "Starting ZV-E10 High-Speed UVC Webcam Installation..."

# 1. Check persistent partition
if ! mount | grep -q '/setting'; then
    die "/setting is not mounted! Cannot proceed."
fi

# 2. Source files location
SRC_DIR=$(dirname "$0")
if [ ! -f "$SRC_DIR/uvc_hook.so" ]; then
    die "uvc_hook.so not found in $SRC_DIR"
fi

# 3. Copy binary and configuration to /setting
say "Installing uvc_hook.so to /setting/uvc_hook.so..."
cp "$SRC_DIR/uvc_hook.so" /setting/uvc_hook.so || die "Failed to copy uvc_hook.so"
chmod 755 /setting/uvc_hook.so

if [ -f "$SRC_DIR/uvc.conf" ]; then
    say "Installing config to /setting/uvc.conf..."
    cp "$SRC_DIR/uvc.conf" /setting/uvc.conf
fi

# 4. Configure Sony developer boot mode (dmode 3p + preload hook)
mkdir -p /setting/mode
say "Configuring /setting/mode/preload..."
echo "/setting/uvc_hook.so" > /setting/mode/preload

say "Configuring /setting/mode/dmode..."
echo "3p" > /setting/mode/dmode

# 5. Flush writes to flash
say "Flushing buffers to eMMC..."
sync

# 6. Verification
say "Verification:"
ls -l /setting/uvc_hook.so /setting/mode/preload /setting/mode/dmode
echo "dmode content:   $(cat /setting/mode/dmode)"
echo "preload content: $(cat /setting/mode/preload)"
md5sum /setting/uvc_hook.so

say "=========================================================="
say "UVC WEBCAM INSTALLATION COMPLETE!"
say "Reboot the camera to engage High-Speed UVC streaming."
say "Check /setting/uvc.log after boot to verify status."
say "=========================================================="
