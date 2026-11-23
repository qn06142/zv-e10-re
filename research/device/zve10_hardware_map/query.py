"""Query atlas metadata only. This tool cannot read or write camera registers."""
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('query', help='Physical address such as 0xf3445108, or a source symbol substring')
    p.add_argument('--data', type=Path, default=Path(__file__).resolve().parents[3]/'docs/hardware/data')
    args = p.parse_args()
    platform = json.loads((args.data/'platform.json').read_text())
    native = json.loads((args.data/'native-accessors.json').read_text())['accessors']
    named = json.loads((args.data/'register-contracts.json').read_text())['registers']
    irq_only = platform.get('udif_irq_only_channels', [])
    crg = platform.get('crg_clock_domains', [])
    io_maps = platform.get('static_io_mappings', [])
    try:
        address = int(args.query, 0)
    except ValueError:
        q = args.query.casefold()
        result = {'symbols': [x for x in platform['symbols'] if q in x['name'].casefold()],
                  'declared_windows': [x for x in platform['udif_windows'] if q in x['name_expression'].casefold()],
                  'udif_irq_only_channels': [x for x in irq_only if q in x['name_expression'].casefold() or q in x['irq_expression'].casefold()],
                  'crg_clock_domains': [x for x in crg if q in x['id'].casefold() or q in x['base'].casefold()],
                  'static_io_mappings': [x for x in io_maps if q in x['virtual'].casefold() or q in x['physical'].casefold()],
                  'named_registers': [x for x in named if q in x['name'].casefold()]}
    else:
        result = {'address': hex(address),
                  'named_registers': [x for x in named if int(x['address'], 0) == address],
                  'declared_windows': [x for x in platform['udif_windows'] if int(x['base'], 0) <= address <= int(x['end_inclusive'], 0)],
                  'udif_irq_only_channels': [x for x in irq_only if x['gpl_irq'] == address],
                  'crg_clock_domains': [x for x in crg if int(x['base'], 0) <= address < int(x['base'], 0) + 0x1000],
                  'static_io_mappings': [x for x in io_maps if int(x['physical'], 0) <= address < int(x['physical'], 0) + int(x['length'], 0) or int(x['virtual'], 0) <= address < int(x['virtual'], 0) + int(x['length'], 0)],
                  'native_accessors': [x for x in native if int(x['register'], 0) == address]}
    result['camera_access_performed'] = False
    result['warning'] = 'Metadata only. An entry is not an access permission or initialization recipe.'
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
