#!/usr/bin/env python3
"""Trusted toy adapter example. No model API and no access to expected answers."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from praxis_os.adapters import builtin_execute
request=json.loads(sys.stdin.readline())
result=builtin_execute('direct',request['case'],request['arm'],request['trial'],request['seed'],request['task'])
print(json.dumps(result))
