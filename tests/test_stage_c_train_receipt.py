import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]


class StageCTrainReceiptCliTest(unittest.TestCase):
    def test_receipt_binds_early_final_artifacts_manifest_and_source_identity(self):
        td=pathlib.Path(tempfile.mkdtemp(prefix='stage-c-train-receipt-'))
        files={}
        for name,payload in [('early.pkl',b'early-adapter'),('early.cact',b'early-cact'),('final.pkl',b'final-adapter'),('final.cact',b'final-cact'),('manifest.json',b'{"x":1}\n')]:
            p=td/name; p.write_bytes(payload); files[name]=p
        out=td/'receipt.json'
        cmd=['python3',str(ROOT/'scripts/stage_c_train_receipt.py'),
             '--arm-id','B','--replica-id','R1','--experiment-commit','a'*40,'--launcher-commit','b'*40,'--run-id','123',
             '--early-adapter',str(files['early.pkl']),'--early-cact',str(files['early.cact']),
             '--final-adapter',str(files['final.pkl']),'--final-cact',str(files['final.cact']),
             '--curriculum-manifest',str(files['manifest.json']),'--output',str(out)]
        r=subprocess.run(cmd,text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr)
        receipt=json.loads(out.read_text())
        self.assertEqual(receipt['schema'],'theseus.needle.stage_c_train.v1')
        self.assertEqual(receipt['arm_id'],'B')
        self.assertEqual(receipt['replica_id'],'R1')
        self.assertEqual(receipt['source']['experiment_commit'],'a'*40)
        self.assertEqual(receipt['artifacts']['early_cact_sha256'],hashlib.sha256(b'early-cact').hexdigest())
        self.assertEqual(receipt['artifacts']['final_cact_sha256'],hashlib.sha256(b'final-cact').hexdigest())
        self.assertEqual(receipt['inputs']['curriculum_manifest_sha256'],hashlib.sha256(b'{"x":1}\n').hexdigest())


if __name__=='__main__':
    unittest.main()
