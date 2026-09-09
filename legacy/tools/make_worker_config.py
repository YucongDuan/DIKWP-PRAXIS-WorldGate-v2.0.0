import argparse,json,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
dest=Path(a.out)
if dest.exists():raise SystemExit('Refusing to overwrite worker configuration')
obj={'argv':[sys.executable,str(Path(__file__).resolve().parent/'worker_example.py')],
     'timeout_seconds':5,'max_output_bytes':100000,'env':{}}
dest.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
print(dest)
