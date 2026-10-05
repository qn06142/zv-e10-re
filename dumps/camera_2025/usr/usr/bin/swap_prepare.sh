#!/bin/sh

PROC_SWAP=/proc/ssboot/swapfile
SWAP_FILE=/dev/nflasha8
PART_DIR=/sys/block/nflasha0/nflasha0p8

MAX_KB=60000


if [ -d "$PART_DIR" ]; then
    echo "SwapPartition Found !"

    echo /dev/compswap > $PROC_SWAP
    echo $SWAP_FILE > /sys/block/compswap0/backing_file
    echo $MAX_KB > /sys/block/compswap0/disksize_kb
    echo > /sys/block/compswap0/init

    echo "SwapPartition Prepare Done (compswap) !"
    exit 0
else
    echo "SwapPartition($SWAP_FILE) Not Found."
    exit 1
fi
