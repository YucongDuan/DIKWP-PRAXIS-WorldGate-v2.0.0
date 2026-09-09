import argparse,shutil,tempfile,zipapp
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--out',default='dist/praxis.pyz');a=p.parse_args()
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as t:
    shutil.copytree(root/'src/praxis_os',Path(t)/'praxis_os',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    zipapp.create_archive(t,str(dest),main='praxis_os.cli:main',interpreter='/usr/bin/env python3',compressed=True)
print(dest)
