#!/bin/sh

UPMNT=/setting
UPDIR=$UPMNT/updater
UPMODE=$UPDIR/mode
UPMODE1=$UPDIR/mode1

LSI_MAIN=1
LSI_SUB=2

#######################################
### Function declaration

### change to usermode
func_usermode()
{
	#delete other mode flags
	rm -f $UPDIR/mode*

	#create mode flag
	touch $UPDIR/mode

	#sync
	sync

	# file check and message
	if [ -f "$UPMODE" ] ; then
		echo "next boot...   UFP mode"
	else
		echo "next boot...   Normal mode"
	fi
}

### change to version skip mode
func_verskip()
{
	#delete other mode flags
	rm -f $UPDIR/mode*

	#create mode flag
	touch $UPDIR/mode $UPDIR/mode6

	#sync
	sync

	# file check and message
	if [ -f "$UPDIR/mode6" ] ; then
		echo "next boot...   Version Skip mode"
	else
		echo "next boot...   Normal mode"
	fi
}

### change to version skip mode
func_mscrypt()
{
	#delete other mode flags
	rm -f $UPDIR/mode*

	#create mode flag
	touch $UPDIR/mode $UPDIR/mode5

	#sync
	sync

	# file check and message
	if [ -f "$UPDIR/mode5" ] ; then
		echo "next boot...   MS Crypt mode"
	else
		echo "next boot...   Normal mode"
	fi
}

### change to servicemode
func_servicemode()
{
	#delete other mode flags
	rm -f $UPDIR/mode*

	#create mode flag
	touch $UPDIR/mode $UPDIR/mode3

	#sync
	sync

	# file check and message
	if [ -f "$UPDIR/mode3" ] ; then
		echo "next boot...   Service mode"
	else
		echo "next boot...   Normal mode"
	fi

}

### change to keepbackup mode
func_keepbackup()
{
	#delete other mode flags
	rm -f $UPDIR/mode*

	#create mode flag
	touch $UPDIR/mode $UPDIR/mode1 $UPDIR/mode4

	#sync
	sync

	# file check and message
	if [ -f "$UPDIR/mode4" ] ; then
		echo "next boot...   Keepbackup mode"
	else
		echo "next boot...   Normal mode"
	fi
}


### modify version
## $1 : target version
func_modver()
{
	local _newver=$1
	test ${#_newver} -eq 4 || { echo "Invalid Parameter" ; return 1 ; } 

	if [ ! -e /root/IAMUPDATER ] ; then
		mount -t tmpfs -o size=1024 tmpfs /tmp_updater
	fi

	#get current version
	ud_datcnv.elf -d -i /setting/updater/dat4 -o /tmp_updater/upcurver -a
	if [ $? -ne 0 ] ; then
		echo "Could not get current version" ; return 1 ;
	fi
	local _current
	_current=`cat /tmp_updater/upcurver`

	rm -f /tmp_updater/upcurver

	#write new version into tempfile
	echo "$_newver" > /tmp_updater/upnewver
	ud_datcnv.elf -e -i /tmp_updater/upnewver -o /setting/updater/dat4 -a
	if [ $? -ne 0 ] ; then
		echo "Could not write new version" ; return 1 ;
	fi

	#sync
	sync
	sync

	rm -f /tmp_updater/upnewver

	if [ ! -e /root/IAMUPDATER ] ; then
		umount /tmp_updater
	fi

	#message
	echo "Modify verion $_current -> $_newver"
}

### modify model
## $1 : target model
func_modmod()
{
	func_com_mod_modreg "model" "dat2" $1
}

### modify region
## $1 : target region
func_modreg()
{
	func_com_mod_modreg "region" "dat3" $1

}

### common func modmod, modreg
# $1 : Prompt String
# $2 : filename ( dat2 or dat3 )
# $3 : new value
func_com_mod_modreg()
{
	local _file=$2
	local _newval=$3
	test ${#_newval} -eq 8 || { echo "Invalid Parameter" ; return 1 ; }

	if [ ! -e /root/IAMUPDATER ] ; then
		mount -t tmpfs -o size=1024 tmpfs /tmp_updater
	fi

	mkdir -p /tmp_updater/upmnt
	mount -t vfat /dev/nflasha1 -o posix_attr,noatime,nodiratime,shortname=mixed /tmp_updater/upmnt
	if [ $? -ne 0 ] ; then
		echo "Error Failed to mount p1" ; exit 1
	fi

	#get current value
	ud_datcnv.elf -d -i /tmp_updater/upmnt/$_file -o /tmp_updater/upcurval -a
	if [ $? -ne 0 ] ; then
		echo "Could not get current value"
		umount /tmp_updater/upmnt
		exit 1
	fi

	local _current
	_current=`cat /tmp_updater/upcurval`
	rm -f /tmp_updater/upcurval

	#write new value into tempfile
	echo "$_newval" > /tmp_updater/upnewval
	ud_datcnv.elf -e -i /tmp_updater/upnewval -o /tmp_updater/upmnt/$_file -a
	if [ $? -ne 0 ] ; then
		echo "Could not write new value" ; unmount /tmp_updater/upmnt ; exit 1 ;
	fi

	umount /tmp_updater/upmnt

	rm -rf /tmp_updater/upnewval /tmp_updater/upmnt

	if [ ! -e /root/IAMUPDATER ] ; then
		umount /tmp_updater
	fi

	#message
	echo "Modify $1 $_current -> $_newval"

}


##########################################
## main 
##########################################


if [ $# -eq 0 ] ; then

# if not exist ,  create directory
if [ ! -d "$UPDIR" ];then
	mkdir $UPDIR
fi

# create file
if [ -f "$UPMODE" ];then
	rm -f $UPDIR/mode*
else
	touch $UPMODE $UPMODE1
fi
# write nand 
sync

# file check and message
if [ -f "$UPMODE" ];then
	echo "next boot...   Updater mode"
	mode_num=4
else
	echo "next boot...   Normal mode"
	mode_num=0
fi

else
#########################################
## user, service, modmod, modver, modreg

case $1 in
#	"keep" )
#		func_keepbackup
#		;;
	"user" )
		func_usermode
		mode_num=2
		;;
	"serv" )
		func_servicemode
		mode_num=3
		;;
	"modmod" )
		func_modmod $2
		;;
	"modver" )
		func_modver $2
		;;
	"modreg" )
		func_modreg $2
		;;
	"ms" )
		func_mscrypt
		;;
	"ver" )
		func_verskip
		mode_num=6
		;;
	*)
		;;
esac

fi

test -e /root/IAMUPDATER
if [ $? = 0 ]; then
	exit 0
fi

ud_send_lsi.elf $mode_num
