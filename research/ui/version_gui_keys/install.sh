#!/bin/sh
# Display-only Version-screen input probe. No sequence or OS handoff.
set -eu
BB=/bin/busybox
TARGET=/usr/lib/viewUnified6.so
STAGE=/usr/lib/viewUnified6.gui-keys.new
BACKUP_DIR=/usr/share/version-gui-keys-v01
BACKUP=$BACKUP_DIR/viewUnified6.previous-marker.so
CANDIDATE=/log/version-gui-keys-v01/viewUnified6.gui-keys.so
STOCK_MD5=e0291b75251f665c23ace529bb04e01f
PROBE_MD5=0aa2e7c2928c261b3f63197a89f38bb3
sum() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
fail() { echo "$*" >&2; exit 1; }
[ "$(sum "$TARGET")" = "$STOCK_MD5" ] || fail 'Stock library identity mismatch'
[ "$(sum "$CANDIDATE")" = "$PROBE_MD5" ] || fail 'Candidate identity mismatch'
$BB grep -q ' /usr ext2 ro[, ]' /proc/mounts || fail 'Expected read-only ext2 /usr'
[ ! -e "$STAGE" ] || fail 'Preserving existing staging file; inspect it first'
if [ -e "$BACKUP" ]; then
    [ "$(sum "$BACKUP")" = "$STOCK_MD5" ] || fail 'Preserving conflicting backup'
fi
activated=no
success=no
finish() {
    result=$?
    trap - EXIT
    if [ "$activated" = yes ] && [ "$success" != yes ]; then
        echo 'Restoring original library pathname after installation failure' >&2
        if $BB cp "$BACKUP" "$STAGE" &&
           [ "$(sum "$STAGE")" = "$STOCK_MD5" ] &&
           $BB mv "$STAGE" "$TARGET" &&
           [ "$(sum "$TARGET")" = "$STOCK_MD5" ]; then
            echo ORIGINAL_PATH_RESTORED >&2
        else
            echo ROLLBACK_FAILED_USE_VERIFIED_HOST_BACKUP >&2
            result=1
        fi
    fi
    $BB sync || result=1
    mount -o remount,ro /usr || result=1
    exit "$result"
}
mount -o remount,rw /usr
trap finish EXIT
$BB mkdir -p "$BACKUP_DIR"
[ ! -e "$BACKUP" ] || fail 'Preserving existing input-probe backup; inspect before reinstall'
# A hard link retains the inode currently mapped by im.elf.
$BB ln "$TARGET" "$BACKUP"
[ "$(sum "$BACKUP")" = "$STOCK_MD5" ] || fail 'Backup verification failed'
$BB cp "$CANDIDATE" "$STAGE"
$BB chmod 755 "$STAGE"
[ "$(sum "$STAGE")" = "$PROBE_MD5" ] || fail 'Staged verification failed'
[ "$(sum "$TARGET")" = "$STOCK_MD5" ] || fail 'Target changed while staging'
# Replace the directory entry, preserving the inode used by existing mappings.
$BB mv "$STAGE" "$TARGET"
activated=yes
[ "$(sum "$TARGET")" = "$PROBE_MD5" ] || fail 'Installed verification failed'
$BB sync
success=yes
echo GUI_KEYS_INSTALLED_RESTART_REQUIRED
