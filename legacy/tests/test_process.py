import sys
import unittest
from praxis_os.adapters import trusted_process
from praxis_os.common import ValidationError

class ProcessTests(unittest.TestCase):
    def cfg(self,script,**kw):return dict(argv=[sys.executable,'-c',script],**kw)
    def test_default_denies(self):
        with self.assertRaises(ValidationError):trusted_process(self.cfg('print(1)'),{})
    def test_valid_json(self):
        a=trusted_process(self.cfg('print(\'{"execution_status":"COMPLETED","output":{"a":1},"spans":[]}\')'),{},True)
        self.assertEqual(a['output'],{'a':1})
    def test_timeout(self):
        a=trusted_process(self.cfg('import time;time.sleep(2)',timeout_seconds=.05),{},True)
        self.assertEqual(a['execution_status'],'TIMEOUT')
    def test_output_cap(self):
        a=trusted_process(self.cfg('print("x"*10000)',max_output_bytes=64),{},True)
        self.assertEqual(a['execution_status'],'OUTPUT_LIMIT')
    def test_invalid_json(self):
        a=trusted_process(self.cfg('print("bad")'),{},True)
        self.assertEqual(a['execution_status'],'INVALID_WORKER_JSON')
    def test_nonzero_worker(self):
        a=trusted_process(self.cfg('raise SystemExit(2)'),{},True)
        self.assertEqual(a['execution_status'],'WORKER_ERROR')
    def test_env_secret_not_inherited(self):
        import os
        os.environ['PRAXIS_TEST_SECRET']='never-copy'
        try:
            a=trusted_process(self.cfg('import os,json;print(json.dumps({"output":os.environ.get("PRAXIS_TEST_SECRET")}))'),{},True)
            self.assertIsNone(a['output'])
        finally:del os.environ['PRAXIS_TEST_SECRET']
    def test_argv_not_shell(self):
        with self.assertRaises(ValidationError):trusted_process({'argv':'echo exploit'}, {},True)
    def test_absolute_exec_required(self):
        with self.assertRaises(ValidationError):trusted_process({'argv':['python','x.py']},{},True)
