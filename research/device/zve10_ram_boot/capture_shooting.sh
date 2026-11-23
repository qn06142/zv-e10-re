#!/bin/sh
# Bounded normal-shooting capture. Reads RAM/MMIO and writes only its new log dir.
set -eu
B=/tmp/busybox
D=${1:-/log/zvlv21}
case "$D" in
    /log/zvlv21|/log/zvlv22) ;;
    *) exit 2 ;;
esac
[ ! -e "$D" ] || exit 2
mkdir "$D"
trap 'echo FAILED > "$D/status"' EXIT
echo WAITING_FOR_SHOOTING > "$D/status"
n=0
while [ "$n" -lt 180 ]; do
    mode=$($B devmem 0x0426b4a0 32)
    value=$((mode))
    if [ "$value" -gt 0 ] && [ "$value" -lt 219 ] && [ "$value" -ne 17 ]; then
        break
    fi
    n=$((n + 1))
    $B sleep 1
done
[ "$n" -lt 180 ] || { trap - EXIT; echo NO_SHOOTING_MODE > "$D/status"; exit 3; }
echo CAPTURING > "$D/status"
$B sleep 2
for i in 0 1 2; do
    $B hexdump -v -n 1088 -s 69645188 /dev/mem > "$D/imager-$i.txt"
    if [ "$D" = /log/zvlv22 ]; then
        # IRQ 84 subscriber records at firmware VA 0x64263d24. Read the RAM
        # table without reading the interrupt controller's event/ack ports.
        $B hexdump -v -n 256 -s 69614884 /dev/mem > "$D/irq84-slots-$i.txt"
    fi
    $B cat /proc/uptime > "$D/uptime-$i.txt"
    $B cat /proc/interrupts > "$D/irq-$i.txt"
    for base in 0xf3002380 0xf3102380 0xf3020200 0xf3020280 0xf3020300 0xf3020380 0xf3020400 0xf3020480 0xfc0a9200 0xf3441280 0xf3441580 0xf3441200 0xf3441500; do
        for offset in 0 4 16 32 36 40 44; do
            address=$((base + offset))
            printf '%08x ' "$address"
            $B devmem "$address" 32
        done
    done > "$D/registers-$i.txt"
    $B sleep 1
done
$B cat /proc/sys/kernel/random/boot_id > "$D/boot-id.txt"
echo DONE > "$D/status"
trap - EXIT
