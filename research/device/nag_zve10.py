import sys
sys.path.insert(0, r"C:\Users\Minhsnguhoa\AppData\Local\hermes\skills\reverse-engineering\camera-usb-re\scripts")
import nag_reboot
nag_reboot.nag_reboot(
    title="Replug the ZV-E10",
    msg="The camera is stuck in service mode (unclean exit).\n"
        "Unplug it, plug it back in, then click OK.\n"
        "(It will reboot into normal MSC; the script will then re-enter service mode.)",
)
print("NAG_OK")
