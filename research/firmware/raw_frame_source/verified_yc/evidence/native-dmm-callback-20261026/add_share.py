from pathlib import Path
p=Path('work/native-dmm-callback/inspect_kernel.py');s=p.read_text().replace("'dmm_ctrl_CloseUnitHdlr']", "'dmm_ctrl_CloseUnitHdlr','dmm_unit_ctrl_Share','dmm_ctrl_AllocUnitShareHdlr']");p.write_text(s)
