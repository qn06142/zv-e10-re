#!/bin/sh

MODE_FILE=/setting/mode/dmode
PRELOAD_FILE=/setting/mode/preload

LIB_LT=/usr/tool/LeakTracer.so
LIB_EFENCE=/usr/tool/libefence.so
LIB_JEMALLOC=/usr/tool/libjemalloc_tsh.so
LIB_MCHECKB=/usr/tool/libmcheckb.so

usage()
{
	echo "Usage   : change_mode.sh <param>"
	echo "param   : "
	echo "    0   : kernel boot"
	echo "    1   : kernel boot -> created global infra"
	echo "    2   : kernel boot -> created global infra -> LIRO boot"
	echo "    3   : kernel boot -> created global infra -> LIRO boot -> appFw boot (**default**)"
	echo "    4   : kernel boot -> created global infra(nounified driver)"
	echo "    5   : kernel boot -> created global infra(nounified driver) -> LIRO boot"
	echo "    6   : kernel boot -> created global infra(nounified driver) -> LIRO boot -> appFw boot"
	echo "  ----  : "
	echo "    7   : kernel boot -> created global infra -> LIRO boot -> appFw boot (w/ LeakTracer)"
	echo "    8   : kernel boot -> created global infra -> LIRO boot -> appFw boot (sslibc Wfree Check Mode)"
	echo "    9   : kernel boot -> created global infra -> LIRO boot -> appFw boot (KMC ICE)"
	echo "    a   : kernel boot -> created global infra -> LIRO boot -> appFw boot (target gdb)"
	echo "    b   : kernel boot -> created global infra -> LIRO boot -> appFw boot (gdbserver)"
	echo "    d   : kernel boot -> created global infra -> LIRO boot -> appFw boot (DUMA)"
	echo "    e   : kernel boot -> created global infra -> LIRO boot -> appFw boot (Electric Fence)"
	echo "    f   : kernel boot -> created global infra -> LIRO boot -> appFw boot (jemalloc)"
	echo "   10   : kernel boot -> created global infra -> LIRO boot -> appFw boot (mcheckb)"
	echo " --help : display Usage"
}

if [ ! -d /setting/mode ] ; then 
	mkdir -p /setting/mode
fi

if [ ! -f $MODE_FILE ] ; then 
	echo > $MODE_FILE
fi

chmod 777 $MODE_FILE

if [ $# = 0 ]; then
	echo "Invalid parameter."
	usage
	exit 1
elif [ $1 = 0 ]; then
	echo 0 > $MODE_FILE
	echo  > $PRELOAD_FILE
	echo "Changed your mode to mode0."
elif [ $1 = 1 ]; then
	echo 1 > $MODE_FILE
	echo  > $PRELOAD_FILE
	echo "Changed your mode to mode1."
elif [ $1 = 2 ]; then
	echo 2 > $MODE_FILE
	echo  > $PRELOAD_FILE
	echo "Changed your mode to mode2."
elif [ $1 = 3 ]; then
	echo 3 > $MODE_FILE
	echo  > $PRELOAD_FILE
	echo "Changed your mode to mode3(default)."
elif [ $1 = 4 ]; then
	echo 1n > $MODE_FILE
	echo  > $PRELOAD_FILE
	echo "Changed your mode to mode1(nounified driver)."
elif [ $1 = 5 ]; then
	echo 2n > $MODE_FILE
	echo  > $PRELOAD_FILE
	echo "Changed your mode to mode2(nounified driver)."
elif [ $1 = 6 ]; then
	echo 3n > $MODE_FILE
	echo  > $PRELOAD_FILE
	echo "Changed your mode to mode3(nounified driver)."
elif [ $1 = 7 ]; then
	echo 3L > $MODE_FILE
	echo -n $LIB_LT > $PRELOAD_FILE
	echo "Changed your mode to mode3(LeakTracer)."
elif [ $1 = 8 ]; then
	echo 3w > $MODE_FILE
	echo  > $PRELOAD_FILE
	echo "Changed your mode to mode3(sslibc WCheck)."
elif [ $1 = 9 ]; then
	echo 3k > $MODE_FILE
	echo  > $PRELOAD_FILE
	echo "Changed your mode to mode3(KMC ICE)."
elif [ $1 = a ]; then
	echo 3g > $MODE_FILE
	echo  > $PRELOAD_FILE
	echo "Changed your mode to mode3(target gdb)."
elif [ $1 = b ]; then
	echo 3s > $MODE_FILE
	echo  > $PRELOAD_FILE
	echo "Changed your mode to mode3(gdbserver)."
elif [ $1 = d ]; then
	echo 3d > $MODE_FILE
	echo  > $PRELOAD_FILE
	echo "Changed your mode to mode3(DUMA)."
elif [ $1 = e ]; then
	echo 3e > $MODE_FILE
	echo  > $PRELOAD_FILE
	echo "Changed your mode to mode3(eFence)."
elif [ $1 = f ]; then
	echo 3p > $MODE_FILE
	echo -n $LIB_JEMALLOC > $PRELOAD_FILE
	echo "Changed your mode to mode3(jemalloc)."
elif [ $1 = 10 ]; then
	echo 3p > $MODE_FILE
	echo -n $LIB_MCHECKB > $PRELOAD_FILE
	echo "Changed your mode to mode3(mcheckb)."
elif [ $1 = p ]; then
	echo 3p > $MODE_FILE
	echo -n $2 > $PRELOAD_FILE
	echo "Changed your mode to mode3(preload)."
elif [ $1 = "--help" ]; then
	usage
	exit 1
else
	echo "Invalid parameter."
	usage
	exit 1
fi


echo "============================"
echo "Please reboot your system."
