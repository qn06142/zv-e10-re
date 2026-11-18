# ZV-E10 access and diagnostics

Reviewed 18 November 2026 from saved runtime evidence and tool sources. [Current status](CURRENT_STATUS.md) records the last camera checkpoint.

## Access paths

| Route | Use | Dependency and evidence |
| --- | --- | --- |
| Wi-Fi SSH | Inspect normal shooting, live view and recording from Linux. | Installed Dropbear, working wlan0/hotspot lease, client key and pinned host key. Verified authenticated sessions on 17 November. |
| USB MSC to Senser | Existing filesystem and shell workflow through pmca. | Stock mode handoff and service environment. Entering service mode changes the application state being investigated. [USB interface guide](reference/08-camera-interfaces.md). |
| Linux filesystem update | Deploy checked files to mounted partitions through an available shell. | Read current mounts and baseline hashes first. /usr is ext2 and normally mounted read-only. [Persistence and partitions](reference/07-modification.md). |
| BootROM/toolkit recovery | Restore selected user partitions when normal Linux access fails. | Working hardware injection, stage1 USB communication, eMMC access and matching backups. The toolkit guide covers user partitions and excludes boot0/boot1, partition tables and physical faults. |

The local toolkit checkout is C:/Users/qn061/Documents/Codex/2026-11-05/d-02-development-and-projects-pmca/outputs/usb-library-recovery/zv-e10-toolkit-main. Its fastboot/docs/recovery.md contains the checked procedure and scope. The available records do not demonstrate a same-body restore/readback for the proposed RTOS replacement trial. [Upstream recovery guide](https://github.com/dino2048/zv-e10-toolkit/blob/main/fastboot/docs/recovery.md).

## SSH connection

The last authenticated lease was 192.168.137.152, port 22, user root. Camera Wi-Fi MAC is D8-10-68-34-B6-45. Match that MAC if DHCP changes the lease. Root login uses the supplied Ed25519 key. Keep the private key outside this repository.

```powershell
$recovery = 'C:\Users\qn061\Documents\Codex\2026-11-05\d-02-development-and-projects-pmca\work\network-recovery-build'
$cameraHost = '192.168.137.152'
$sshArgs = @(
    '-T', '-p', '22', '-i', (Join-Path $recovery 'zve10-recovery-client'),
    '-o', 'HostKeyAlias=zve10-recovery',
    '-o', "UserKnownHostsFile=$(Join-Path $recovery 'known_hosts')",
    '-o', 'StrictHostKeyChecking=yes', '-o', 'BatchMode=yes',
    '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=5'
)
ssh @sshArgs "root@$cameraHost" '/tmp/busybox cat /proc/uptime /proc/sys/kernel/random/boot_id'
```

Pinned host-key fingerprint is SHA256:6+ZO+gUb+AenngIvPWyeVzhSVNoFH7oWH1M54V7TzvA. The launcher under /usr/share/pmca-ssh binds Dropbear to wlan0 and tracks hotspot address changes. The earlier Wi-Fi installation report ended before an authenticated retest. The November runtime SSH sessions supply that later evidence. [Captured session evidence](../research/firmware/evidence/zve10-20261117/README.md).

For PowerShell here-strings sent to sh -s, strip CR characters before the SSH pipe. An unstripped carriage return caused a remote exit-status parsing error in the initial probe. Stream large traces directly to a unique host file and check the SSH exit status.

## On-camera tools

| Tool | Verified behavior | Limit |
| --- | --- | --- |
| /bin/busybox | Stock small utility set. | Missing several processing applets used by ordinary shell scripts. |
| /tmp/busybox | Existing BusyBox 1.35.0, 269 applets, including awk, diff, head, od, sha256sum, stat, timeout and xz. | Invoke this symlink name. Executing its bbhf target by that name produced an applet lookup error. |
| /tmp/zve10-tools/zve10-trace liro | Reads /proc/tmonitor to stdout. | Reading alone cannot guarantee a fresh window. Repeated and empty windows were observed. |
| /tmp/zve10-tools/zve10-regs TID | Brief PTRACE_ATTACH, ARM register dump, PTRACE_DETACH. A disposable sleep process resumed with TracerPid 0. | Stops the selected thread briefly. No attach to im.elf was tested. It is a small register snapshot tool. Stack unwinding and breakpoint debugging are not implemented. |

The diagnostics [source and build notes](../research/device/zve10_diagnostics/README.md) are in the repo. The original Zig 0.15.2 build used arm-linux-musleabi, cortex_a9, static and Oz. The hardware inventory identifies Cortex-A5, so retain that mismatch in build provenance and check generated instructions before extending the program. The tested register dumper ran successfully on the camera.

/tmp and /etc share nflasha10, a flash-backed VFAT partition. In the observed session it had about 1 MiB free. Large trace files should stream to the host. Reboot persistence of the new diagnostics remains unverified.

## Fresh LiRo trace capture

The tested kernel interface takes a decimal CPU mask with no newline. Mask 15 selects all four CPUs and mask 4 selects CPU 2. The observed ring capacity was 1,024 records at 32 KiB. Restricting capture to CPU 2 extended the sampled interval from about 43 ms to about 140 ms.

Use this procedure when the tracer is known stopped. It starts a bounded capture and leaves tracing stopped. It discards the old window. Preserve any existing capture before rearming.

```sh
(
    set -eu
    trap 'printf 0 > /proc/tmonitor' EXIT
    printf '%s' 4 > /proc/tmonitor
    /tmp/busybox sleep 0.20
    printf 0 > /proc/tmonitor
    /tmp/zve10-tools/zve10-trace liro
)
```

The original trace reader returned the same 46.847 ms window six times, followed by empty reads. Explicit rearming produced four distinct windows. The old tmonitor.py comment claiming every read is fresh should be interpreted using these hardware observations. [Raw captures and provenance](../research/firmware/evidence/zve10-20261117/README.md).

## Host analysis and file identity

The existing project uses Python, pyelftools, Capstone/Unicorn and GNU Arm Embedded tools. Captured Sony av-cam.bin analysis used load base 0x635c6000 and MD5 cdcae9d4fdbf66a33704a4c7564e346d. Addresses apply to that input until a current readback proves a match.

Use repository-relative evidence paths in durable docs. Store source location, SHA-256, byte count, capture context and any mode uncertainty alongside imported evidence. Private keys, host private keys, firmware images and patched Sony objects belong in local build/backup storage under the existing provenance rules. [Provenance policy](reference/09-provenance.md).
