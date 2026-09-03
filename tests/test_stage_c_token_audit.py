import unittest

from scripts.audit_stage_c_token_lengths import bind_stage_c_rows

PREFIX="Use route to classify the following evidence:\n\n"


class StageCTokenAuditBindingTest(unittest.TestCase):
    def test_binding_preserves_duplicate_case_ids_and_validates_behavioral_query(self):
        canonical=[
            {"case_id":"p","query":"positive","canonical_state":{"applicability":"ROUTE","decision":"PROBE"}},
            {"case_id":"n","query":"negative","canonical_state":{"applicability":"NONE","decision":"NO_CALL"},"sample_ordinal":0},
            {"case_id":"n","query":"negative","canonical_state":{"applicability":"NONE","decision":"NO_CALL"},"sample_ordinal":1},
        ]
        projection=[
            {"query":PREFIX+"positive","tools":[],"answers":[]},
            {"query":"negative","tools":[],"answers":[]},
            {"query":"negative","tools":[],"answers":[]},
        ]
        rows=bind_stage_c_rows(projection,canonical,PREFIX)
        self.assertEqual([r['case_id'] for r in rows],["p","n","n"])
        self.assertEqual(len(rows),3)

    def test_binding_rejects_count_or_query_mismatch(self):
        with self.assertRaisesRegex(RuntimeError,"row count"):
            bind_stage_c_rows([{"query":"x"}],[],PREFIX)
        with self.assertRaisesRegex(RuntimeError,"query mismatch"):
            bind_stage_c_rows(
                [{"query":"WRONG"}],
                [{"case_id":"n","query":"negative","canonical_state":{"applicability":"NONE","decision":"NO_CALL"}}],
                PREFIX,
            )


if __name__=='__main__':
    unittest.main()
