import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TRAIN = ROOT / 'scripts' / 'run_realistic_sft_full_train.sh'


class RealisticSftFullTrainContractTest(unittest.TestCase):
    def test_full_train_entrypoint_is_exact_config_replica_scoped_and_does_not_evaluate(self):
        text = TRAIN.read_text(encoding='utf-8')
        self.assertIn(': "${EXPERIMENT_SHA:?EXPERIMENT_SHA is required}"', text)
        self.assertIn(': "${LAUNCHER_SHA:?LAUNCHER_SHA is required}"', text)
        self.assertIn(': "${REPLICA_ID:?REPLICA_ID is required}"', text)
        self.assertIn('R1|R2', text)
        for value in [
            '--seed 0', '--epochs 15', '--batch-size 16', '--lr 1e-4',
            '--lora-rank 16', '--lora-alpha 32', '--max-len 256', '--val-split 0.1',
        ]:
            self.assertIn(value, text)
        self.assertIn('cactus-needle[train]==2.0.8', text)
        self.assertIn('validate_realistic_sft_dataset.py', text)
        self.assertIn('audit_realistic_sft_token_lengths.py --max-len 256', text)
        self.assertIn('needle build checkpoints/needle2.pkl --lora "$adapter" --out "$cact"', text)
        self.assertNotIn('--bits', text)
        self.assertNotIn('run_realistic_sft_eval.py', text)
        self.assertNotIn('OPENROUTER', text.upper())
        self.assertNotIn('secrets.', text)

    def test_training_receipt_binds_replica_artifacts_and_exact_source_identities(self):
        from scripts.realistic_sft_replica_train_receipt import build_receipt
        receipt = build_receipt(
            replica_id='R1', experiment_commit='a'*40, launcher_commit='b'*40,
            workflow_run_id='123', train_sha256='c'*64, checkpoint_sha256='d'*64,
            adapter_sha256='e'*64, cact_sha256='f'*64,
            train_elapsed_seconds=100.0, train_max_rss_kb=1000, build_elapsed_seconds=5.0,
        )
        self.assertEqual(receipt['schema'], 'theseus.needle.realistic_sft_replica_train.v1')
        self.assertEqual(receipt['replica_id'], 'R1')
        self.assertEqual(receipt['source']['experiment_commit'], 'a'*40)
        self.assertEqual(receipt['source']['launcher_commit'], 'b'*40)
        self.assertEqual(receipt['config']['epochs'], 15)
        self.assertEqual(receipt['artifacts']['cact_sha256'], 'f'*64)


if __name__ == '__main__':
    unittest.main()

EVAL = ROOT / 'scripts' / 'run_realistic_sft_full_eval.sh'

class RealisticSftFullEvalContractTest(unittest.TestCase):
    def test_eval_entrypoint_is_paired_base_vs_tuned_and_never_trains(self):
        text = EVAL.read_text(encoding='utf-8')
        self.assertIn(': "${EXPERIMENT_SHA:?EXPERIMENT_SHA is required}"', text)
        self.assertIn(': "${LAUNCHER_SHA:?LAUNCHER_SHA is required}"', text)
        self.assertIn(': "${REPLICA_ID:?REPLICA_ID is required}"', text)
        self.assertEqual(text.count('run_realistic_sft_eval.py'), 4)
        self.assertIn('--split train', text)
        self.assertIn('--split heldout', text)
        self.assertIn('--weights "$cact"', text)
        self.assertIn('realistic_sft_quality_receipt.py replica', text)
        self.assertNotIn('run_seeded_finetune.py', text)
        self.assertNotIn('needle build', text)

    def test_replica_receipt_and_final_aggregate_bind_two_independent_receipts(self):
        from scripts.realistic_sft_quality_receipt import build_replica_receipt, aggregate_receipts
        good={'train_fit':True,'learned_and_generalizes':True,'applicability_regression':False}
        r1=build_replica_receipt('R1','a'*40,'b'*40,'123',good,'c'*64,'d'*64)
        r2=build_replica_receipt('R2','a'*40,'b'*40,'123',good,'e'*64,'f'*64)
        final=aggregate_receipts(r1,r2)
        self.assertEqual(r1['schema'],'theseus.needle.realistic_sft_replica_eval.v1')
        self.assertEqual(final['schema'],'theseus.needle.realistic_sft_final.v1')
        self.assertEqual(final['disposition'],'ACCEPTED_LEARNED_AND_GENERALIZES')
        self.assertEqual(set(final['replicas']),{'R1','R2'})
