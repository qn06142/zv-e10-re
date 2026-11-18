"""Build the experimental Sony SDF 1080p YUY2 USB 3.0 24fps candidate offline."""
from pathlib import Path
import shutil
import hashlib,json,re,struct,subprocess
from keystone import Ks,KS_ARCH_ARM,KS_MODE_THUMB
from elftools.elf.elffile import ELFFile
import argparse

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--repo',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--streaming-image',type=Path,required=True)
ap.add_argument('--kernel', type=Path,
                help='Verified chunk kernel to package; defaults to the existing output kernel.')
ap.add_argument('--cc',type=Path,default=Path(r'C:\msys64\ucrt64\bin\arm-none-eabi-gcc.exe'))
args=ap.parse_args()
ROOT=args.repo.resolve()
WORK=Path(__file__).resolve().parent;OUT=args.output.resolve();OUT.mkdir(parents=True,exist_ok=True)
CC=args.cc
kernel_input = (args.kernel or OUT / 'usbg_video.ko').resolve()
kernel_bytes = kernel_input.read_bytes()
kernel_md5 = hashlib.md5(kernel_bytes).hexdigest()
if kernel_md5 not in {
    '702b82f347b6fc25e8d46ddba1836743',
    '9ded6930932e7db541247c4b158b93fc',
}:
    raise ValueError('Unexpected chunk-kernel input: ' + kernel_md5)
kernel_output = OUT / 'usbg_video.ko'
install_template = (WORK.parent / 'install.sh').read_text(encoding='utf-8')
rollback_template = WORK.parent / 'rollback.sh'
if not rollback_template.is_file():
    raise FileNotFoundError(rollback_template)
from generate_guards import build as generate_guards
generate_guards(ROOT,WORK/"vga_guards.h")
from generate_port_guards import build as port_guards
port_guards(ROOT,WORK/"yc_port_guards.h")
cmn=(ROOT/'.local/dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so').read_bytes()
stream=args.streaming_image.read_bytes()
assert hashlib.md5(cmn).hexdigest()=='31308976206a837f6f5c571992d2b499'
assert hashlib.md5(stream).hexdigest()=='19461091c07aa6900829defb0060fcd6'
source=(WORK/'yuy2_1080_v43chunk.c').read_text()
for name,data in [('path_guard',stream[0x8e14:0x8e1e]),('data_guard',stream[0x9618:0x9622]),('ctrl_guard',cmn[0x12064:0x1206e])]:
 source=re.sub(r'(static const u8 '+name+r'\[10\]=)\{[^}]+\}',lambda m:m[1]+'{'+','.join(hex(b) for b in data)+'}',source)
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
guards=[]
for off in [0x7aa8,0x903e,0x8f9c,0x8dbe,0x894c,0x83c8]:
 data=stream[off:off+10];instructions=list(Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(data,off))
 assert sum(i.size for i in instructions)==10
 assert not any('pc' in i.op_str or i.mnemonic.startswith(('b','cb','it')) for i in instructions)
 guards.append('{'+','.join(hex(x) for x in data)+'}')
source=source.replace('EXTRA_GUARDS',','.join(guards))
cfg=(ROOT/'.local/dumps/camera_2025/usr/setting/DmmConfig.bin').read_bytes()
assert struct.unpack_from('<4I',cfg,0x11c24)==(0x276,0,0x333,0xffffffff)
assert struct.unpack_from('<5I',cfg,0x2e20)==(0x333,0x320000,0x10f,0,7)
assert struct.unpack_from('<5I',cfg,0x2e34)==(0x333,0x320000,0x10f,0,4)
manifest_path = OUT / 'manifest.json'
manifest_path.unlink(missing_ok=True)
if kernel_input != kernel_output:
    kernel_output.write_bytes(kernel_bytes)
(OUT/'yuy2_640.c').write_text(source)
common=['-mcpu=cortex-a5','-marm','-mfpu=vfpv4-d16','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mfloat-abi=soft','-O2','-fno-builtin','-fno-stack-protector','-fstack-usage','-nostdlib',f'-L{ROOT}/.local/build_sysroot/lib',f'-Wl,-rpath-link,{ROOT}/.local/build_sysroot/lib']
cmd=[str(CC),*common,'-fPIC','-fvisibility=hidden','-shared','-Wl,--hash-style=sysv,-soname,yuy2_1080_v43chunk.so,--no-undefined','-o',str(OUT/'yuy2_1080_v43chunk.so'),str(OUT/'yuy2_640.c'),'-DRAW_FRAME_CONVERSION_ONLY','-DRAW_LIVE_TARGET_ARM',f'-I{WORK}',str(WORK/'vga_resize.c'),str(WORK/'yc_port.c'),str(WORK/'yc_unpack.c'),str(WORK/'vga_contract.c'),str(WORK/'sony_yc_sds.c'),str(WORK/'sony_yc_metadata.c'),'-l:libc.so.6','-l:libdl.so.2','-l:libpthread-2.11.2.so','-lgcc']
subprocess.run(cmd,check=True)

from persistent_stream import build as build_stream
patched,report=build_stream(stream)
(OUT/'libInfraStreamingUsb.so').write_bytes(patched)
(OUT/'libInfraStreamingUsb.persistent.json').write_text(json.dumps(report,indent=2)+'\n')
artifact_guards = {
    'yuy2_1080_v43chunk.so': OUT / 'yuy2_1080_v43chunk.so',
    'libInfraStreamingUsb.v43.so': OUT / 'libInfraStreamingUsb.so',
    'usbg_video.v43.ko': kernel_output,
}
for staged_name, artifact in artifact_guards.items():
    digest = hashlib.md5(artifact.read_bytes()).hexdigest()
    pattern = r'(guard "\$D/' + re.escape(staged_name) + r'" )[0-9a-f]{32}'
    install_template, replacements = re.subn(
        pattern, lambda match: match[1] + digest, install_template
    )
    if replacements != 1:
        raise ValueError('Expected one installer guard for ' + staged_name)
(OUT / 'install.sh').write_bytes(install_template.replace('\r\n', '\n').encode('utf-8'))
shutil.copyfile(rollback_template, OUT / 'rollback.sh')
(OUT / 'README.md').write_bytes(
    b'# Offline HD UVC candidate\n\n'
    b'Revision 4.6. Built from the guarded source recipe and explicit input files.\n'
    b'Hardware capture and sustained delivery remain unverified.\n'
    b'The manifest records the exact packaged files and kernel dependency.\n'
)
manifest=dict(status='BUILT_NOT_HARDWARE_VERIFIED',deployment='NOT_INSTALLED',revision='4.6-1080p-usb3-24fps-candidate',
 position_independent=True,width=1920,height=1080,advertised_fps=24,observed_fps=None,
 pixel_format='8-bit YUY2 uncompressed; SDF hardware decompress to owned 1080p destination with Cat0 and Cat1',
 source_backend='NATIVE_VDF_PIN_SEND_PRIVATE_QUEUE_TO_SONY_SDF_OWNED_HD127_CHUNKED_USB3_24FPS',
 continuous_video=True,source_pool_scanning=False,source_transfer_free_mode=2,
 requested_native_output=[0,2,0,0x59000e],private_receiver_index=0x7fffff37,
 output_busy_behavior='REFUSE_WITHOUT_DISCONNECTING_EXISTING_PEER',
 native_output_availability='VGA_INPUT_PREVIOUSLY_CAPTURED; HD_RESIZER_OUTPUT_WITH_CAT1_TESTED',
 diagnostic_revision=False,functional_descriptor_fix=True,reference_cleanup_changed=False,
 metadata_settle_attempts=32,metadata_retry_delay_us=0,metadata_max_sleeps=0,
 rejected_descriptor_record='YC38RJ01',rejected_record_max_bytes=131152,
 no_image_metadata_handled=True,remaining_rejection_gates_unchanged=True,artificial_pacing_removed=True,hardware_completion_waits_preserved=True,
 required_kernel_version='yc42_chunk',required_kernel_md5=kernel_md5,
 crash_fix_verified=False,independent_usb_source_credit_retained_until_boot=True,
 synthetic_fallback=False,frame_bytes=4147200,packet_header_bytes=0,
 cold_boot_required=True,stream_sessions_per_boot=1,
 required_dmm_config_md5='9f197ff9b300e49ab531b6f9e794253e',
 source_requires_1920x1080=True, high_depth_target_deferred_by_user=True,
 physical_pool_sizes_changed=False, live_allocation_availability_unverified=True, chunk_bytes=614400, transport_fragments_per_frame=7, dmm_aliases_unchanged=True,files={})
for name in ['yuy2_1080_v43chunk.so','libInfraStreamingUsb.so','usbg_video.ko','install.sh','rollback.sh','README.md']:
 data=(OUT/name).read_bytes();manifest['files'][name]=dict(bytes=len(data),md5=hashlib.md5(data).hexdigest(),sha256=hashlib.sha256(data).hexdigest())
temporary_manifest = OUT / 'manifest.json.tmp'
temporary_manifest.write_text(json.dumps(manifest,indent=2)+'\n')
temporary_manifest.replace(manifest_path)
print(json.dumps(manifest,indent=2))
