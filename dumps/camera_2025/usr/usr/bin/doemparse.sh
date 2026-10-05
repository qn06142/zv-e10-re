#! /bin/sh

# doemparse.sh

export PATH=/bin:/usr/bin:/devel/usr/bin

if [ 0 -eq $# ] ; then
	emparse.pl -f /proc/klog -s /System.map -t "/usr/lib /lib" | c++filt
else
	if [ $1 = '/' ] ; then
		emparse.pl -f /proc/klog -s /System.map -t / | c++filt
	else
		echo 'Usage : doemparse.sh </>'
		echo '    wraps emparse.pl.'
		echo '    The option "/" is to set library path to root.'
	fi
fi
