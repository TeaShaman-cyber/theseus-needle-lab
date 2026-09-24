import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READBACK = ROOT / 'receipts' / 'typed-decision-benchmark-v1-readback.json'
TERMINAL = ROOT / 'receipts' / 'typed-decision-benchmark-v1-terminal.json'
SUM = ROOT / 'receipts' / 'typed-decision-benchmark-v1-readback.sha256'

class TypedDecisionTerminalReceiptTests(unittest.TestCase):
    def test_readback_bytes_match_recorded_sha(self):
        observed = hashlib.sha256(READBACK.read_bytes()).hexdigest()
        declared = SUM.read_text(encoding='utf-8').strip().split()[0]
        self.assertEqual(observed, declared)
        self.assertEqual(observed, 'c802430e5a8d18e015cbfdd62fe981a5b3768ae58d600be443b1407d3f6ca550')

    def test_terminal_receipt_binds_rejected_bounded_outcome(self):
        terminal = json.loads(TERMINAL.read_text(encoding='utf-8'))
        readback = json.loads(READBACK.read_text(encoding='utf-8'))
        self.assertEqual(terminal['schema'], 'theseus.typed-decision-benchmark-terminal-receipt.v1')
        self.assertEqual(terminal['parent_issue'], 56)
        self.assertEqual(terminal['research_outcome'], 'REJECTED')
        self.assertEqual(terminal['delivery_disposition'], 'PROMOTED')
        self.assertTrue(terminal['scientific_acceptance_performed'])
        self.assertTrue(terminal['falsifier']['triggered'])
        self.assertTrue(readback['complete_local_matrix'])
        self.assertFalse(readback['scientific_acceptance_performed'])
        self.assertFalse(readback['acceptance_authority'])
        self.assertEqual(readback['experiment_sha'], terminal['execution']['experiment_sha'])
        self.assertEqual(readback['run_id'], str(terminal['execution']['recovery_run_id']))
        self.assertEqual(readback['run_attempt'], str(terminal['execution']['recovery_run_attempt']))

    def test_scope_guards_prevent_overgeneralization(self):
        terminal = json.loads(TERMINAL.read_text(encoding='utf-8'))
        guards = set(terminal['scope_guards'])
        for required in {
            'bounded_v1_fixture_only',
            'needle_3_0_4_base_reference_only',
            'not_current_upstream_3_0_5',
            'not_w4_cact_deployment_equivalence',
            'not_hidden_label_generalization',
            'nimble_unmeasured_unknown',
            'jev_unmeasured_unknown',
        }:
            self.assertIn(required, guards)

if __name__ == '__main__':
    unittest.main()
