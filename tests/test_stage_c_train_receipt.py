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
        for name,payload in [('early.pkl',b'early-adapter'),('early.cact',b'early-cact'),('final.pkl',b'final-adapter'),('final.cact',b'final-cact'),('manifest.json',b'{"x":1}\n'),('checkpoint.pkl',b'base-checkpoint')]:
            p=td/name; p.write_bytes(payload); files[name]=p
        out=td/'receipt.json'
        cmd=['python3',str(ROOT/'scripts/stage_c_train_receipt.py'),
             '--arm-id','B','--replica-id','R1','--experiment-commit','a'*40,'--launcher-commit','b'*40,'--run-id','123',
             '--early-adapter',str(files['early.pkl']),'--early-cact',str(files['early.cact']),
             '--final-adapter',str(files['final.pkl']),'--final-cact',str(files['final.cact']),
             '--curriculum-manifest',str(files['manifest.json']),'--checkpoint',str(files['checkpoint.pkl']),
             '--seed','101','--epochs','15','--batch-size','16','--lr','1e-4','--lora-rank','16','--lora-alpha','32','--max-len','512','--val-split','0.0',
             '--output',str(out)]
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

class StageCRealizedTrainingProvenanceRegressionTest(unittest.TestCase):
    def _files(self, td):
        files={}
        for name,payload in [('early.pkl',b'early-adapter'),('early.cact',b'early-cact'),('final.pkl',b'final-adapter'),('final.cact',b'final-cact'),('manifest.json',b'{"x":1}\n'),('checkpoint.pkl',b'base-checkpoint')]:
            p=td/name; p.write_bytes(payload); files[name]=p
        return files

    def test_receipt_binds_realized_seed_checkpoint_and_training_config(self):
        td=pathlib.Path(tempfile.mkdtemp(prefix='stage-c-realized-config-'))
        f=self._files(td); out=td/'receipt.json'
        cmd=['python3',str(ROOT/'scripts/stage_c_train_receipt.py'),
             '--arm-id','B','--replica-id','R1','--experiment-commit','a'*40,'--launcher-commit','b'*40,'--run-id','123',
             '--early-adapter',str(f['early.pkl']),'--early-cact',str(f['early.cact']),'--final-adapter',str(f['final.pkl']),'--final-cact',str(f['final.cact']),
             '--curriculum-manifest',str(f['manifest.json']),'--checkpoint',str(f['checkpoint.pkl']),
             '--seed','101','--epochs','15','--batch-size','16','--lr','1e-4','--lora-rank','16','--lora-alpha','32','--max-len','512','--val-split','0.0',
             '--output',str(out)]
        r=subprocess.run(cmd,text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr)
        receipt=json.loads(out.read_text())
        self.assertEqual(receipt['inputs']['base_checkpoint_sha256'],hashlib.sha256(b'base-checkpoint').hexdigest())
        self.assertEqual(receipt['training_config'],{'seed':101,'epochs':15,'batch_size':16,'lr':1e-4,'lora_rank':16,'lora_alpha':32.0,'max_len':512,'val_split':0.0})

    def test_receipt_rejects_seed_that_disagrees_with_replica_id(self):
        td=pathlib.Path(tempfile.mkdtemp(prefix='stage-c-wrong-seed-'))
        f=self._files(td); out=td/'receipt.json'
        cmd=['python3',str(ROOT/'scripts/stage_c_train_receipt.py'),
             '--arm-id','A','--replica-id','R1','--experiment-commit','a'*40,'--launcher-commit','b'*40,'--run-id','123',
             '--early-adapter',str(f['early.pkl']),'--early-cact',str(f['early.cact']),'--final-adapter',str(f['final.pkl']),'--final-cact',str(f['final.cact']),
             '--curriculum-manifest',str(f['manifest.json']),'--checkpoint',str(f['checkpoint.pkl']),
             '--seed','202','--epochs','15','--batch-size','16','--lr','1e-4','--lora-rank','16','--lora-alpha','32','--max-len','512','--val-split','0.0',
             '--output',str(out)]
        r=subprocess.run(cmd,text=True,capture_output=True)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('seed',r.stderr.lower())

    def test_receipt_rejects_non_preregistered_training_config(self):
        td=pathlib.Path(tempfile.mkdtemp(prefix='stage-c-wrong-config-'))
        f=self._files(td); out=td/'receipt.json'
        cmd=['python3',str(ROOT/'scripts/stage_c_train_receipt.py'),
             '--arm-id','A','--replica-id','R1','--experiment-commit','a'*40,'--launcher-commit','b'*40,'--run-id','123',
             '--early-adapter',str(f['early.pkl']),'--early-cact',str(f['early.cact']),'--final-adapter',str(f['final.pkl']),'--final-cact',str(f['final.cact']),
             '--curriculum-manifest',str(f['manifest.json']),'--checkpoint',str(f['checkpoint.pkl']),
             '--seed','101','--epochs','15','--batch-size','16','--lr','1e-4','--lora-rank','16','--lora-alpha','32','--max-len','256','--val-split','0.0',
             '--output',str(out)]
        r=subprocess.run(cmd,text=True,capture_output=True)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('training config mismatch',r.stderr.lower())
