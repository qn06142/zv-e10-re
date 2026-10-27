"""Production builds must reject the withdrawn simulated acquisition model."""
from pathlib import Path
import subprocess,tempfile,pytest

@pytest.mark.parametrize('target',[False,True])
def test_default_and_target_never_use_legacy_protocol(target):
    src=Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='sony-guard-') as d:
        exe=Path(d)/'guard.exe'
        flags=['-DRAW_LIVE_TARGET_ARM','-DSONY_ENABLE_LEGACY_TEST_FIXTURES'] if target else []
        subprocess.run(['gcc','-O2','-Wall','-Wextra','-Werror',*flags,'-I',str(src),
            str(src/'raw_live_sony.c'),str(src/'test_backend_guard.c'),'-o',str(exe)],check=True,capture_output=True)
        result=subprocess.run([str(exe)],check=True,capture_output=True,text=True)
        assert '7 checks passed' in result.stdout
