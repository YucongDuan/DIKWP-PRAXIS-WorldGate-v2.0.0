"""Build a compact application; cryptography is a host dependency, NOT vendored."""
import sys,zipapp,tempfile,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as td:
 p=Path(td)
 for name in ('praxis_gate','praxis_os'):
  shutil.copytree(root/'src'/name,p/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 (root/'dist').mkdir(exist_ok=True)
 (p/'__main__.py').write_text('from praxis_gate.cli import main\nraise SystemExit(main())\n',encoding='utf-8')
 zipapp.create_archive(p,root/'dist/praxis_v2.pyz',interpreter='/usr/bin/env python3',compressed=True)
print(root/'dist/praxis_v2.pyz')
