"""Run the five new compiled ARM integration cases without replaying inherited cases."""
from pathlib import Path
import json
source=Path(__file__).with_name('verify.py').read_text()
prefix=source.split('results=[]',1)[0]
body=source.split('# Execute new live path',1)[1].split("(OUT/'verification.json').write_text",1)[0]
exec(compile(prefix,"verify.py:setup","exec"))
results=[]
exec(compile('# Execute new live path'+body,"verify.py:live","exec"))
result={'passed':len(results),'cases':results,'hardware_services_mocked':True}
(OUT/'live-integration-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
