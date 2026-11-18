from pathlib import Path
import json,hashlib,shutil,zipfile
O=Path('outputs/hd-v41');m=json.loads((O/'build/manifest.json').read_text());plan=json.loads((O/'memory-plan.json').read_text())
r='''# Revision 4.1: 1080p uncompressed resizer / USB candidate

30 October 2026. Built and tested offline; NOT installed and NOT hardware verified. This implements the user's pivot to the existing 8-bit YUY2 route at 1920x1080, including direct USB output. The separate native 10/12-bit producer investigation is deferred for this experiment.

## What changes

Native full-resolution VDF input -> owned source metadata copy -> Sony SDF resizeRotate -> owned 1920x1080 uncompressed image -> existing UYVY-to-YUY2 byte permutation -> owned USB source -> existing fenced gadget driver.

The source contract now requires a native 1920x1080 canvas and full-size valid area, with no offset. A VGA input is rejected instead of upscaled. The incoming native YC may still be compressed: SDF is requested to deliver an uncompressed destination. This does not claim to bypass upstream ISP compression or provide native high-depth samples. Output is 8-bit YUY2, 4,147,200 bytes/frame, 3840 bytes/row as the candidate's intended packed layout. Returned metadata must be 1920x1080, compression zero and depth marker zero before the complete output is copied; actual HD hardware packing must be checked from captured bytes.

USB descriptors/probe/commit now specify 1920x1080, 16 bits/pixel, 4,147,200 maximum frame bytes and a single 2,000,000 x100ns interval (5fps). Bitrate fields are 165,888,000 bits/s. Five fps is the initial advertised test rate, not a measured result; no timed sleeps were added. Source/host backpressure and ACK/CMP/DMA fences remain.

## Allocation plan and its limits

The old type0x220 destination resolves to an 819,200-byte pool, old USB source type0x276 to 3,276,800 bytes and USB staging type0x50e to 1,843,200 bytes. They cannot carry full-HD YUY2.

This module directly requests existing native image unit0x127, mapped to existing extent0x165 with 4,147,200-byte definitions, separately for the SDF output and USB source. Actual DMM grants, bounds and non-overlap must pass. The unit must be available twice concurrently; a static config entry does not prove this. No busy peer or live allocation is borrowed or disconnected. Insufficient allocations refuse the stream.

DmmConfig.bin changes only one alias word at file offset0x1309c: USB staging unit0x50e moves from extent0x589 to existing8MiB extent0x1ba. Every physical extent definition/size remains byte-identical. Existing0x220 and0x276 aliases remain unchanged. This avoids increasing configured physical pool sizes, but can create resource contention with other clients of extent0x1ba; live availability is unverified. Configuration loading/caching and cold-boot behavior require device validation. This is a candidate configuration, not a certified deployment.

Original installed yc37_fence driver code at .text+0x1b44..0x1b6c was executed offline. It uses returned allocation size/2 for the slot split. With8MiB it gives two4MiB slots; each fits4,147,200+12 bytes. Three size fixtures pass. The frontend separately rejects total staging smaller than8,294,424 bytes. No kernel modification is needed; exact required kernel MD5 remains388799d95bbb524ca581c66b077b6dc2. Existing DMA error fences and ownership protections are retained.

## Verification

- 39 real worker C cases pass with mocked native services, including100-frame HD publication/reference-ledger cases, no-image handling, failures and cleanup.
- Destination/source contract checks pass, including rejecting VGA input, compressed destination, nonzero destination depth marker and short spans.
- Actual compiled ARM code passes activation, host-busy, no-sleep, 1080p descriptor and full-frame submission checks. An undersized double-staging case refuses submission.
- Four actual compiled ARM source-allocation cases request unit0x127, refuse3.2MB / one-byte-short results, free owned short grants and map valid HD allocations.
- Persistent wrapper checks pass at three load addresses; ARM ISA inspection finds no NEON instructions.
- Three original kernel size-split cases pass; this does not emulate real DMA or USB bandwidth.

All hardware/native IPC services in the worker/frontend tests are simulated. No real1080p image, throughput, stability or resizer acceptance result exists yet. The previous stream-end crash is not fixed by this geometry change. Existing one-session-per-boot restrictions remain. No camera was contacted this pass.

## Candidate files and next live boundary

The candidate bundle contains matched producer library, persistent streaming wrapper, candidate DMM configuration and unchanged required kernel, plus exact baseline files for reference/rollback. These are not interchangeable with4.0 geometry. No installer is included: before deployment, create a guarded matched-set installer/rollback, verify camera's current files/storage/mappings, archive/hash-verify/clear owned logs per procedure, and account for native WBI/config caching. Do not overwrite active mapped libraries or assume reboot-f reloads configuration. Configuration changes need a concrete recovery plan; the current camera remains4.0.

After installation and fresh boot, first inspect actual sizes/unique physical ranges of both unit0x127 allocations and unit0x50e. Then request1920x1080/5fps/YUY2 with other clients closed and use a bounded FFmpeg capture. Verify complete4,147,200-byte frames, returned SSYC dimensions/compression, coherent content and stream-end cleanup. Keep captured data off camera where possible. If any allocation or metadata check fails, collect evidence and restore the matched baseline; do not loosen guards.

Host command (run only when the device is streaming the new candidate):

    ffmpeg -f dshow -video_size 1920x1080 -framerate 5 -pixel_format yuyv422 -i video="ZV-E10" -frames:v 3 -an -c:v rawvideo -f rawvideo hd-first.yuy2

Wrap the process in a wall-clock timeout; waiting for three frames alone is not a bounded test. Three complete frames must total12,441,600 bytes. Raw format inspection: ffplay -f rawvideo -pixel_format yuyv422 -video_size1920x1080 -framerate5 hd-first.yuy2 (insert spaces after option names).
'''
# Keep the inspection command directly copyable.
r=r.replace('-video_size1920x1080 -framerate5','-video_size 1920x1080 -framerate 5').replace(' (insert spaces after option names).','.')
(O/'README.md').write_text(r)
P=O/'candidate';P.mkdir(exist_ok=True)
for name in ['yuy2_1080_v41hd.so','libInfraStreamingUsb.so']:shutil.copy2(O/'build'/name,P/name)
shutil.copy2(O/'DmmConfig.bin',P/'DmmConfig.bin');shutil.copy2('outputs/vga-v40/usbg_video.ko',P/'usbg_video.ko');shutil.copy2(O/'README.md',P/'README.md')
B=P/'baseline-v40';B.mkdir(exist_ok=True)
for name in ['libInfraStreamingUsb.so','yuy2_640_v40vga.so']:shutil.copy2(Path('outputs/vga-v40/build')/name,B/name)
shutil.copy2('D:/02_Development_And_Projects/pmca-re/dumps/camera_2025/usr/setting/DmmConfig.bin',B/'DmmConfig.bin')
m['memory_plan']=plan;m['package_status']='CANDIDATE_NOT_INSTALLED_NO_INSTALLER';m['files']={}
for p in P.rglob('*'):
 if p.is_file():m['files'][p.relative_to(P).as_posix()]={'bytes':p.stat().st_size,'md5':hashlib.md5(p.read_bytes()).hexdigest(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(P/'manifest.json').write_text(json.dumps(m,indent=2));
with zipfile.ZipFile(O/'hd-v41-candidate.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in P.rglob('*'):
  if p.is_file():z.write(p,p.relative_to(P))
print('Candidate bundle prepared; no camera changes')
