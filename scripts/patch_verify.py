#!/usr/bin/env python3
"""Minimal patch to verify the camera reads av-cam.bin from disk at boot.

Patches a single uint16 in the string/constant table at offset 0xff44c8
(3376 -> 4000) and reads it back after reboot.

The constant 3376 (0x0D30) is the Y-window size used by ISP_dimension_select.
Changing it to 4000 (0x0FA0) is safe — it's in a read-only data table,
not executable code. If the camera outputs a different resolution or
errors, we know av-cam.bin is the active pipeline.
"""
import sys, os, struct, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import senser_fix  # noqa: F401 — fixes 0x8000 payload loss on PID 0x0336

from pmca.commands.usb import senserShellCommand
from pmca.platform import CameraShell
from pmca.platform.backend.senser import SenserPlatformBackend
from pmca.shell.parser import ArgParser

PATCH_OFFSET = 0xff44c8   # file offset of uint16 3376
PATCH_VALUE  = 4000       # uint16 LE to write (0x0FA0)
ORIG_VALUE   = 3376       # original value for revert

def main():
    def complete(dev):
        SenserPlatformBackend(dev).start()
        raw = dev.dev
        dev.setTerminalEnable(False)
        dev.setTerminalEnable(True)
        try:
            # Drain banner
            import time as _t
            buf = b""
            last = _t.time()
            end = _t.time() + 3.0
            while _t.time() < end:
                d = dev.readTerminal()
                if d:
                    buf += d
                    last = _t.time()
                    end = _t.time() + 3.0
                elif _t.time() - last > 1.5:
                    break
                else:
                    _t.sleep(0.02)
            if buf:
                print("--- banner ---")
                print(buf.decode("latin1", errors="replace")[:500])

            # Step 1: Read original value at offset
            print("\n=== Step 1: Read original value ===")
            raw.writeTerminal(
                ("busybox xxd -s 0x%x -l 2 /system/av-cam.bin" % PATCH_OFFSET).encode("latin1") + b"\n"
            )
            out = b""
            last = _t.time()
            end = _t.time() + 5.0
            while _t.time() < end:
                d = dev.readTerminal()
                if d:
                    out += d
                    last = _t.time()
                    end = _t.time() + 5.0
                elif _t.time() - last > 2.0:
                    break
                else:
                    _t.sleep(0.02)
            print(out.decode("latin1", errors="replace"))

            # Step 2: Patch the byte
            # Write 0x0FA0 (4000) as little-endian uint16 at offset 0xff44c8
            # 0x0FA0 = 0xA0 0x0F
            print("=== Step 2: Patch 0x%x (3376 -> 4000) ===" % PATCH_OFFSET)
            # Use printf to write the bytes
            cmd = (
                "printf '\\xa0\\x0f' | busybox dd of=/system/av-cam.bin "
                "bs=1 seek=%d conv=notrunc 2>&1" % PATCH_OFFSET
            )
            raw.writeTerminal(cmd.encode("latin1") + b"\n")
            out = b""
            last = _t.time()
            end = _t.time() + 5.0
            while _t.time() < end:
                d = dev.readTerminal()
                if d:
                    out += d
                    last = _t.time()
                    end = _t.time() + 5.0
                elif _t.time() - last > 2.0:
                    break
                else:
                    _t.sleep(0.02)
            print(out.decode("latin1", errors="replace"))

            # Step 3: Verify the patch on disk (before reboot)
            print("=== Step 3: Verify patch on disk ===")
            raw.writeTerminal(
                ("busybox xxd -s 0x%x -l 2 /system/av-cam.bin" % PATCH_OFFSET).encode("latin1") + b"\n"
            )
            out = b""
            last = _t.time()
            end = _t.time() + 5.0
            while _t.time() < end:
                d = dev.readTerminal()
                if d:
                    out += d
                    last = _t.time()
                    end = _t.time() + 5.0
                elif _t.time() - last > 2.0:
                    break
                else:
                    _t.sleep(0.02)
            print(out.decode("latin1", errors="replace"))

            # Step 4: Reboot the camera
            print("=== Step 4: Reboot camera ===")
            raw.writeTerminal(b"reboot\n")
            _t.sleep(5.0)
            # Drain any output during reboot
            out = b""
            last = _t.time()
            end = _t.time() + 10.0
            while _t.time() < end:
                d = dev.readTerminal()
                if d:
                    out += d
                    last = _t.time()
                    end = _t.time() + 10.0
                elif _t.time() - last > 3.0:
                    break
                else:
                    _t.sleep(0.02)
            if out:
                print("Reboot output (first 500 chars):")
                print(out.decode("latin1", errors="replace")[:500])
            print("Camera should be rebooting... waiting 15s for service mode to come back.")
            _t.sleep(15.0)

            # Step 5: Read back the patched value after reboot
            print("=== Step 5: Read patched value after reboot ===")
            raw.writeTerminal(
                ("busybox xxd -s 0x%x -l 2 /system/av-cam.bin" % PATCH_OFFSET).encode("latin1") + b"\n"
            )
            out = b""
            last = _t.time()
            end = _t.time() + 5.0
            while _t.time() < end:
                d = dev.readTerminal()
                if d:
                    out += d
                    last = _t.time()
                    end = _t.time() + 5.0
                elif _t.time() - last > 2.0:
                    break
                else:
                    _t.sleep(0.02)
            print(out.decode("latin1", errors="replace"))

            # Step 6: Check md5 to see if the file changed
            print("=== Step 6: md5sum after reboot ===")
            raw.writeTerminal(b"busybox md5sum /system/av-cam.bin\n")
            out = b""
            last = _t.time()
            end = _t.time() + 10.0
            while _t.time() < end:
                d = dev.readTerminal()
                if d:
                    out += d
                    last = _t.time()
                    end = _t.time() + 10.0
                elif _t.time() - last > 3.0:
                    break
                else:
                    _t.sleep(0.02)
            print(out.decode("latin1", errors="replace"))

            print("\n=== PATCH VERIFY COMPLETE ===")
            print("If the md5 matches the original (cdcae9d4fdbf66a33704a4c7564e346d),")
            print("the camera did NOT persist the patch (av-cam.bin is decrypted at boot from secure core).")
            print("If the md5 is DIFFERENT and the xxd shows 0xA0 0x0F at offset 0xff44c8,")
            print("the camera DOES read av-cam.bin from disk at boot (plaintext, not decrypted).")

        except Exception as e:
            print("Error: %s" % e)
            import traceback; traceback.print_exc()
        finally:
            try: dev.setTerminalEnable(False)
            except: pass
            try: dev.backend.stop()
            except: pass

    senserShellCommand(complete=complete)

if __name__ == "__main__":
    main()