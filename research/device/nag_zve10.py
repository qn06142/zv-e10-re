import pathlib
import sys
# nag_reboot lives beside this script.  The old sys.path pointed into a
# per-user skills directory that only existed on the original machine, and the
# repository root does not help either -- the module is not a package member.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nag_reboot
nag_reboot.nag_reboot(
    title="Replug the ZV-E10",
    msg="The camera is stuck in service mode (unclean exit).\n"
        "Unplug it, plug it back in, then click OK.\n"
        "(It will reboot into normal MSC; the script will then re-enter service mode.)",
)
print("NAG_OK")
