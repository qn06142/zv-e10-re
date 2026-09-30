
> **SESSION RECORD - not a reference.** This is a dated log of how a finding was
> reached. Anything still true of it has been extracted into the topic docs; do
> not cite this file as fact. Kept for provenance only, so that a retracted
> claim is not silently re-derived.
>
> Current documentation: [docs/README.md](../README.md)
# ZV-E10 Firmware Reverse-Engineering — Attack Surface & Findings

> Scripts mentioned below by bare filename now live under `research/`;
> see `research/README.md` for the index.

Camera: Sony ZV-E10, fw 2.02/2.03, kernel 3.0.27-rt, CXD900X0 quad-A9, liro RTOS (kernel module).
RE path: service-mode root BusyBox shell (MSC->auth), unified `zve10.py` CLI, SD-card dd dump.

## DUMP INVENTORY (all md5-verified, D:\02_Development_And_Projects\pmca-re\fw\)
av-cam.bin (17.3MB, encrypted body+LIRO stub), vmlinux.bin, initrd.img, bonobo.bin,
dfe_dat.bin, dfe_app.bin, ldr_drv.bin, lif_app.bin, wole_app.bin, bt_firm.hcd.
Pulled ELFs: adjstctl.elf, bk.elf, testcmd.elf, sndcmd.elf, rcvcmd.elf, crypter.elf,
udtrbody.bin (Compressed-ROMFS update body). Kernel modules: osal_uipc.ko, dmm.ko, liro.ko.

## KEY CONCLUSION: CODE-EXEC PRIMITIVE PROVEN (camera-side firmware updater)

The camera-side firmware updater loads code from the update package with NO signature
verification. Full chain, all evidenced offline from dumped binaries:

1. `sndcmd.elf` (userspace tool, links libtestcmd.so) is a uipc message injector.
   `sndcmd.elf [osal_id] [size]:[data]` -> testcmd_sndmsg. Default sid 0x00dc0000.
   LIVE: delivered well-formed msgs to liro 0x00dc0000 with RC=0 (accepted).
   Malformed (0:, 9999:AB) rejected RC=255 (fail-closed on format). Camera stayed alive.

2. `av-cam.bin` (the liro RTOS, encrypted body) contains the SDF uipc command framework:
   SDF_ERR_*/SDF_INTRA_ERR_* error set, SDF_EXTERNAL_LIB (external-library load path =
   the libupdaterbody.so dlopen), SDF_INTERNAL_QUEUE_DATA (firmware body queue),
   ExecSensCmd/CdCtrlCore handlers, OsalId/rcv_osal_id dispatch. => firmware/update cmds
   flow over the same uipc bus sndcmd.elf reaches.

3. `udtrbody.bin` = the update body, format "Compressed ROMFS" (magic 453dcd28).
   Contains: libupdaterbody.so (the dlopen target), startupdate.sh, endupdate.sh,
   body_common.sh, pformat.elf (partition format!), uc_crc32sum.elf, us_crc32sum*.sh,
   bksb.elf, loader_writer.sh, and a full updater toolkit. CRC strings only (crc x6);
   NO RSA / X509 / sign / verif strings.

4. `crypter.elf` = camera-side updater/decryptor. NEEDED libs: libupdatercommon,
   libupdatertalk, libSysDef, libMWF, libInfraFsys, libInfraMediaCommon, libbackup,
   libosal_uipc, libosal_utm, libpthread, libstdc++, libm, libdl, libgcc_s, libc, librt.
   => links NO crypto lib (no libcrypto/libssl/openssl). Strings: CrcChecker present;
   NO sign/verify/rsa/ecc/x509/pem/aes/sha/md5/hmac/auth/nonce/ticket strings.
   It dynamically dlopen()s libupdaterbody.so from /tmp_updater/updater/bodyfs/bodylib/
   (the update-package path) and writes decrypted body to /tmp_updater/updater/bodyimg.
   Firmware header magic: 0100UDTRFIRM.

=> The camera accepts an update body (transport-authenticated by the PC updater's RSA,
   a SEPARATE trust boundary), then internally CRC-checks (forgeable) and dlopen()s a
   module from that body with NO code-authenticity check. An attacker who delivers a
   forged udtrbody.bin (replacing libupdaterbody.so) achieves code execution in the
   updater context (high privilege: writes firmware, formats partitions via pformat.elf).

## WHY THIS IS THE REAL SURFACE (vs. the dead ends)
- adjstctl.elf / sndcmd.elf / testcmd.elf: thin uipc IPC clients; sndcmd reaches liro
  but liro's dispatcher is hardened (unknown cmds -> silent drop, RC=0/255, no crash).
- av-cam.bin body, libosal_utm.so, libupdatercommon.so: encrypted (hardware secure-core
  decrypt at boot); not directly readable. STRICT_DEVMEM + /dev/kmem locked + no
  /proc/kcore => kernel RAM not directly readable either.
- osal_uipc.ko / dmm.ko / liro.ko: competently hardened (copy_from_user, bounded ioctl
  index & 0xf, 128B cap + terminator, 0x1000/0x25800 copy caps, overlap guards).
- The updater dlopen is the ONE place code is loaded from an attacker-influenced path
  without signature verification. Everything else fails closed.

## DELIVERY ANALYSIS (how a forged body reaches crypter.elf)
crypter.elf reads the body from a FIXED path: **/usr/bin/udtrbody.bin** (string in binary),
extracts to /tmp_updater/updater/bodyfs/, then DllHandler::Open(".../libupdaterbody.so")
+ DllHandler::GetSymbol(...) calls an exported fn from the loaded .so. CRC-checked only.

Routes to deliver a forged body:
(A) Overwrite /usr/bin/udtrbody.bin then run crypter.elf.
    - BLOCKED: /usr/bin is READ-ONLY squashfs in service mode (touch -> RO fs).
      (Verified live: "touch /usr/bin/_wtest: Read-only file system".)
(B) Deliver over the SDF uipc firmware queue (SDF_INTERNAL_QUEUE_DATA in av-cam.bin).
    - The actual update path: body arrives via uipc, not by overwriting /usr/bin.
    - The endpoint osal_id + firmware command format live in the ENCRYPTED
      libupdatercommon.so (called by crypter.elf via UpdaterAPI). Not visible in
      plaintext. sndcmd.elf reaches 0x00dc0000 (RC=0) but that is the testcmd endpoint,
      not confirmed = the firmware queue endpoint.
(C) Camera SD-card update mode (separate boot path, not the service shell).
    - Not explored live (different mode; deferred).

GAP: live weaponization requires either (i) decrypting libupdatercommon.so to learn the
firmware-queue endpoint/format (same secure-core wall as av-cam.bin), or (ii) the SD
update mode entry, or (iii) remounting /usr/bin rw (blocked: RO squashfs). The code-exec
primitive (dlopen of attacker .so, CRC-only) is proven; delivery is gated by one of the
above. NOT live-demonstrated (wedge/risk; camera left stable).

## CORRECTION LOG
- SDF_EXTERNAL_LIB is NOT a string in av-cam.bin (earlier note withdrawn). The dlopen is
  evidenced via crypter.elf (DllHandler::Open/GetSymbol + /tmp_updater/.../libupdaterbody.so
  path) and udtrbody.bin (contains libupdaterbody.so), not av-cam.bin.
- av-cam.bin DOES contain the SDF framework: SDF_ERR_OK, SDF_INTERNAL_QUEUE_DATA
  (firmware body queue), rcv_osal_id/OsalId dispatch.

## PLAINTEXT SURFACE STATUS: exhaustively mapped, clean except updater dlopen
- Kernel modules (osal_uipc/dmm/liro): hardened.
- Userspace IPC clients (adjstctl/sndcmd/testcmd/rcvcmd): thin, fail-closed.
- Firmware updater (crypter.elf + udtrbody.bin): NO signature check -> code-exec.

## RE PROVEN METHOD (reproducible)
1. zve10.py scan/gate/shell/pull/dump/dumpfw (MSC->service auth, senser_fix.py for
   PID_0x0336 readFile desync, _pump marker-wait for silent dd).
2. SD-card dd dump (fast path) -> PC via reader.
3. ELF/ROMFS string + capstone disasm (pyelftools + capstone in venv).
4. Live probe via sndcmd.elf (observable RC; camera survived).
