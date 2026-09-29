# Runs ON the camera. Locates the live picture buffer by diffing /dev/mem
# across two reads taken ~1s apart while a video is playing.  Whatever changes
# is the picture (plus the log); a region that changes *coherently* and is
# large is the frame buffer, and its row pitch gives us the real resolution.
#
# Needs: /dev/mem readable (confirmed), the SD card mounted, ~57 GB free.
# Cost: ~2 dumps of the scanned range.  At the ~3 MB/s the shell sustains for
# /dev/mem that is minutes per dump, so the range is deliberately a knob.

echo "=== preflight ==="
busybox mkdir -p /tmp/sd
busybox mount -t vfat /dev/mmca1 /tmp/sd
echo "MOUNT_RC=$?"
busybox mount | busybox grep sd
busybox ls /tmp/sd

# ---- knobs ---------------------------------------------------------------
# CHUNK = 1 MiB.  RANGE_MB = how many MiB to scan from PHYS_BASE.
PHYS_BASE=0
CHUNK_MB=1
COUNT_MB=512

CHUNK=$((CHUNK_MB*1024*1024))
echo ""
echo "=== scanning $COUNT_MB MiB from $PHYS_BASE in $CHUNK_MB MiB chunks ==="

dump_list() {
    OUT=$1
    busybox rm -f "$OUT"
    i=0
    while [ $i -lt $COUNT_MB ]; do
        OFF=$((PHYS_BASE + i*CHUNK))
        H=$(busybox dd if=/dev/mem bs=$CHUNK skip=$i count=1 2>/dev/null | busybox md5sum | busybox cut -c1-12)
        busybox echo "$i $H" >> "$OUT"
        i=$((i+1))
    done
    busybox echo "  wrote $OUT"
}

echo "--- pass 1 (play the video NOW) ---"
dump_list /tmp/sd/md5_a.txt
echo "--- pass 2 (keep playing, ~1s later) ---"
dump_list /tmp/sd/md5_b.txt

echo ""
echo "=== chunks that differ between the two passes ==="
busybox diff /tmp/sd/md5_a.txt /tmp/sd/md5_b.txt | busybox grep '^>' | busybox cut -c1-8
echo ""
echo "=== for each differing chunk, the address range and a hex preview ==="
busybox diff /tmp/sd/md5_a.txt /tmp/sd/md5_b.txt | busybox grep '^>' | busybox sed 's/^> //' | busybox cut -d' ' -f1 | while read IDX; do
    OFF=$((PHYS_BASE + IDX*CHUNK))
    busybox echo "---- chunk $IDX  phys 0x$(busybox echo $OFF | busybox sed 's/^0*//') ----"
    busybox dd if=/dev/mem bs=16 skip=$((OFF/16)) count=24 2>/dev/null | busybox xxd
done
echo ""
echo "done. md5 lists kept on the card at /tmp/sd/md5_a.txt and md5_b.txt"
