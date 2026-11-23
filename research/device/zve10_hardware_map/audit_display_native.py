"""Offline display contract audit. No camera access or executable payload output."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC

BASE=0x635c6000


def section_info(path):
    with path.open('rb') as f:
        e=ELFFile(f)
        result={s.name:s.data() for s in e.iter_sections() if s['sh_type']!='SHT_NOBITS'}
        reloc={}
        for s in e.iter_sections():
            if s['sh_type']!='SHT_REL':continue
            st=e.get_section(s['sh_link'])
            def symbol_name(r):
                symbol=st.get_symbol(r['r_info_sym'])
                return symbol.name or (e.get_section(symbol['st_shndx']).name if isinstance(symbol['st_shndx'],int) else '')
            reloc[e.get_section(s['sh_info']).name]={r['r_offset']:symbol_name(r) for r in s.iter_relocations()}
    return result,reloc


def audit(image,liro,backup,libobj):
    assert hashlib.md5(image).hexdigest()=='cdcae9d4fdbf66a33704a4c7564e346d'
    assert hashlib.sha256(liro.read_bytes()).hexdigest()=='72b77031f00679877ac04edf452e9f49e5fbca05cb4ee4554ddd2e5243e8e0cc'
    assert hashlib.sha256(libobj.read_bytes()).hexdigest()=='bc0deb2f0e94218752e42ce6f5a3576d7456971eb63fbde705ffbd9b3a7fdeea'
    sections,reloc=section_info(liro)
    assert struct.unpack_from('<I',sections['.init.text'],0x420)[0]==0xe2800024
    assert reloc['.init.text'][0x424]=='memcpy' and reloc['.init.text'][0x4b0]=='.init.data'
    bindings={}
    for offset,slot,name in [(0x1980c,0x298,'Backup_read'),(0x19828,0x264,'Backup_nread'),
                             (0x19860,0x29c,'Backup_read_multi'),(0x199b8,0x2e0,'Backup_read_4Byte'),
                             (0x19208,0x188,'Vspin_lock'),(0x19224,0x190,'Vspin_unlock')]:
        assert reloc['.init.data'][slot-0x24]==name
        # The Thumb LDR.W encoding contains the corresponding callback slot.
        assert struct.pack('<H',0x3000|slot) in image[offset:offset+28]
        bindings[hex(offset)]={'callback_slot':hex(slot),'liro_init_data_offset':hex(slot-0x24),'symbol':name}
    cpu=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
    cpu.mem_map(BASE,0x02000000);cpu.mem_write(BASE,image)
    cpu.mem_map(0x2000000,0x4000);cpu.mem_map(0x2100000,4096)
    cpu.mem_map(0xf2910000,0x3000)
    stack=0x2003f00;counter=0x2000100;context=0x64560304
    def call(entry,args):
        for reg,val in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):cpu.reg_write(reg,val)
        cpu.reg_write(UC_ARM_REG_SP,stack);cpu.reg_write(UC_ARM_REG_LR,0x2100001)
        cpu.emu_start((BASE+entry)|1,0x2100000,count=2000)
        assert cpu.reg_read(UC_ARM_REG_PC)==0x2100000
        assert cpu.reg_read(UC_ARM_REG_SP)==stack
    wait_results=[]
    for selector in (0,1):
        for initial in (0,1):
            for pending in (0,1):
                cpu.mem_write(counter,struct.pack('<I',initial))
                cpu.mem_write(context+4,struct.pack('<II',pending if selector==0 else 1-pending,pending if selector==1 else 1-pending))
                cpu.mem_write(stack,struct.pack('<I',4))
                call(0x504190,[selector,counter,2,3])
                advance=initial+1>=2 and not pending
                assert cpu.reg_read(UC_ARM_REG_R0)==(4 if advance else 3)
                assert struct.unpack('<I',cpu.mem_read(counter,4))[0]==(0 if advance else initial+1)
                wait_results.append({'selector':selector,'initial_counter':initial,'threshold':2,'pending':pending,'advanced':advance})
    writes=[]
    def io_write(cpu,access,address,size,value,_):
        if address>=0xf0000000:
            assert size==4
            writes.append((address,value))
    hook=cpu.hook_add(UC_HOOK_MEM_WRITE,io_write)
    gpio_results=[]
    for bank in (0,11,17):
        for bit in (0,20,31):
            for high in (False,True):
                writes.clear()
                call(0x808cca if high else 0x808cd6,[bank,bit,0,0])
                expected=0xf2910000+(bank<<8)+(0x44 if high else 0x48)
                assert writes==[(expected,1<<bit)],writes
                gpio_results.append({'bank':bank,'bit':bit,'high':high,'address':hex(expected),'mask':hex(1<<bit)})
    writes.clear();call(0x808cca,[18,0,0,0]);assert not writes
    # Leave the original GPIO instructions intact and stub only the LiRo lock callbacks.
    lock_calls = []
    def lock_callback(emulator, address, size, _data):
        lock_calls.append((address, emulator.reg_read(UC_ARM_REG_R0)))
        emulator.reg_write(UC_ARM_REG_PC, emulator.reg_read(UC_ARM_REG_LR))

    lock_hooks = [cpu.hook_add(UC_HOOK_CODE, lock_callback, begin=address, end=address)
                  for address in (BASE + 0x19208, BASE + 0x19224)]
    gpio_config_cases = []
    descriptor = counter + 0x100
    for bank, function, direction, input_enable, pad, expected_offsets in (
        (11, 1, 1, 1, 1, (0x34, 0x04, 0x24, 0x2048, 0x2054)),
        (11, 0, 0, 0, 0, (0x38, 0x08, 0x28, 0x2048, 0x2058)),
        (11, 1, -1, 1, -1, (0x34, 0x28, 0x2044, 0x2058)),
        (18, 1, 1, 1, 1, ()),
    ):
        lock_calls.clear()
        writes.clear()
        cpu.mem_write(descriptor, struct.pack('<IiIi', function, direction, input_enable, pad))
        call(0x808c26, [bank, 20, descriptor])
        base = 0xf2910000 + (bank << 8)
        assert writes == [(base + offset, 1 << 20) for offset in expected_offsets], (bank, function, direction, input_enable, pad, [(hex(a), v) for a, v in writes])
        assert lock_calls == ([(BASE + 0x19208, 9), (BASE + 0x19224, 9)] if bank < 18 else [])
        gpio_config_cases.append({
            'bank': bank, 'bit': 20, 'descriptor_inputs': [function, direction, input_enable, pad],
            'mmio_write_addresses': [hex(address) for address, _ in writes],
            'lock_ids': [argument for _, argument in lock_calls],
        })
    for lock_hook in lock_hooks:
        cpu.hook_del(lock_hook)
    cpu.hook_del(hook)
    # Narrow saved-backup inspection; do not enumerate unrelated settings, keys or identity units.
    from pmca.backup import BackupFile
    keys=[0x5f0206,0x5f01d8,0x5f052f,0xf900ac,0xf90068,0xf901ab,0xf901ac,
          0xf9088f,0xf90890,0xf9040d,0xf9040e,0xf90375,0xf90376,0xf90377,0xf90378,
          0xf90560,0xf90561,0xf90562,0xf90563]
    properties={}
    with backup.open('rb') as f:
        bf=BackupFile(f)
        for key in keys:
            value=bf.getProperty(key).data
            properties[hex(key)]={'bytes':len(value),'value_le':hex(int.from_bytes(value,'little')),
                                  'scope':'saved backup only; current-body state not verified'}
        profile_ids=struct.unpack_from('<304I',image,0x645ecaf0-BASE)
        assert struct.unpack_from('<I',image,0x645ecaf0-BASE+304*4)[0]==0
        profile=bytearray()
        for key in profile_ids:
            value=bf.getProperty(key).data;assert len(value)==1;profile.extend(value)
    # Fixed expected body pin is an observation in this saved file, not a portable wiring constant.
    pinbank=int(properties['0xf9088f']['value_le'],0);pinbit=int(properties['0xf90890']['value_le'],0)
    assert pinbank==11 and pinbit==20
    # These exported APIs are empty in this identified ELF. Do not infer a working framebuffer API from names.
    with libobj.open('rb') as f:
        elf=ELFFile(f);sym=elf.get_section_by_name('.dynsym')
        symbols={s.name:s['st_value']&~1 for s in sym.iter_symbols()}
        noop=[]
        for name in ['GRM_screenGetOnBitmap','GRM_fbrmInitializeYUV','GRM_fbrmPrepareUpdateYUV','GRM_fbrmUpdateYUV','GRM_fbrmFillrectYUV','GRM_fbrmRectblitYUV']:
            va=symbols[name]
            seg=next(s for s in elf.iter_segments() if s['p_type']=='PT_LOAD' and s['p_vaddr']<=va< s['p_vaddr']+s['p_filesz'])
            f.seek(seg['p_offset']+va-seg['p_vaddr']);code=f.read(8)
            assert code==bytes.fromhex('80b5002000af80bd'),(name,code.hex())
            noop.append({'symbol':name,'elf_va':hex(va),'effect':'returns zero without reading arguments or changing pointed-to memory'})
    return {'schema_version':1,'status':'offline-original-instruction-contracts-verified',
            'firmware_sha256':hashlib.sha256(image).hexdigest(),
            'liro_sha256':hashlib.sha256(liro.read_bytes()).hexdigest(),
            'backup_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),
            'libobj_sha256':hashlib.sha256(libobj.read_bytes()).hexdigest(),
            'callback_bindings':bindings,'wait_helper':{'file_offset':'0x504190','cases':wait_results,'time_unit':'invocation count, tick duration not recovered'},
            'gpio_output_helpers':{'cases':gpio_results,'invalid_bank_18_no_mmio_write':True,'hardware_alias_effects_emulated':False},
            'selected_saved_backup_properties':properties,
            'gpio_config_wrapper':{'file_offset':'0x808c26','cases':gpio_config_cases},
            'saved_profile0':{'bytes':304,'source_id_list_va':'0x645ecaf0','source_id_list_zero_terminated':True,'all_selected_properties_one_byte':True,
                              'destination_firmware_va':'0x6455fe88','sha256':hashlib.sha256(profile).hexdigest(),'current_body_binding':False},
            'saved_pin_slot_2':{'bank_property':'0xf9088f','bit_property':'0xf90890','bank':pinbank,'bit':pinbit,
                                'set_address':hex(0xf2910000+(pinbank<<8)+0x44),'clear_address':hex(0xf2910000+(pinbank<<8)+0x48),'mask':hex(1<<pinbit),'electrical_role':'not independently identified'},
            'empty_exported_apis':noop,'camera_access_performed':False,'hardware_display_initialized':False,
            'limits':['GPIO MMIO writes recorded in an emulator; no physical effect modeled or verified',
                      'Saved Backup.bin is not a current-body capture or universal panel configuration',
                      'Full pixel routing, serial panel transaction, clock prerequisites and frame completion remain unresolved']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(a.repo));dump=a.repo/'.local/dumps/camera_2025'
    result=audit((a.repo/'.local/dumps/av-cam.bin').read_bytes(),dump/'usr/usr/kmod/liro.ko',dump/'usr/setting/Backup.bin',dump/'usr/usr/lib/libObj.so')
    a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'wait_cases':len(result['wait_helper']['cases']),
                      'gpio_cases':len(result['gpio_output_helpers']['cases']), 'empty_exports':len(result['empty_exported_apis']), 'camera_access_performed':False}))
