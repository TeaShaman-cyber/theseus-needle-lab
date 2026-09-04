import unittest

from scripts.stage_c_recovery_state import build_recovery_state, update_recovery_entry


POLICY = {
    "false_call_increment": 1.0,
    "max_priority": 4.0,
    "successes_before_decay": 2,
    "success_decay_factor": 0.5,
    "min_active_priority": 0.25,
}


class StageCRecoveryStateTest(unittest.TestCase):
    def test_rejects_heldout_rows(self):
        semantic = [{"case_id": "heldout-negative-x", "split": "heldout", "applicability": "none", "expected_decision": None}]
        outcomes = [{"id": "heldout-negative-x", "predicted": "READY"}]
        with self.assertRaisesRegex(ValueError, "heldout"):
            build_recovery_state(semantic, outcomes, POLICY)

    def test_false_call_creates_high_priority_negative_boundary(self):
        semantic = [{"case_id": "train-negative-x", "split": "train", "applicability": "none", "expected_decision": None}]
        outcomes = [{"id": "train-negative-x", "predicted": "READY"}]
        state = build_recovery_state(semantic, outcomes, POLICY)
        self.assertEqual(state, [{
            "case_id": "train-negative-x",
            "class": "negative_boundary",
            "failure_count": 1,
            "success_streak": 0,
            "recovery_priority": 1.0,
            "last_outcome": "FALSE_CALL",
            "retention_zone": "recent",
            "evictable": False,
        }])

    def test_priority_caps_after_repeated_false_calls(self):
        entry = {
            "case_id": "train-negative-x", "class": "negative_boundary",
            "failure_count": 3, "success_streak": 0, "recovery_priority": 3.5,
            "last_outcome": "FALSE_CALL", "retention_zone": "recent", "evictable": False,
        }
        updated = update_recovery_entry(entry, "FALSE_CALL", POLICY)
        self.assertEqual(updated["failure_count"], 4)
        self.assertEqual(updated["recovery_priority"], 4.0)
        self.assertEqual(updated["success_streak"], 0)

    def test_two_stable_no_calls_decay_priority_without_erasing_state(self):
        entry = {
            "case_id": "train-negative-x", "class": "negative_boundary",
            "failure_count": 2, "success_streak": 0, "recovery_priority": 2.0,
            "last_outcome": "FALSE_CALL", "retention_zone": "recent", "evictable": False,
        }
        first = update_recovery_entry(entry, "CORRECT_NO_CALL", POLICY)
        self.assertEqual(first["success_streak"], 1)
        self.assertEqual(first["recovery_priority"], 2.0)
        second = update_recovery_entry(first, "CORRECT_NO_CALL", POLICY)
        self.assertEqual(second["success_streak"], 2)
        self.assertEqual(second["recovery_priority"], 1.0)
        self.assertEqual(second["retention_zone"], "active")
        self.assertFalse(second["evictable"])

    def test_other_outcome_does_not_mutate_priority(self):
        entry = {
            "case_id": "train-negative-x", "class": "negative_boundary",
            "failure_count": 1, "success_streak": 0, "recovery_priority": 1.0,
            "last_outcome": "FALSE_CALL", "retention_zone": "recent", "evictable": False,
        }
        updated = update_recovery_entry(entry, "OTHER", POLICY)
        self.assertEqual(updated["recovery_priority"], 1.0)
        self.assertEqual(updated["failure_count"], 1)
        self.assertEqual(updated["success_streak"], 0)
        self.assertEqual(updated["last_outcome"], "OTHER")

    def test_other_resets_success_streak_without_changing_priority(self):
        entry = {
            "case_id": "train-negative-x", "class": "negative_boundary",
            "failure_count": 2, "success_streak": 1, "recovery_priority": 2.0,
            "last_outcome": "CORRECT_NO_CALL", "retention_zone": "active", "evictable": False,
        }
        other = update_recovery_entry(entry, "OTHER", POLICY)
        self.assertEqual(other["success_streak"], 0)
        self.assertEqual(other["recovery_priority"], 2.0)
        again = update_recovery_entry(other, "CORRECT_NO_CALL", POLICY)
        self.assertEqual(again["success_streak"], 1)
        self.assertEqual(again["recovery_priority"], 2.0)


if __name__ == "__main__":
    unittest.main()

class StageCRepeatedOutcomeRegressionTest(unittest.TestCase):
    def test_repeated_outcomes_aggregate_into_single_entry(self):
        semantic=[{'case_id':'train-negative-x','split':'train','applicability':'none','expected_decision':None}]
        outcomes=[
            {'id':'train-negative-x','predicted':'READY'},
            {'id':'train-negative-x','predicted':'PROBE'},
            {'id':'train-negative-x','predicted':'NO_CALL'},
        ]
        state=build_recovery_state(semantic,outcomes,POLICY)
        self.assertEqual(len(state),1)
        self.assertEqual(state[0]['failure_count'],2)
        self.assertEqual(state[0]['success_streak'],1)
        self.assertEqual(state[0]['recovery_priority'],2.0)
        self.assertEqual(state[0]['last_outcome'],'CORRECT_NO_CALL')
