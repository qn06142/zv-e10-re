#!/bin/sh

if [ ! -e /tmp_bt/DEBUG ]; 
then
    # echo "normal"
    if [ ! -e /tmp_bt/NOTLOAD ]; 
    then
        # echo "normal"
        /usr/bin/bsa_server -k /tmp_bt/ble_local_keys -u /tmp_bt/ -d /dev/ttyBT -p /usr/bin/bt_firm.hcd -all=0 &
    else
        # echo "not load firm"
        /usr/bin/bsa_server -r 14 -k /tmp_bt/ble_local_keys -u /tmp_bt/ -d /dev/ttyBT -all=0 &
    fi
else
    # echo "debug"
    if [ ! -e /tmp_bt/NOTLOAD ]; 
    then
        # echo "normal"
        /usr/bin/bsa_server -k /tmp_bt/ble_local_keys -u /tmp_bt/ -d /dev/ttyBT -b /tmp_bt/snoop.cfa -p /usr/bin/bt_firm.hcd -all=5 > /tmp_bt/bsa_log.txt &
    else
        # echo "not load firm"
        /usr/bin/bsa_server -r 14 -k /tmp_bt/ble_local_keys -u /tmp_bt/ -d /dev/ttyBT -b /tmp_bt/snoop.cfa -all=5 > /tmp_bt/bsa_log.txt &
    fi
fi

while :
do
    pidof bsa_server > /tmp_bt/bsa_s_pid
    
    invalid=`cat /tmp_bt/bsa_s_pid | grep -c "\s"`
    if [ "$invalid" = "0" ];
    then
        if [ -s /tmp_bt/bsa_s_pid ];
        then
            # echo "valid pid"
            break
        else
            # echo "pid file empty"
            # echo "pid file empty" > /log/TEST
	    :
        fi
    else
        # echo "invalid pid"
        # echo "invalid pid" > /log/TEST
        :
    fi
done
