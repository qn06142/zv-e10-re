"""Check atlas invariants and independently anchored platform arithmetic. Offline only."""
import argparse
import importlib.util
import json
from pathlib import Path


def verify(data, builder):
    platform = json.loads((data/'platform.json').read_text())
    native = json.loads((data/'native-accessors.json').read_text())['accessors']
    named = json.loads((data/'register-contracts.json').read_text())['registers']
    symbols = {x['name']: int(x['value'], 0) for x in platform['symbols']}
    expected = {'CXD900X0_GPIO_BASE': 0xf2910000, 'CXD900X0_MISC_BASE': 0xf2915000,
                'DMA330_IO_BASE': 0xf0030000, 'DMAC_IO_BASE': 0xf0000000, 'DMAC1_IO_BASE': 0xf0010000}
    for key, value in expected.items(): assert symbols[key] == value, key
    windows = {x['name_expression']: x for x in platform['udif_windows']}
    for key, address, size in [('I2C_NAME "0"', 0xf2401000, 0x800),
                               ('I2C_NAME "1"', 0xf2401800, 0x800),
                               ('SIO_NAME "4"', 0xf2405800, 0x200),
                               ('SPI_CH_NAME(1)', 0xf2007000, 0x1000)]:
        row = windows[key]
        assert int(row['base'], 0) == address and int(row['size'], 0) == size, key
    for key,irq in [('I2C_NAME \"0\"',199),('I2C_NAME \"1\"',200),('SIO_NAME \"4\"',205),('DMA330_CH_NAME(0)',115)]:
        assert [x['gpl_irq'] for x in windows[key]['interrupts']]==[irq],key
    assert len(symbols) >= 500
    for extra_sym in ('OCTRL_OEN', 'CRG_CRCDC', 'LPCMD_REG', 'BAM_MON_CTRL', 'AIN_SEL', 'SRAMC_MODE', 'SSRAMC_MODE', 'PA2NC_DDRA'):
        assert extra_sym in symbols, extra_sym
    assert 'AUX_VAL' in {u['name'] for u in platform['unresolved_definitions']}
    assert sum(bool(x['clock']) for x in platform['udif_windows']) == 4
    i2c0_clk = windows['I2C_NAME "0"']['clock']
    assert i2c0_clk['hclk']['set'] == '0xf2a30044' and i2c0_clk['hclk']['clr'] == '0xf2a30048' and i2c0_clk['hclk']['shift'] == 1
    assert i2c0_clk['dclk']['set'] == '0xf2a30064' and i2c0_clk['dclk']['clr'] == '0xf2a30068' and i2c0_clk['dclk']['shift'] == 17
    irq_only = {x['name_expression']: x['gpl_irq'] for x in platform['udif_irq_only_channels']}
    assert irq_only == {'SIRCS_OVERRUN_NAME': 197, 'FUSB_CH0_NAME': 230, 'FUSB_CH1_NAME': 231, 'DMA330_ABT_NAME': 119}, irq_only
    crg = {x['id']: x['base'] for x in platform['crg_clock_domains']}
    assert len(crg) == 9 and crg['CRG11_00'] == '0xf2a01000' and crg['CRG11_41'] == '0xf2a32000', crg
    io_maps = platform['static_io_mappings']
    assert len(io_maps) == 8
    assert any(m['physical'] == '0xbf800000' and m['virtual'] == '0xf8800000' and not m['identity_mapped'] for m in io_maps)
    assert len({x['file_offset'] for x in native}) == len(native)
    for row in native:
        mask = ((1 << row['width_bits']) - 1) << row['lsb']
        assert int(row['mask'], 0) == mask <= 0xffffffff
        assert row['reset_value'] is None and row['required_value'] is None
        assert row['read_or_write_permission'] is False
        assert int(row['register'], 0) % 4 == 0 and row['access_width_bits'] == 32
        if int(row['register'], 0) >= 0xf5000000:
            assert row['address_space'] == 'unclassified_high_address'
        for observation in row['observations']:
            assert observation['mode'] == 'Senser' and 'not a reset' in observation['scope']
    colour = [x for x in native if int(x['register'], 0) == 0xf3445108]
    assert {(x['lsb'], x['width_bits']) for x in colour} >= {(16, 8), (8, 8), (0, 8), (25, 1), (24, 1)}
    assert all(x['current_camera_code_page_match'] for x in colour)
    assert any(int(x['register'], 0) == 0xf344510c and x['lsb'] == 0 and x['width_bits'] == 1 for x in native)
    assert len({x['name'] for x in named}) == len(named)
    assert all(
        x['reset_value'] is None
        and x['required_runtime_value'] is None
        and x['read_or_write_permission'] is False
        and x['access_width_bits'] in {16, 32}
        for x in named
    )
    named_map = {x['name']: x for x in named}
    for req_name in ('XDMAC0_XDACS', 'XDMAC_CH5_XDTBC', 'XDMAC_CH5_XDDSD', 'DMA330_DSR', 'DMA330_DBGINST0',
                     'I2C0_REG_00', 'I2C0_REG_04', 'CLK4_IPCLKEN2_SET', 'CLK4_CLKRST11_CLR', 'CRG11_40_CRCDC', 'OCTRL0_OEN',
                     'VPH_AIF_OSD0_STARTADRS', 'VPH_OUT0_COLORBAR_CTL', 'VPH_OUT0_LAYER_EN',
                     'VPH_TOP_CTRL_0000', 'SUGILITE_IRQ_STAT', 'SUGILITE_CONTROL_0084_CLR'):
        assert req_name in named_map, req_name

    dma = json.loads((data / 'dma-contracts.json').read_text())
    assert dma['schema_version'] == 1 and dma['camera_access_performed'] is False and dma['read_or_write_permission'] is False
    assert dma['xdmac']['sha256'] == '718284caacf31654151fac234db7293d8338e348687c37b6e3f65dbf24de1522'
    assert len(dma['xdmac']['channel_bases']) == 8 and len(dma['xdmac']['channel_registers']) == 9
    assert dma['dma330']['sha256'] == 'a86794fb8ab97fb27adac21bbcb067d424b787f3815d97bf91942b460dffd86d'
    assert len(dma['dma330']['register_offsets']) == 60 and len(dma['dma330']['microcode_template_arrays']) == 4

    i2c = json.loads((data / 'i2c-contract.json').read_text())
    assert i2c['schema_version'] == 1 and i2c['camera_access_performed'] is False and i2c['read_or_write_permission'] is False
    assert i2c['sha256'] == '37b37633a8cdfd6ce60258d646afc2cf11dc50de67cd71a0b53631584412321e'
    assert len(i2c['register_offsets_16bit']) == 13
    assert [s['address'] for s in i2c['clk4_reset_sequence']] == ['0xf2a30048', '0xf2a300b8', '0xf2a30044', '0xf2a300b4']
    assert i2c['clk4_reset_gate']['executes_clk4_when_zero'] is True and i2c['clk4_reset_gate']['checks_channel_index'] is False
    assert i2c['channels']['0']['uipc_endpoint'] == '0x00520250' and i2c['channels']['1']['uipc_endpoint'] == '0x00520607'

    vph = json.loads((data / 'vph-aif-contracts.json').read_text())
    assert vph['schema_version'] == 1 and vph['camera_access_performed'] is False and vph['read_or_write_permission'] is False
    assert vph['source_firmware']['sha256'] == 'bc6cba98c1ce5ef9c7692b9701ed855c25958d285a646ef90dc3fdf398f5c4fa'
    assert len(vph['aif_table']['vph_channels']) == 8
    cb0_map = vph['vph_output_runs']['colorbar_output0_0x4b3f8c']['mode_map']
    assert cb0_map['3'] == '0x00000014' and cb0_map['4'] == '0x00000013'
    osd0 = vph['vph_output_runs']['osd0_repeat_setup_0x4b5818']
    assert osd0['ddr1_0xa8200000']['0xf3441320_startadrs'] == '0xa8200000'
    assert osd0['ddr1_0xa8200000']['0xf344134c_rptadrs'] == '0x28200000'
    assert osd0['ddr0_0x22000000']['0xf3441320_startadrs'] == '0x22000000'
    assert osd0['ddr0_0x22000000']['0xf344134c_rptadrs'] == '0x22000000'
    osd_pipe = vph['osd_pipeline_and_irqs']
    vdf_proc = osd_pipe['vdf_osd_image_size_processor_0x15bfb0']
    assert vdf_proc['trans_type_0']['logged_format_tag_r1'] == '0x00004444'
    assert vdf_proc['trans_type_1']['logged_format_tag_r1'] == '0x00008888'
    assert set(osd_pipe['vph_osd_queue_and_routes']['route_fanout_0x498aa4']) == {'0', '1', '2'}
    irqs = osd_pipe['vph_vsync_irqs_and_callbacks']
    assert irqs['irq_102_handler'] == '0x00806294' and irqs['irq_110_handler'] == '0x00806352'
    assert irqs['osd0_route1_completion_0x4b59ec']['callback_token_r1'] == '0x1234'
    assert irqs['osd0_route1_completion_0x4b59ec']['flag_after'] == 0
    assert irqs['osd1_route0_completion_0x4b5a84']['callback_token_r1'] == '0x5678'
    assert irqs['osd1_route0_completion_0x4b5a84']['flag_after'] == 0

    grm = json.loads((data / 'grm-contracts.json').read_text())
    assert grm['schema_version'] == 1 and grm['camera_access_performed'] is False and grm['read_or_write_permission'] is False
    assert grm['grm_gles']['sha256'] == '4e4b99e5e17e170ddc13dc432178299512525debd6fb19512521b38867da7a65'
    assert grm['grm_ma']['sha256'] == 'c21479fea7b0bc081f72315c0b0b514b383a58b5a3bb5f2fefbfd26e20711879'
    assert grm['dataflowInfraFramework']['sha256'] == '3a7235ab96ed87606fc598f45db8e318afacc1e58a07e51b541923a43de76941'
    assert grm['libObj']['sha256'] == 'bc0deb2f0e94218752e42ce6f5a3576d7456971eb63fbde705ffbd9b3a7fdeea'
    assert len(grm['grm_gles']['register_init_writes']) == 21
    assert [(w['address'], w['value']) for w in grm['grm_gles']['clock_down_writes'][:2]] == [
        ('0xf3400084', '0x00000015'),
        ('0xf3400284', '0x00000010'),
    ]
    assert len(grm['grm_ma']['cache_ops']) == 2
    assert len(grm['dataflowInfraFramework']['osd_entry_field_layout_runs']) == 14
    container = grm['dataflowInfraFramework']['serialized_container']
    assert container['header_magic'] == 'SSOS' and container['entry_magic'] == 'ETRY'
    assert grm['libObj']['type5_osd_builder'] == '0x006fe064' and grm['libObj']['type5_pin_sender'] == '0x006fe3b0'
    # Ensure ambiguous branches and unsupported C syntax cannot silently become numeric facts.
    spec = importlib.util.spec_from_file_location('atlas_builder', builder)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    definitions = module.Definitions()
    definitions.add('#define BASE 0xf2401000U\n#define STRIDE 0x800\n#define PORT(x) (BASE + STRIDE*(x))\n#define AMBIG 1\n#define AMBIG 2\n#define UNSUPPORTED ((int*) BASE)\n', 'fixture')
    assert definitions.expression('PORT(1)') == 0xf2401800
    for name in ['AMBIG', 'UNSUPPORTED', '__import__("os")']:
        try: definitions.expression(name)
        except (ValueError, SyntaxError, KeyError, TypeError): pass
        else: raise AssertionError('Accepted unsupported/ambiguous macro: ' + name)
    return {'status': 'atlas-structure-and-source-arithmetic-verified', 'native_candidates': len(native),
            'device_semantics_verified': False, 'camera_access_performed': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--builder', type=Path, required=True)
    a = p.parse_args(); print(json.dumps(verify(a.data, a.builder)))
