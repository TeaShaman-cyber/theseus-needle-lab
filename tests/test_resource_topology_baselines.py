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
        fast_budget = receipt["hard_resource_budget"]["fast_tier_budget_bytes"]
        slow_budget = receipt["hard_resource_budget"]["slow_tier_budget_bytes"]
        self.assertEqual(receipt["disposition"], "BASELINE_RECEIPT_VALID")
        self.assertEqual(receipt["native_policy_status"], "NOT_EXPOSED_IN_SYNTHETIC_FIXTURE")
        self.assertEqual(receipt["deterministic_fallback_policy"], "lru")
        for metrics in receipt["policies"].values():
            self.assertTrue(metrics["hard_budget_respected"])
            self.assertTrue(metrics["fast_tier_budget_respected"])
            self.assertTrue(metrics["slow_tier_budget_respected"])
            self.assertEqual(metrics["fast_tier_budget_bytes"], fast_budget)
            self.assertLessEqual(metrics["peak_occupancy_bytes"], fast_budget)
            self.assertEqual(metrics["slow_tier_budget_bytes"], slow_budget)
            self.assertLessEqual(metrics["slow_tier_occupancy_bytes"], slow_budget)
            self.assertEqual(
                metrics["slow_tier_headroom_bytes"],
                slow_budget - metrics["slow_tier_occupancy_bytes"],
            )
            self.assertEqual(
                metrics["slow_tier_semantics"],
                "backing_store_retains_all_working_sets",
            )
            self.assertIsNone(metrics["quality_deviation"])
            self.assertEqual(metrics["quality_measurement_status"], "NOT_MEASURED")

    def test_cold_warm_state_is_derived_from_trace(self):
        receipt = module.build_receipt(MANIFEST, TRACE)
        for metrics in receipt["policies"].values():
            self.assertEqual(metrics["cold_accesses"], 3)
            self.assertEqual(metrics["warm_accesses"], 9)
            self.assertEqual(metrics["cold_warm_state"], "MIXED")

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cold_only_trace = {
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
        module.validate_fixture(manifest, cold_only_trace)
        metrics = module.Simulator(manifest, cold_only_trace, "lru").run()
        self.assertEqual(metrics["cold_accesses"], 1)
        self.assertEqual(metrics["warm_accesses"], 0)
        self.assertEqual(metrics["cold_warm_state"], "COLD_ONLY")

    def test_slow_tier_backing_store_budget_fails_closed(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        trace = json.loads(TRACE.read_text(encoding="utf-8"))
        manifest["topology"]["slow_tier_budget_bytes"] = 12582912
        with self.assertRaisesRegex(ValueError, "slow-tier backing-store budget"):
            module.validate_fixture(manifest, trace)

    def test_negative_control_proves_hit_rate_is_not_system_objective(self):
        receipt = module.build_receipt(MANIFEST, TRACE)
        control = receipt["negative_control"]
        self.assertTrue(control["pass"])
        self.assertTrue(control["prefetch_hit_rate_gt_lru"])
        self.assertTrue(control["prefetch_latency_gt_lru"])
        self.assertTrue(control["prefetch_bytes_moved_ge_lru"])

    def test_overflowed_aggregate_metrics_fail_closed(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        manifest["policies"]["aggressive_prefetch"][
            "controller_overhead_seconds_per_event"
        ] = 1e308

        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            manifest_path = pathlib.Path(tmp) / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "derived metric must be finite"):
                module.build_receipt(manifest_path, TRACE)

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
            "slow_tier_occupancy_bytes",
            "slow_tier_headroom_bytes",
            "cold_accesses",
            "warm_accesses",
            "cold_warm_state",
            "quality_deviation",
            "cache_or_state_churn_bytes",
            "controller_overhead_seconds",
        }
        for policy, metrics in receipt["policies"].items():
            self.assertTrue(required.issubset(metrics), policy)

    def test_fractional_or_boolean_discrete_fields_fail_closed(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        trace = json.loads(TRACE.read_text(encoding="utf-8"))

        cases = [
            ("fast_tier_budget_bytes", 12582912.9),
            ("slow_tier_budget_bytes", 134217728.5),
            ("fast_tier_budget_bytes", True),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                candidate = copy.deepcopy(manifest)
                candidate["topology"][field] = value
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    module.validate_fixture(candidate, trace)

        candidate = copy.deepcopy(manifest)
        candidate["working_sets"]["A"] = 6291456.5
        with self.assertRaisesRegex(ValueError, "positive integer"):
            module.validate_fixture(candidate, trace)

        candidate_trace = copy.deepcopy(trace)
        candidate_trace["events"][0]["tokens"] = 0.5
        with self.assertRaisesRegex(ValueError, "nonnegative integer"):
            module.validate_fixture(manifest, candidate_trace)

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

    def test_static_fixed_set_must_fit_hard_budget(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        trace = json.loads(TRACE.read_text(encoding="utf-8"))
        manifest["policies"]["static_fixed"]["fixed_sets"] = ["A", "B", "C"]
        with self.assertRaisesRegex(ValueError, "exceed fast-tier budget"):
            module.validate_fixture(manifest, trace)

    def test_static_fixed_set_must_use_known_unique_working_sets(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        trace = json.loads(TRACE.read_text(encoding="utf-8"))

        duplicate = copy.deepcopy(manifest)
        duplicate["policies"]["static_fixed"]["fixed_sets"] = ["A", "A"]
        with self.assertRaisesRegex(ValueError, "must be unique"):
            module.validate_fixture(duplicate, trace)

        unknown = copy.deepcopy(manifest)
        unknown["policies"]["static_fixed"]["fixed_sets"] = ["A", "UNKNOWN"]
        with self.assertRaisesRegex(ValueError, "unknown working set"):
            module.validate_fixture(unknown, trace)

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

    def test_zero_duration_decode_is_observed_not_absent(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for field in ("transfer_seconds_per_byte", "miss_penalty_seconds"):
            manifest["topology"][field] = 0.0
        for policy in manifest["policies"].values():
            policy["controller_overhead_seconds_per_event"] = 0.0

        trace = {
            "schema_version": "theseus.needle.resource_topology_trace.v1",
            "topology_id": manifest["topology"]["topology_id"],
            "events": [
                {
                    "request_id": "R1",
                    "phase": "decode",
                    "working_set_id": "A",
                    "base_latency_seconds": 0.0,
                    "tokens": 1,
                }
            ],
        }
        module.validate_fixture(manifest, trace)
        metrics = module.Simulator(manifest, trace, "lru").run()
        self.assertIsNone(metrics["decode_tokens_per_second"])
        self.assertEqual(
            metrics["decode_throughput_measurement_status"],
            "OBSERVED_ZERO_DURATION",
        )

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
