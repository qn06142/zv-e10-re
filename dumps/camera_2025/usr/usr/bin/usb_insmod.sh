#!/bin/sh

insmod /kmod/usb_event.ko
insmod /kmod/usb_scd.ko
insmod /kmod/ups.ko
insmod /kmod/usb_otgcore.ko
insmod /kmod/usb_gadgetcore.ko
insmod /kmod/usb_portMonitor.ko
insmod /kmod/usbg_sen.ko
insmod /kmod/usb_extcmd.ko

