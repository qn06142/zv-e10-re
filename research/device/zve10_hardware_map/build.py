"""Build a source-backed hardware inventory. Offline only; never accesses a camera."""
import argparse
import ast
import hashlib
import json
import re
import struct
from collections import defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from capstone.arm import ARM_OP_IMM, ARM_OP_MEM, ARM_OP_REG, ARM_REG_PC, ARM_REG_R0, ARM_REG_R2, ARM_REG_R3, ARM_REG_LR


def digest(data):
    return hashlib.sha256(data).hexdigest()


def clean_comments(text):
    return re.sub(r'/\*.*?\*/', lambda m: '\n' * m[0].count('\n'), text, flags=re.S)


class Definitions:
    """Conservative C integer macro reader; no eval, CPP execution or condition guessing."""
    def __init__(self):
        self.rows = defaultdict(list)

    def add(self, text, source):
        for number, line in enumerate(clean_comments(text).splitlines(), 1):
            m = re.match(r'\s*#\s*define\s+(\w+)(\([^)]*\))?\s+(.+)', line)
            if not m:
                continue
            params = None if m[2] is None else [x.strip() for x in m[2][1:-1].split(',')]
            self.rows[m[1]].append({'source': source, 'line': number, 'parameters': params,
                                    'expression': m[3].split('//')[0].strip()})

    def resolve(self, name, args=(), trail=()):
        if name in trail or name not in self.rows:
            raise ValueError(name)
        values = set()
        for row in self.rows[name]:
            params = row['parameters']
            if params is None and args or params is not None and len(params) != len(args):
                raise ValueError(name)
            env = dict(zip(params or [], args))
            values.add(self.expression(row['expression'], env, trail + (name,)))
        if len(values) != 1:
            raise ValueError('Conditional/redefined macro: ' + name)
        return values.pop()

    def expression(self, text, env=None, trail=()):
        text = re.sub(r'\b(0[xX][0-9a-fA-F]+|\d+)[uUlL]+\b', r'\1', text)
        tree = ast.parse(text, mode='eval').body
        env = env or {}

        def visit(n):
            if isinstance(n, ast.Constant) and type(n.value) is int:
                return n.value
            if isinstance(n, ast.Name):
                return env[n.id] if n.id in env else self.resolve(n.id, trail=trail)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and not n.keywords:
                return self.resolve(n.func.id, tuple(visit(a) for a in n.args), trail)
            if isinstance(n, ast.UnaryOp):
                value = visit(n.operand)
                if isinstance(n.op, ast.USub): return -value
                if isinstance(n.op, ast.UAdd): return value
                if isinstance(n.op, ast.Invert): return ~value
            if isinstance(n, ast.BinOp):
                a, b = visit(n.left), visit(n.right)
                if isinstance(n.op, ast.Add): return a+b
                if isinstance(n.op, ast.Sub): return a-b
                if isinstance(n.op, ast.Mult): return a*b
                if isinstance(n.op, (ast.Div, ast.FloorDiv)) and a >= 0 and b > 0: return a//b
                if isinstance(n.op, ast.LShift): return a << b
                if isinstance(n.op, ast.RShift): return a >> b
                if isinstance(n.op, ast.BitOr): return a | b
                if isinstance(n.op, ast.BitAnd): return a & b
            raise ValueError('Unsupported integer expression: ' + text)
        return visit(tree)


def calls(text, name):
    for m in re.finditer(r'\b' + re.escape(name) + r'\s*\(', text):
        depth, start, args = 1, m.end(), []
        for i in range(start, len(text)):
            if text[i] == '(': depth += 1
            elif text[i] == ')':
                depth -= 1
                if depth == 0:
                    args.append(text[start:i].strip())
                    yield text[:m.start()].count('\n') + 1, args
                    break
            elif text[i] == ',' and depth == 1:
                args.append(text[start:i].strip()); start = i+1


def extract_native(image, observations, matched_pages):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB); md.detail = True
    records = []
    casts = {'uxtb', 'uxth', 'sxtb', 'sxth', 'lsrs', 'lsls', 'asrs'}
    end = min(0x920000, len(image)-64)
    for start in range(0x1000, end, 2):
        h = struct.unpack_from('<H', image, start)[0]
        if h & 0xf800 != 0x4800 or (h >> 8) & 7 != 3:
            continue
        pool = ((start+4) & ~3) + (h & 255)*4
        if pool+4 > len(image): continue
        base = struct.unpack_from('<I', image, pool)[0]
        if not 0xf0000000 <= base < 0xff000000: continue
        seq = []
        for ins in md.disasm(image[start:start+40], start):
            seq.append(ins)
            if ins.mnemonic == 'bx': break
            if len(seq) > 8: break
        if len(seq) < 5 or seq[-1].mnemonic != 'bx' or seq[-1].op_str != 'lr': continue
        core, transforms = [], []
        valid = True
        for ins in seq[1:-1]:
            name = ins.mnemonic.split('.')[0]
            if name in casts:
                op = ins.operands
                if len(op) < 2 or op[0].type != ARM_OP_REG or op[1].type != ARM_OP_REG or op[0].reg != ARM_REG_R0 or op[1].reg != ARM_REG_R0:
                    valid = False; break
                transforms.append({'file_offset': hex(ins.address), 'operation': name, 'operands': ins.op_str})
            else: core.append(ins)
        if not valid or len(core) != 3: continue
        load, insert, store = core
        if [i.mnemonic.split('.')[0] for i in core] != ['ldr', 'bfi', 'str']: continue
        if len(load.operands) != 2 or len(store.operands) != 2: continue
        if any(i.operands[0].type != ARM_OP_REG or i.operands[0].reg != ARM_REG_R2 or i.operands[1].type != ARM_OP_MEM for i in (load, store)): continue
        lm, sm = load.operands[1].mem, store.operands[1].mem
        if lm.base != ARM_REG_R3 or sm.base != ARM_REG_R3 or lm.index or sm.index or lm.disp != sm.disp: continue
        op = insert.operands
        if len(op) != 4 or op[0].reg != ARM_REG_R2 or op[1].reg != ARM_REG_R0 or op[2].type != ARM_OP_IMM or op[3].type != ARM_OP_IMM: continue
        shift, width = op[2].imm, op[3].imm
        if not 0 <= shift < 32 or not 1 <= width <= 32-shift: continue
        address = base + lm.disp
        if address & 3 or not 0xf0000000 <= address < 0xff000000: continue
        finish = seq[-1].address + seq[-1].size
        pages = {x & ~4095 for x in range(start, finish)}
        records.append({'file_offset': hex(start), 'firmware_va': hex(0x635c6000+start),
                        'instruction_set': 'Thumb', 'address_space': ('candidate_physical_mmio' if address < 0xf5000000 else 'unclassified_high_address'),
                        'register': hex(address), 'access_width_bits': 32, 'lsb': shift, 'width_bits': width,
                        'mask': hex(((1 << width)-1) << shift), 'input_transforms': transforms,
                        'instruction_pattern': 'literal base; 32-bit load; BFI; 32-bit store; return',
                        'source_bytes_sha256': digest(image[start:finish]),
                        'current_camera_code_page_match': pages <= matched_pages,
                        'field_meaning': None, 'reset_value': None, 'required_value': None,
                        'device_read_side_effects': 'unknown', 'device_write_side_effects': 'unknown',
                        'read_or_write_permission': False,
                        'observations': observations.get(address, [])})
    return records


def parse_clock_init(entry, defs, base_line):
    """Resolve UDIF_CLOCK_INIT fields inside a single UDIF channel block."""
    for clk_line, clk_args in calls(entry, 'UDIF_CLOCK_INIT'):
        if len(clk_args) != 9:
            continue
        vals = [defs.expression(x) for x in clk_args]
        hs, hc, hsh, ds, dc, dsh, dss, dsc, dssh = vals
        return {
            'hclk': {'set': hex(hs), 'clr': hex(hc), 'shift': hsh, 'mask': hex(1 << hsh)} if (hs or hc) else None,
            'dclk': {'set': hex(ds), 'clr': hex(dc), 'shift': dsh, 'mask': hex(1 << dsh)} if (ds or dc) else None,
            'dclksel': {'set': hex(dss), 'clr': hex(dsc), 'shift': dssh, 'mask': hex(0xff << dssh)} if (dss or dsc) else None,
            'source_line': base_line + clk_line - 1,
        }
    return None


def parse_crg_domains(kernel, defs):
    """Extract CRG11 clock-divider physical bases from mach-cxd900x0/udif/clock.c."""
    rel_path = 'arch/arm/mach-cxd900x0/udif/clock.c'
    text = clean_comments((kernel / rel_path).read_text(encoding='utf-8'))
    lines = text.splitlines()
    domains = []
    for line, args in calls(text, 'DECLARE_DIVCLK'):
        if len(args) != 2 or lines[line - 1].lstrip().startswith('#'):
            continue
        phys_expr = args[1].replace('VA_CLKCRG', 'CXD900X0_CLKCRG')
        base = defs.expression(phys_expr)
        domains.append({
            'id': args[0],
            'vaddr_expression': args[1],
            'base': hex(base),
            'crcdc_offset': '0x30',
            'crdm_formula': 'base + 0x100 + (clk << 4)',
            'address_space': 'physical_mmio',
            'source': rel_path,
            'line': line,
            'hardware_body_binding': 'not established by source declaration alone',
        })
    return domains


def parse_static_io_mappings(kernel, defs):
    """Extract cxd900x0_io_desc[] static MMU mappings from mach-cxd900x0/core.c."""
    rel_path = 'arch/arm/mach-cxd900x0/core.c'
    text = clean_comments((kernel / rel_path).read_text(encoding='utf-8'))
    block_match = re.search(r'cxd900x0_io_desc\[\]\s+__initdata\s*=\s*\{(.*?)\};', text, re.S)
    if not block_match:
        raise ValueError('Missing cxd900x0_io_desc table in core.c')
    entry_re = re.compile(
        r'\{\s*\.virtual\s*=\s*IO_ADDRESS\(([^)]+)\)\s*,\s*\.pfn\s*=\s*__phys_to_pfn\(([^)]+)\)\s*,\s*'
        r'\.length\s*=\s*([^,]+)\s*,\s*\.type\s*=\s*(\w+)\s*\}'
    )
    mappings = []
    for m in entry_re.finditer(block_match.group(1)):
        line = text[:block_match.start(1) + m.start()].count('\n') + 1
        virt = defs.expression(m.group(1).strip())
        phys = defs.expression(m.group(2).strip())
        length = defs.expression(m.group(3).strip())
        mappings.append({
            'virtual': hex(virt),
            'physical': hex(phys),
            'length': hex(length),
            'identity_mapped': virt == phys,
            'type_initializer': m.group(4).strip(),
            'runtime_override_in_map_io': 'memtype_io',
            'source': rel_path,
            'line': line,
        })
    return mappings


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel', type=Path, required=True)
    p.add_argument('--firmware', type=Path, required=True)
    p.add_argument('--observations', type=Path)
    p.add_argument('--page-matches', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    sources = ['include/asm-generic/sizes.h', 'arch/arm/mach-cxd900x0/include/mach/platform.h',
               'arch/arm/mach-cxd900x0/include/mach/irqs.h', 'arch/arm/mach-cxd900x0/include/mach/regs-gpio.h',
               'arch/arm/mach-cxd900x0/include/mach/regs-clk.h', 'arch/arm/mach-cxd900x0/include/mach/regs-misc.h',
               'arch/arm/mach-cxd900x0/include/mach/regs-timer.h', 'arch/arm/mach-cxd900x0/udif/platform.c',
               'arch/arm/mach-cxd900x0/include/mach/regs-octrl.h', 'arch/arm/mach-cxd900x0/include/mach/regs-ddrc.h',
               'arch/arm/mach-cxd900x0/include/mach/regs-sramc.h', 'arch/arm/mach-cxd900x0/include/mach/regs-syncsramc.h',
               'arch/arm/mach-cxd900x0/include/mach/regs-adc.h', 'arch/arm/mach-cxd900x0/include/mach/regs-avbckg.h',
               'arch/arm/mach-cxd900x0/include/mach/regs-bam.h', 'arch/arm/mach-cxd900x0/include/mach/noncache.h',
               'arch/arm/mach-cxd900x0/include/mach/pl310.h', 'arch/arm/mach-cxd900x0/include/mach/udif/platform.h']
    impl_sources = ['arch/arm/mach-cxd900x0/udif/clock.c', 'arch/arm/mach-cxd900x0/clock.c',
                    'arch/arm/mach-cxd900x0/core.c', 'arch/arm/mach-cxd900x0/adrs_conv.c']
    defs = Definitions(); provenance = []
    for source in sources:
        data = (args.kernel/source).read_bytes()
        defs.add(data.decode('utf-8'), source)
        provenance.append({'kind': 'Sony GPL source', 'path': source, 'sha256_lf': digest(data.replace(b'\r\n', b'\n'))})
    for source in impl_sources:
        data = (args.kernel/source).read_bytes()
        provenance.append({'kind': 'Sony GPL implementation source', 'path': source, 'sha256_lf': digest(data.replace(b'\r\n', b'\n'))})
    symbols, unresolved = [], []
    for name, rows in sorted(defs.rows.items()):
        if rows[0]['parameters'] is not None: continue
        try: value = defs.resolve(name)
        except (ValueError, SyntaxError, KeyError, TypeError):
            unresolved.append({'name': name, 'definitions': rows}); continue
        symbols.append({'name': name, 'value': hex(value), 'definitions': rows,
                        'evidence': 'GPL source definition; target configuration and wiring require confirmation'})
    udif = args.kernel/'arch/arm/mach-cxd900x0/udif/platform.c'
    windows = []; bound_irq_lines = set()
    udif_text = clean_comments(udif.read_text())
    udif_lines = udif_text.splitlines(keepends=True)
    for line, values in calls(udif_text, '__UDIF_IOMEM_INIT'):
        if len(values) != 3 or udif_lines[line-1].lstrip().startswith('#'): continue
        try: address, size = [defs.expression(x) for x in values[1:]]
        except (ValueError, SyntaxError, KeyError, TypeError): continue
        # Bind only interrupt and clock initializers before this channel entry closes.
        tail=''.join(udif_lines[line-1:])
        closing=re.search(r'\n\s*},',tail)
        entry=tail[:closing.start()] if closing else ''
        interrupts=[]
        for irq_line,irq_args in calls(entry,'UDIF_INTRPT_INIT'):
            if len(irq_args)!=3:continue
            try:irq=defs.expression(irq_args[1])
            except (ValueError,SyntaxError,KeyError,TypeError):continue
            src_line = line+irq_line-1
            bound_irq_lines.add(src_line)
            interrupts.append({'gpl_irq':irq,'expression':irq_args[1],'source_line':src_line})
        clock = parse_clock_init(entry, defs, line)
        windows.append({'name_expression': values[0], 'base': hex(address), 'size': hex(size),
                        'end_inclusive': hex(address+size-1), 'address_space': 'physical_mmio',
                        'source': 'arch/arm/mach-cxd900x0/udif/platform.c', 'line': line,
                        'interrupts':interrupts, 'clock': clock,
                        'hardware_body_binding': 'not established by source declaration alone'})
    irq_only = []
    for line, irq_args in calls(udif_text, 'UDIF_INTRPT_INIT'):
        if len(irq_args) != 3 or line in bound_irq_lines or udif_lines[line-1].lstrip().startswith('#'):
            continue
        irq = defs.expression(irq_args[1])
        irq_only.append({'name_expression': irq_args[0], 'gpl_irq': irq, 'irq_expression': irq_args[1],
                         'flags_expression': irq_args[2], 'source': 'arch/arm/mach-cxd900x0/udif/platform.c',
                         'line': line, 'hardware_body_binding': 'not established by source declaration alone'})
    crg_domains = parse_crg_domains(args.kernel, defs)
    io_mappings = parse_static_io_mappings(args.kernel, defs)
    observations = defaultdict(list)
    if args.observations:
        capture=json.loads(args.observations.read_text())
        if not isinstance(capture,dict) or capture.get('schema_version')!=1:
            raise ValueError('Observations need versioned mode/date/identity metadata')
        for row in capture['register_reads']:
            observations[row['address']].append({'value': hex(row['value']), 'mode': capture['mode'],
                'date': capture['date'], 'boot_id':capture['boot_id'],
                'camera_firmware_md5':capture['camera_firmware_md5'],
                'scope': 'single captured mode/session; not a reset or required value'})
    matched_pages = set()
    if args.page_matches:
        matched_rows = [x for x in json.loads(args.page_matches.read_text()) if x['matches_offline_page']]
        matched_pages = {int(x['offset'], 0) for x in matched_rows}
    image = args.firmware.read_bytes()
    if hashlib.md5(image).hexdigest() != 'cdcae9d4fdbf66a33704a4c7564e346d':
        raise ValueError('Unexpected reference firmware; review scan bounds and provenance')
    if args.page_matches:
        for row in matched_rows:
            offset=int(row['offset'],0)
            if row['bytes'] != 4096 or digest(image[offset:offset+4096]) != row['sha256']:
                raise ValueError('Reference page does not match recorded camera-page hash')
    native = extract_native(image, observations, matched_pages)
    platform = {'schema_version': 1, 'sources': provenance, 'symbols': symbols,
                'unresolved_definitions': unresolved, 'udif_windows': windows,
                'udif_irq_only_channels': irq_only, 'crg_clock_domains': crg_domains,
                'static_io_mappings': io_mappings,
                'limits': 'No C preprocessor conditions selected; differing alternatives left unresolved. Definitions are not an access allowlist.'}
    corpus = {'schema_version': 1, 'reference_firmware_sha256': digest(image), 'firmware_base': '0x635c6000',
              'scan_bounds_file_offsets': ['0x1000', hex(min(0x920000, len(image)-64))],
              'executable_extent_confirmed': False,
              'limits': 'Conservative Thumb patterns only; unreferenced starts may be data, not function boundaries. No device semantics or safe access inferred.',
              'observation_input_sha256': digest(args.observations.read_bytes()) if args.observations else None,
              'page_match_input_sha256': digest(args.page_matches.read_bytes()) if args.page_matches else None,
              'accessors': native}
    for name, data in [('platform.json', platform), ('native-accessors.json', corpus)]:
        (args.out/name).write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
    summary = {'platform_numeric_symbols': len(symbols), 'udif_channel_windows': len(windows),
               'udif_windows_with_resolved_clocks': sum(bool(x['clock']) for x in windows),
               'udif_irq_only_channels': len(irq_only),
               'crg_clock_domains': len(crg_domains),
               'static_io_mappings': len(io_mappings),
               'native_rmw_accessor_candidates': len(native), 'native_register_words': len({x['register'] for x in native}),
               'observed_register_words': len(observations),
               'udif_windows_with_resolved_irqs':sum(bool(x['interrupts']) for x in windows),
               'current_camera_page_matched_accessors': sum(x['current_camera_code_page_match'] for x in native),
               'native_bank_register_counts': {hex(bank):len({x['register'] for x in native if int(x['register'],16)&0xffff0000==bank}) for bank in sorted({int(x['register'],16)&0xffff0000 for x in native})},
               'camera_access_performed': False, 'complete_hardware_map': False}
    (args.out/'coverage.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__': main()
