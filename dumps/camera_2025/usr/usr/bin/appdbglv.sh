#!/bin/sh

CMDNAME=${0#/usr/bin/}

if [ -e /usr/bin/ulogio.elf ] ; then
	ULOGIOCMD=ulogio.elf
else
	ULOGIOCMD=ulogio
fi

APPSYSTEM_NO=131
MODELSUBSYS_NO=135
VIEWSUBSYS_NO=136
WGTSUBSYS_NO=137

SUBSYSTEM_NO=$APPSYSTEM_NO
SUBSYS_SELECT=legacy

#------------------------------------------------------
#  USAGE
#------------------------------------------------------
Usage()
{
	echo "Usage: $CMDNAME [option] [category|modelID|viewID|wgtDlogID] [level]"
	echo "  options  -d   set to default"
	echo "           -i   infomation(show setting)"
	echo "           -o   other subsystem"
	echo "           -s   silent"
	if [ "$ULOGIOCMD" = "ulogio.elf" ] ; then
		echo "           -r   rewind"
	fi
	echo "           -m   each model"
	echo "           -v   each view"
	echo "           -q   inquire model/view id number"
	echo "                    ex. $CMDNAME -q view/TOOL_MENU"
	echo "           -w   widget"
	echo ""
	echo "           $CMDNAME cannot accept multiple options at same time."
	echo "  category  all | view | model | vmng | mmng | mbase | cbase  | vbase | fmwk | wgt | wrapper"
	echo "  level     clr | err | war | dbg | info | off"
	exit 0
}

SubsysModel_set()
{
	SUBSYSTEM_NO=$MODELSUBSYS_NO		# 0x87
	SUBSYS_SELECT="model"
}

SubsysView_set()
{
	SUBSYSTEM_NO=$VIEWSUBSYS_NO		# 0x88
	SUBSYS_SELECT="view"
}

SubsysWgt_set()
{
	SUBSYSTEM_NO=$WGTSUBSYS_NO		# 0x89
	SUBSYS_SELECT="wgt"
}

#------------------------------------------------------
#  OPTIONS
#------------------------------------------------------
Options()
{
	case $1 in
		-*) HIFEN="TRUE";;
	esac

	if [ "$HIFEN" = "TRUE" ]; then
		HIFEN_EXIT="yes"

		# debug
		if [ "$1" = "-b" -o  "$1" = "-B" ]; then
			APPDBGLVSH_DEBUG=yes
			shift
			echo "debug on, $1"
		fi

		# clear filter setting(rollback to default)
		if [ "$1" = "-d" -o "$1" = "-D" ]; then
			$ULOGIOCMD filter clear
			$ULOGIOCMD filter on 0 error
		fi

		# information(show setting)
		if [ "$1" = "-i" -o "$1" = "-I" ]; then
			echo "app category ids(hex):"
			echo "    1 - view    2 - model   3 - vmng   4 - mmng   5 - cbase"
			echo "    6 - mbase   7 - vbase   8 - fmwk   9 - wgt    a - wrapper"
			$ULOGIOCMD filter info
		fi

		# other subsystem
		if [ "$1" = "-o" -o "$1" = "-O" ]; then
			shift
			if [ "$1" = "clear" -o "$2" = "clear" -o "$3" = "clear" ]; then
				echo $CMDNAME': cannot apply "clear" to each component. try only "clear" for all clear'
			else
				if [ $# -eq 2 ] ; then
					if [ "$2" = "off" ]; then
						$ULOGIOCMD filter off $1
					else
						if [ "$2" = "on" ]; then
							$ULOGIOCMD filter on $1 info
						else
							$ULOGIOCMD filter on $1 $2
						fi
					fi
				else
					if [ $# -eq 3 ] ; then
						if [ "$3" = "off" ]; then
							echo $CMDNAME': cannot apply "off" to each component. typing "'$1' err" might reduce messages.'
						else
							$ULOGIOCMD filter on $1 $2 $3
						fi
					else
						echo $CMDNAME': illeagal parameter(s)'
					fi
				fi
			fi
		fi

		# rewind
		if [ "$1" = "-r" -o "$1" = "-R" ]; then
			if [ "$ULOGIOCMD" = "ulogio.elf" ] ; then
				$ULOGIOCMD rewind
			fi
		fi

		# silent
		if [ "$1" = "-s" -o "$1" = "-S" ]; then
			$ULOGIOCMD filter off 0
		fi

		# each model
		if [ "$1" = "-m" -o "$1" = "-M" ]; then
			SubsysModel_set
			HIFEN_EXIT="no"
		fi
		# each view
		if [ "$1" = "-v" -o "$1" = "-V" ]; then
			SubsysView_set
			HIFEN_EXIT="no"
		fi
		# widget
		if [ "$1" = "-w" -o "$1" = "-W" ]; then
			SubsysWgt_set
			HIFEN_EXIT="no"
		fi

		# model/view id number inquiry
		if [ "$1" = "-q" -o "$1" = "-Q" ]; then
			echo "*** check debug level if nothing is shown. ***"
			echo "***   \"$CMDNAME cbase error\" required.   ***"
			echo ""
			testcmd.elf --sync 0x83014b other 0x1700200C str 0x17002009 $2
		fi

		# exit if not -v or -m
		if [ "$HIFEN_EXIT" = "yes" ]; then
			exit 0;
		fi
	fi
}

do_ulogio_filter_clear() {
	if [ "$SUBSYS_SELECT" = "legacy" ]; then
		$ULOGIOCMD filter clear
	else
		echo $CMDNAME': cannot clear by each subsystem or component. use "all clr".'
	fi
}

do_ulogio_filter() {
#echo "do_ulogio_filter "$1
	case $1 in
		"all" )   $ULOGIOCMD filter on $SUBSYSTEM_NO $LEVEL
		          eval CATEGORY=\$CAT_$SUBSYS_SELECT
		          if [ "$SUBSYS_SELECT" = "view" ]; then
		               $ULOGIOCMD filter on $APPSYSTEM_NO 0xffffffff $LEVEL
		               $ULOGIOCMD filter on $APPSYSTEM_NO $CATEGORY $LEVEL
		          else
			          if [ "$SUBSYS_SELECT" = "model" ]; then
			              $ULOGIOCMD filter on $APPSYSTEM_NO 0xfffffffe $LEVEL
		                  $ULOGIOCMD filter on $APPSYSTEM_NO $CATEGORY $LEVEL
		              else
		                  if [ "$SUBSYS_SELECT" = "wgt" ]; then
		                      $ULOGIOCMD filter on $APPSYSTEM_NO 0xfffffffd $LEVEL
		                      $ULOGIOCMD filter on $APPSYSTEM_NO $CATEGORY $LEVEL
		                  fi
			          fi
		          fi
		          if [ "yes" = "$APPDBGLVSH_DEBUG" ]; then
		              echo "    subsystem filter $SUBSYSTEM_NO $LEVEL"
		          fi ;;
		"clr" )   do_ulogio_filter_clear;;
		"clear" ) do_ulogio_filter_clear;;
		"off" )   $ULOGIOCMD filter off $SUBSYSTEM_NO
		          eval CATEGORY=\$CAT_$SUBSYS_SELECT
		          if [ "$SUBSYS_SELECT" = "view" ]; then
		              $ULOGIOCMD filter on $APPSYSTEM_NO 0xffffffff error
		              $ULOGIOCMD filter on $APPSYSTEM_NO $CATEGORY error
		          fi
		          if [ "$SUBSYS_SELECT" = "model" ]; then
		              $ULOGIOCMD filter on $APPSYSTEM_NO 0xfffffffe error
		              $ULOGIOCMD filter on $APPSYSTEM_NO $CATEGORY error
		          fi
		          if [ "$SUBSYS_SELECT" = "wgt" ]; then
		              $ULOGIOCMD filter on $APPSYSTEM_NO 0xfffffffd error
		              $ULOGIOCMD filter on $APPSYSTEM_NO $CATEGORY error
		          fi
		          if [ "yes" = "$APPDBGLVSH_DEBUG" ]; then
		              echo "    subsystem filter $SUBSYSTEM_NO off"
		          fi ;;
		* )       if [ "$CATEGORY" = "-1" -o "$CATEGORY" = "0xffffffff" ]; then
		              SUBSYSTEM_NO=$APPSYSTEM_NO
		              CATEGORY=0xffffffff
		          fi
		          if [ "$CATEGORY" = "-2" -o "$CATEGORY" = "0xfffffffe" ]; then
		              SUBSYSTEM_NO=$APPSYSTEM_NO
		              CATEGORY=0xfffffffe
		          fi
		          if [ "$CATEGORY" = "-3" -o "$CATEGORY" = "0xfffffffd" ]; then
		              SUBSYSTEM_NO=$APPSYSTEM_NO
		              CATEGORY=0xfffffffd
		          fi
		          $ULOGIOCMD filter on $SUBSYSTEM_NO $CATEGORY $LEVEL
		          if [ "yes" = "$APPDBGLVSH_DEBUG" ]; then
		              echo "    component filter $SUBSYSTEM_NO $CATEGORY $LEVEL"
		          fi ;;
	esac
}

redo_ulogio_filter_if_legacy_vmw()
{
	case $1 in
		"view" )
			SubsysView_set
			do_ulogio_filter all;;
		"model" )
			SubsysModel_set
			do_ulogio_filter all;;
		"wgt" )
			SubsysWgt_set
			do_ulogio_filter all;;
	esac
}

#------------------------------------------------------
#  MAIN Procedure
#------------------------------------------------------
if [ $# -eq 0 -o $# -gt 4 ] ; then
	Usage
fi

Options $@

if [ "$HIFEN_EXIT" = "no" ]; then
	shift
fi
if [ "yes" = "$APPDBGLVSH_DEBUG" ]; then
	shift
fi

if [ $# -gt 3 ] ; then
	Usage
fi

# build LUT,   donot assign 0, since it is used for error check
CAT_view=1
CAT_model=2
CAT_vmng=3
CAT_mmng=4
CAT_cbase=5
CAT_mbase=6
CAT_vbase=7
CAT_fmwk=8
CAT_wgt=9
CAT_wrapper=10
CAT_all="all"
LEV_clr="clear"
LEV_clear="clear"
LEV_err="error"
LEV_error="error"
LEV_war="warning"
LEV_warning="warning"
LEV_dbg="debug"
LEV_debug="debug"
LEV_info="info"
LEV_off="off"

if [ $# -eq 1 ]; then
	if [ "$SUBSYS_SELECT" = "legacy" ]; then
		eval CATEGORY=\$CAT_$1
	else
		if [ "$SUBSYS_SELECT" = "view" -o "$SUBSYS_SELECT" = "model" -o "$SUBSYS_SELECT" = "wgt" ]; then
			CATEGORY=$1
		else
			CATEGORY=$SUBSYS_SELECT
		fi
	fi
	eval LEVEL=\$LEV_$1
	if [ "$CATEGORY" = "" -a "$LEVEL" = "" ] ; then
		echo $CMDNAME': illeagal name - '$1
		exit 1
	fi
	if [ "$LEVEL" = "$CATEGORY" ]; then
		LEVEL=
	else
		if [ "$LEVEL" = "" ]; then
			LEVEL="info"
		fi
	fi

	do_ulogio_filter $1
	redo_ulogio_filter_if_legacy_vmw $1

#	if [ "$1" = "all" ] ; then
#		$ULOGIOCMD filter on $SUBSYSTEM_NO info
#		echo "    subsystem filter $SUBSYSTEM_NO info"
#	else
#		if [ "$1" = "clr" -o "$1" = "clear" ] ; then
#			$ULOGIOCMD filter clear
#		else
#			if [ "$1" = "off" ] ; then
#				$ULOGIOCMD filter off $SUBSYSTEM_NO
#				echo "    subsystem filter $SUBSYSTEM_NO off"
#			else
#				$ULOGIOCMD filter on $SUBSYSTEM_NO $CATEGORY info
#				echo "    component filter $SUBSYSTEM_NO $CATEGORY info"
#			fi
#		fi
#	fi
else
	if [ "$SUBSYS_SELECT" = "legacy" ]; then
		eval CATEGORY=\$CAT_$1
	else
		if [ "$SUBSYS_SELECT" = "view" -o "$SUBSYS_SELECT" = "model" -o "$SUBSYS_SELECT" = "wgt" ]; then
			CATEGORY=$1
		else
			CATEGORY=$SUBSYS_SELECT
		fi
	fi
	eval LEVEL=\$LEV_$2

	if [ "$CATEGORY" = "" ] ; then
		echo $CMDNAME': illeagal category name - '$1
		exit 1
	fi
	if [ "$LEVEL" = "" ] ; then
		echo $CMDNAME': illeagal level name - '$2
		exit 1
	fi

	if [ "$1" = "all" ] ; then
		if [ "$2" = "clr" -o "$2" = "clear" ] ; then
			 do_ulogio_filter_clear
		else
			if [ "$2" = "off" ]; then
				$ULOGIOCMD filter off $SUBSYSTEM_NO
				if [ "$SUBSYS_SELECT" = "view" ]; then
					$ULOGIOCMD filter $SUBSYSTEM_NO 0xffffffff error
					$ULOGIOCMD filter $SUBSYSTEM_NO $CATEGORY error
				fi
				if [ "$SUBSYS_SELECT" = "model" ]; then
					$ULOGIOCMD filter $SUBSYSTEM_NO 0xfffffffe error
					$ULOGIOCMD filter $SUBSYSTEM_NO $CATEGORY error
				fi
				if [ "$SUBSYS_SELECT" = "wgt" ]; then
					$ULOGIOCMD filter $SUBSYSTEM_NO 0xfffffffd error
					$ULOGIOCMD filter $SUBSYSTEM_NO $CATEGORY error
				fi
				if [ "yes" = "$APPDBGLVSH_DEBUG" ]; then
					echo "    subsystem filter $SUBSYSTEM_NO off"
				fi
			else
				do_ulogio_filter all
			fi
		fi
	else
		if [ "$2" = "clr" -o "$2" = "clear" ] ; then
			 do_ulogio_filter_clear
		else
			if [ "$2" = "off" ]; then
				echo $CMDNAME': cannot apply "off" to each component. typing "'$1' err" might reduce messages.'
			else
				do_ulogio_filter individually
				redo_ulogio_filter_if_legacy_vmw $1
			fi
		fi
	fi
fi
