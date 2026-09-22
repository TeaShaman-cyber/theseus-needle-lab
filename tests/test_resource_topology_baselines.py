import copy
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "resource_topology_baselines.py"
MANIFEST = ROOT / "experiments" / "resource-topology-baselines" / "v1" / "manifest.json"
TRACE = ROOT / "experiments" / "resource-topology-baselines" / "v1" / "trace.json"
RECEIPT = ROOT / "receipts" / "resource-topology-baseline-v1.json"

spec = importlib.util.spec_from_file_location("resource_topology_baselines", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ResourceTopologyBaselineTests(unittest.TestCase):
    def test_fixture_is_valid_and_all_policies_share_hard_budget(self):
        receipt = module.build_receipt(MANIFEST, TRACE)
        budget = receipt["hard_resource_budget"]["fast_tier_budget_bytes"]
        self.assertEqual(receipt["disposition"], "BASELINE_RECEIPT_VALID")
        self.assertEqual(receipt["native_policy_status"], "NOT_EXPOSED_IN_SYNTHETIC_FIXTURE")
        for metrics in receipt["policies"].values():
            self.assertTrue(metrics["hard_budget_respected"])
            self.assertEqual(metrics["fast_tier_budget_bytes"], budget)
            self.assertLessEqual(metrics["peak_occupancy_bytes"], budget)
            self.assertIsNone(metrics["quality_deviation"])
            self.assertEqual(metrics["quality_measurement_status"], "NOT_MEASURED")

    def test_negative_control_proves_hit_rate_is_not_system_objective(self):
        receipt = module.build_receipt(MANIFEST, TRACE)
        control = receipt["negative_control"]
        self.assertTrue(control["pass"])
        self.assertTrue(control["prefetch_hit_rate_gt_lru"])
        self.assertTrue(control["prefetch_latency_gt_lru"])
        self.assertTrue(control["prefetch_bytes_moved_ge_lru"])

    def test_receipt_contains_required_resource_metrics(self):
        receipt = module.build_receipt(MANIFEST, TRACE)
        required = {
            "bytes_moved",
            "demand_misses",
            "miss_penalty_seconds",
            "total_latency_seconds",
            "mean_ttft_seconds",
            "decode_tokens_per_second",
            "peak_occupancy_bytes",
            "minimum_headroom_bytes",
            "quality_deviation",
            "cache_or_state_churn_bytes",
            "controller_overhead_seconds",
        }
        for policy, metrics in receipt["policies"].items():
            self.assertTrue(required.issubset(metrics), policy)

    def test_negative_or_nonfinite_costs_fail_closed(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        trace = json.loads(TRACE.read_text(encoding="utf-8"))

        cases = [
            ("transfer_seconds_per_byte", -1e-9),
            ("miss_penalty_seconds", float("inf")),
        ]
        for field, value in cases:
            with self.subTest(field=field):
                candidate = copy.deepcopy(manifest)
                candidate["topology"][field] = value
                with self.assertRaises(ValueError):
                    module.validate_fixture(candidate, trace)

        candidate = copy.deepcopy(manifest)
        candidate["policies"]["lru"]["controller_overhead_seconds_per_event"] = -0.1
        with self.assertRaises(ValueError):
            module.validate_fixture(candidate, trace)

    def test_missing_prefill_and_decode_emit_unavailable_metrics(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        trace = {
            "schema_version": "theseus.needle.resource_topology_trace.v1",
            "topology_id": manifest["topology"]["topology_id"],
            "events": [
                {
                    "request_id": "R1",
                    "phase": "request",
                    "working_set_id": "A",
                    "base_latency_seconds": 0.01,
                    "tokens": 0,
                }
            ],
        }
        module.validate_fixture(manifest, trace)
        metrics = module.Simulator(manifest, trace, "lru").run()
        self.assertIsNone(metrics["mean_ttft_seconds"])
        self.assertEqual(metrics["ttft_measurement_status"], "NOT_OBSERVED")
        self.assertIsNone(metrics["decode_tokens_per_second"])
        self.assertEqual(
            metrics["decode_throughput_measurement_status"],
            "NOT_OBSERVED",
        )
        self.assertIsNone(metrics["quality_deviation"])
        self.assertEqual(metrics["quality_measurement_status"], "NOT_MEASURED")

    def test_committed_receipt_is_byte_stable(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--manifest",
                str(MANIFEST),
                "--trace",
                str(TRACE),
                "--output",
                str(RECEIPT),
                "--check",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RESOURCE_TOPOLOGY_BASELINE_PASS", result.stdout)

    def test_tampered_fixture_hash_changes_receipt(self):
        original = json.loads(TRACE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            altered = pathlib.Path(tmp) / "trace.json"
            original["events"][0]["base_latency_seconds"] = 0.051
            altered.write_text(json.dumps(original, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            base = module.build_receipt(MANIFEST, TRACE)
            changed = module.build_receipt(MANIFEST, altered)
            self.assertNotEqual(base["fixture"]["trace_sha256"], changed["fixture"]["trace_sha256"])


if __name__ == "__main__":
    unittest.main()
