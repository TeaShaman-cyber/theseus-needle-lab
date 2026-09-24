import unittest
from pathlib import Path

from scripts import typed_decision_benchmark as bench

ROOT=Path(__file__).resolve().parents[1]

class TypedDecisionRunnerContractTests(unittest.TestCase):
    def test_arm_runner_contains_all_planned_candidates(self):
        text=(ROOT/'scripts'/'run_typed_decision_arm.sh').read_text(encoding='utf-8')
        for candidate in ('baseline_constant_unknown','needle3_base','semif_qwen3_0_6b_q8','kev_0_8b'): self.assertIn(candidate,text)

    def test_semif_route_is_exact_package_and_gguf_bound(self):
        text=(ROOT/'scripts'/'run_typed_decision_arm.sh').read_text(encoding='utf-8')
        registry=(ROOT/'experiments'/'typed-decision-benchmark'/'v1'/'candidates.json').read_text(encoding='utf-8')
        self.assertIn('PUBLIC_GITHUB_RELEASE',registry)
        self.assertIn('586562898',registry)
        self.assertIn('prepare_semif_release_runtime.py',text)
        self.assertIn('9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031',text)

    def test_kev_runner_removes_dummy_label_before_probs(self):
        text=(ROOT/'scripts'/'run_typed_decision_candidate.py').read_text(encoding='utf-8')
        self.assertIn("enc.pop('labels',None)",text)
        self.assertIn("enc.get('labels') != [0]",text)

    def test_runners_do_not_reference_fixture_expected_for_requests(self):
        text=(ROOT/'scripts'/'run_typed_decision_candidate.py').read_text(encoding='utf-8')
        self.assertNotIn("case['expected']",text)


class SemIfReleaseConsumerContractTests(unittest.TestCase):
    def test_registry_binds_public_release_and_original_producer(self):
        registry=bench.load_registry(ROOT/'experiments'/'typed-decision-benchmark'/'v1'/'candidates.json')
        ident=registry['candidates']['semif_qwen3_0_6b_q8']['runtime_identity']
        self.assertEqual(ident['distribution'],'PUBLIC_GITHUB_RELEASE')
        self.assertEqual(ident['release_id'],395961859)
        self.assertEqual(ident['release_asset_id'],586562898)
        self.assertEqual(ident['release_asset_digest'],'sha256:f985f2be09ad5301dc809f4f9e6a9b72c60bca9a61e7b8128a245e88de54501d')
        self.assertEqual(ident['producer_actions_artifact_id'],10772811868)

    def test_semif_arm_uses_public_release_not_cross_repo_actions_artifact(self):
        text=(ROOT/'scripts'/'run_typed_decision_arm.sh').read_text(encoding='utf-8')
        self.assertIn('prepare_semif_release_runtime.py',text)
        self.assertNotIn('prepare_runtime_package.py',text)
        self.assertNotIn('GH_TOKEN',text)

    def test_release_consumer_uses_cookbook_safe_tar_extraction(self):
        text=(ROOT/'scripts'/'prepare_semif_release_runtime.py').read_text(encoding='utf-8')
        self.assertIn('helper.safe_extract_tar',text)
        self.assertIn('release_asset_digest',text)
        self.assertIn('tree_sha256',text)

if __name__=='__main__': unittest.main()
