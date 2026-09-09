"""Run new and preserved legacy tests and record an honest combined count."""
import sys,json,unittest,os
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'src'))
# Child CLI processes need the same source root; sys.path alone is not inherited.
os.environ['PYTHONPATH']=str(root/'src') + (os.pathsep + os.environ['PYTHONPATH'] if os.environ.get('PYTHONPATH') else '')
results={}
for name,folder in [('worldgate',root/'tests'),('legacy',root/'legacy/tests')]:
    suite=unittest.TestLoader().discover(str(folder));res=unittest.TextTestRunner(verbosity=2).run(suite)
    results[name]={'tests':res.testsRun,'failures':len(res.failures),'errors':len(res.errors),'skipped':len(res.skipped),'passed':res.wasSuccessful()}
results['total']=sum(r['tests'] for r in results.values());results['all_passed']=all(r['passed'] for r in results.values() if isinstance(r,dict))
p=root/'verification/test_summary.json';p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results));raise SystemExit(0 if results['all_passed'] else 1)
