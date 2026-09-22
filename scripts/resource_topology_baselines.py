#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import pathlib
from typing import Any


RECEIPT_SCHEMA = "theseus.needle.resource_topology_baselines.v1"
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]




def repo_relative(path: pathlib.Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("fixture path is outside repository") from exc

def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def round_metric(value: float) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("derived metric must be finite")
    return round(parsed, 6)


def positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def finite_nonnegative(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return parsed


def validate_fixture(manifest: dict[str, Any], trace: dict[str, Any]) -> None:
    if manifest.get("schema_version") != "theseus.needle.resource_topology_fixture_manifest.v1":
        raise ValueError("unsupported manifest schema")
    if trace.get("schema_version") != "theseus.needle.resource_topology_trace.v1":
        raise ValueError("unsupported trace schema")
    if trace.get("topology_id") != manifest["topology"]["topology_id"]:
        raise ValueError("trace topology does not match manifest")

    budget = positive_integer(
        manifest["topology"]["fast_tier_budget_bytes"],
        "fast_tier_budget_bytes",
    )
    slow_budget = positive_integer(
        manifest["topology"]["slow_tier_budget_bytes"],
        "slow_tier_budget_bytes",
    )
    if manifest["topology"].get("slow_tier_semantics") != "backing_store_retains_all_working_sets":
        raise ValueError("unsupported slow-tier semantics")

    required_policies = {"static_fixed", "lru", "aggressive_prefetch"}
    if not required_policies.issubset(manifest.get("policies", {})):
        raise ValueError("required baseline policy missing")
    fallback_policy = manifest.get("deterministic_fallback_policy")
    if fallback_policy not in required_policies:
        raise ValueError("deterministic fallback policy must name a baseline policy")

    finite_nonnegative(
        manifest["topology"]["transfer_seconds_per_byte"],
        "transfer_seconds_per_byte",
    )
    finite_nonnegative(
        manifest["topology"]["miss_penalty_seconds"],
        "miss_penalty_seconds",
    )
    for policy_name, policy in manifest["policies"].items():
        finite_nonnegative(
            policy["controller_overhead_seconds_per_event"],
            f"{policy_name}.controller_overhead_seconds_per_event",
        )
        if "lookahead_events" in policy:
            lookahead = policy["lookahead_events"]
            if not isinstance(lookahead, int) or isinstance(lookahead, bool) or lookahead < 0:
                raise ValueError(f"{policy_name}.lookahead_events must be a nonnegative integer")

    working_sets = manifest["working_sets"]
    total_working_set_bytes = 0
    for name, size in working_sets.items():
        if not name:
            raise ValueError("invalid working-set name")
        parsed_size = positive_integer(size, f"working_sets.{name}")
        if parsed_size > budget:
            raise ValueError("working-set size exceeds fast-tier budget")
        total_working_set_bytes += parsed_size
    if total_working_set_bytes > slow_budget:
        raise ValueError("working sets exceed slow-tier backing-store budget")

    fixed_sets = manifest["policies"]["static_fixed"].get("fixed_sets", [])
    if not isinstance(fixed_sets, list) or not fixed_sets:
        raise ValueError("static_fixed.fixed_sets must be a nonempty list")
    if len(fixed_sets) != len(set(fixed_sets)):
        raise ValueError("static_fixed.fixed_sets must be unique")
    if any(name not in working_sets for name in fixed_sets):
        raise ValueError("static_fixed.fixed_sets contains unknown working set")
    fixed_bytes = sum(int(working_sets[name]) for name in fixed_sets)
    if fixed_bytes > budget:
        raise ValueError("static_fixed.fixed_sets exceed fast-tier budget")

    if not trace.get("events"):
        raise ValueError("empty trace")

    for event in trace["events"]:
        if event["working_set_id"] not in working_sets:
            raise ValueError("unknown working set")
        if event["phase"] not in {"prefill", "decode", "request", "synthetic"}:
            raise ValueError("unsupported phase")
        finite_nonnegative(event["base_latency_seconds"], "base_latency_seconds")
        nonnegative_integer(event["tokens"], "tokens")


class Simulator:
    def __init__(self, manifest: dict[str, Any], trace: dict[str, Any], policy: str):
        self.manifest = manifest
        self.trace = trace
        self.policy = policy
        self.topology = manifest["topology"]
        self.working_sets = {
            key: positive_integer(value, f"working_sets.{key}")
            for key, value in manifest["working_sets"].items()
        }
        self.budget = positive_integer(
            self.topology["fast_tier_budget_bytes"],
            "fast_tier_budget_bytes",
        )
        self.slow_budget = positive_integer(
            self.topology["slow_tier_budget_bytes"],
            "slow_tier_budget_bytes",
        )
        self.slow_tier_semantics = self.topology["slow_tier_semantics"]
        self.slow_occupancy_bytes = sum(self.working_sets.values())
        self.slow_headroom_bytes = self.slow_budget - self.slow_occupancy_bytes
        self.transfer_seconds_per_byte = float(self.topology["transfer_seconds_per_byte"])
        self.miss_penalty_seconds = float(self.topology["miss_penalty_seconds"])
        self.policy_config = manifest["policies"][policy]
        self.overhead = float(self.policy_config["controller_overhead_seconds_per_event"])

        self.resident: collections.OrderedDict[str, None] = collections.OrderedDict()
        self.resident_bytes = 0
        self.bytes_moved = 0
        self.churn_bytes = 0
        self.evictions = 0
        self.demand_hits = 0
        self.demand_misses = 0
        self.seen_demands: set[str] = set()
        self.cold_accesses = 0
        self.warm_accesses = 0
        self.prefetch_loads = 0
        self.prefetch_bytes = 0
        self.peak_occupancy = 0
        self.min_headroom = self.budget
        self.total_latency = 0.0
        self.prefill_latencies: list[float] = []
        self.decode_elapsed = 0.0
        self.decode_tokens = 0
        self.decode_events = 0
        self.miss_penalty_total = 0.0
        self.transfer_seconds_total = 0.0
        self.controller_overhead_total = 0.0

    def _touch(self, name: str) -> None:
        if name in self.resident:
            self.resident.move_to_end(name)

    def _evict_until_fit(self, size: int) -> None:
        while self.resident_bytes + size > self.budget:
            if not self.resident:
                raise ValueError("working set cannot fit under hard budget")
            victim, _ = self.resident.popitem(last=False)
            victim_size = self.working_sets[victim]
            self.resident_bytes -= victim_size
            self.churn_bytes += victim_size
            self.evictions += 1

    def _record_fast_tier(self) -> None:
        self.peak_occupancy = max(self.peak_occupancy, self.resident_bytes)
        self.min_headroom = min(self.min_headroom, self.budget - self.resident_bytes)

    def _load_cached(self, name: str, *, prefetch: bool) -> float:
        if name in self.resident:
            self._touch(name)
            return 0.0

        size = self.working_sets[name]
        self._evict_until_fit(size)
        self.resident[name] = None
        self.resident_bytes += size
        self.bytes_moved += size

        transfer = size * self.transfer_seconds_per_byte
        self.transfer_seconds_total += transfer
        if prefetch:
            self.prefetch_loads += 1
            self.prefetch_bytes += size
        self._record_fast_tier()
        return transfer

    def _demand(self, name: str) -> tuple[bool, float]:
        if self.policy == "static_fixed":
            fixed = set(self.policy_config["fixed_sets"])
            if name in self.resident:
                self.demand_hits += 1
                self._touch(name)
                return True, 0.0

            self.demand_misses += 1
            size = self.working_sets[name]
            transfer = size * self.transfer_seconds_per_byte
            self.bytes_moved += size
            self.transfer_seconds_total += transfer
            self.miss_penalty_total += self.miss_penalty_seconds

            if name in fixed:
                self._evict_until_fit(size)
                self.resident[name] = None
                self.resident_bytes += size
                self._record_fast_tier()

            return False, transfer + self.miss_penalty_seconds

        if name in self.resident:
            self.demand_hits += 1
            self._touch(name)
            return True, 0.0

        self.demand_misses += 1
        transfer = self._load_cached(name, prefetch=False)
        self.miss_penalty_total += self.miss_penalty_seconds
        return False, transfer + self.miss_penalty_seconds

    def _prefetch(self, index: int) -> float:
        if self.policy != "aggressive_prefetch":
            return 0.0

        horizon = int(self.policy_config["lookahead_events"])
        seen: set[str] = set()
        cost = 0.0
        for event in self.trace["events"][index + 1 : index + 1 + horizon]:
            name = event["working_set_id"]
            if name in seen:
                continue
            seen.add(name)
            cost += self._load_cached(name, prefetch=True)
        return cost

    def run(self) -> dict[str, Any]:
        for index, event in enumerate(self.trace["events"]):
            phase = event["phase"]
            name = event["working_set_id"]
            if name in self.seen_demands:
                self.warm_accesses += 1
            else:
                self.cold_accesses += 1
                self.seen_demands.add(name)
            _, demand_cost = self._demand(name)

            controller = self.overhead
            self.controller_overhead_total += controller
            prefetch_cost = self._prefetch(index)

            elapsed = float(event["base_latency_seconds"]) + demand_cost + controller + prefetch_cost
            self.total_latency += elapsed

            if phase == "prefill":
                self.prefill_latencies.append(elapsed)
            if phase == "decode":
                self.decode_events += 1
                self.decode_elapsed += elapsed
                self.decode_tokens += int(event["tokens"])

        accesses = self.demand_hits + self.demand_misses
        if accesses != len(self.trace["events"]):
            raise ValueError("demand accounting mismatch")

        mean_ttft = (
            round_metric(sum(self.prefill_latencies) / len(self.prefill_latencies))
            if self.prefill_latencies
            else None
        )
        if self.decode_events == 0:
            decode_rate = None
            decode_status = "NOT_OBSERVED"
        elif self.decode_elapsed > 0:
            decode_rate = round_metric(self.decode_tokens / self.decode_elapsed)
            decode_status = "MEASURED"
        else:
            decode_rate = None
            decode_status = "OBSERVED_ZERO_DURATION"

        if self.cold_accesses and self.warm_accesses:
            cold_warm_state = "MIXED"
        elif self.cold_accesses:
            cold_warm_state = "COLD_ONLY"
        elif self.warm_accesses:
            cold_warm_state = "WARM_ONLY"
        else:
            cold_warm_state = "NOT_OBSERVED"

        return {
            "policy": self.policy,
            "hard_budget_respected": (
                self.peak_occupancy <= self.budget
                and self.slow_occupancy_bytes <= self.slow_budget
            ),
            "fast_tier_budget_respected": self.peak_occupancy <= self.budget,
            "fast_tier_budget_bytes": self.budget,
            "peak_occupancy_bytes": self.peak_occupancy,
            "minimum_headroom_bytes": self.min_headroom,
            "slow_tier_budget_respected": self.slow_occupancy_bytes <= self.slow_budget,
            "slow_tier_budget_bytes": self.slow_budget,
            "slow_tier_occupancy_bytes": self.slow_occupancy_bytes,
            "slow_tier_headroom_bytes": self.slow_headroom_bytes,
            "slow_tier_semantics": self.slow_tier_semantics,
            "demand_hits": self.demand_hits,
            "demand_misses": self.demand_misses,
            "demand_hit_rate": round_metric(self.demand_hits / accesses),
            "bytes_moved": self.bytes_moved,
            "prefetch_bytes": self.prefetch_bytes,
            "cache_or_state_evictions": self.evictions,
            "cache_or_state_churn_bytes": self.churn_bytes,
            "miss_penalty_seconds": round_metric(self.miss_penalty_total),
            "transfer_seconds": round_metric(self.transfer_seconds_total),
            "controller_overhead_seconds": round_metric(self.controller_overhead_total),
            "total_latency_seconds": round_metric(self.total_latency),
            "mean_ttft_seconds": mean_ttft,
            "ttft_measurement_status": "MEASURED" if mean_ttft is not None else "NOT_OBSERVED",
            "decode_tokens": self.decode_tokens,
            "decode_tokens_per_second": decode_rate,
            "decode_throughput_measurement_status": decode_status,
            "quality_deviation": None,
            "quality_measurement_status": "NOT_MEASURED",
            "cold_accesses": self.cold_accesses,
            "warm_accesses": self.warm_accesses,
            "cold_warm_state": cold_warm_state,
            "topology_id": self.topology["topology_id"],
            "memory_model": self.topology["memory_model"],
        }


def build_receipt(manifest_path: pathlib.Path, trace_path: pathlib.Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    trace = load_json(trace_path)
    validate_fixture(manifest, trace)

    metrics = {
        policy: Simulator(manifest, trace, policy).run()
        for policy in ("static_fixed", "lru", "aggressive_prefetch")
    }

    lru = metrics["lru"]
    prefetch = metrics["aggressive_prefetch"]
    negative_control = {
        "claim": "higher_demand_hit_rate_does_not_imply_lower_system_cost",
        "prefetch_hit_rate_gt_lru": prefetch["demand_hit_rate"] > lru["demand_hit_rate"],
        "prefetch_latency_gt_lru": prefetch["total_latency_seconds"] > lru["total_latency_seconds"],
        "prefetch_bytes_moved_ge_lru": prefetch["bytes_moved"] >= lru["bytes_moved"],
    }
    negative_control["pass"] = all(
        negative_control[key]
        for key in (
            "prefetch_hit_rate_gt_lru",
            "prefetch_latency_gt_lru",
            "prefetch_bytes_moved_ge_lru",
        )
    )

    return {
        "schema_version": RECEIPT_SCHEMA,
        "parent_issue": 64,
        "interpretation_boundary": manifest["interpretation_boundary"],
        "fixture": {
            "manifest_path": repo_relative(manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
            "trace_path": repo_relative(trace_path),
            "trace_sha256": sha256_file(trace_path),
            "topology_id": manifest["topology"]["topology_id"],
            "memory_model": manifest["topology"]["memory_model"],
        },
        "hard_resource_budget": {
            "fast_tier_budget_bytes": manifest["topology"]["fast_tier_budget_bytes"],
            "slow_tier_budget_bytes": manifest["topology"]["slow_tier_budget_bytes"],
            "slow_tier_semantics": manifest["topology"]["slow_tier_semantics"],
        },
        "native_policy_status": manifest["native_policy_status"],
        "deterministic_fallback_policy": manifest["deterministic_fallback_policy"],
        "policies": metrics,
        "negative_control": negative_control,
        "disposition": "BASELINE_RECEIPT_VALID" if negative_control["pass"] else "NEGATIVE_CONTROL_FAILED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--trace", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(args.manifest, args.trace)
    rendered = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

    if args.check:
        if not args.output.is_file():
            raise SystemExit("BASELINE_RECEIPT_MISSING")
        if args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("BASELINE_RECEIPT_STALE")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")

    print(
        "RESOURCE_TOPOLOGY_BASELINE_"
        + ("PASS" if receipt["disposition"] == "BASELINE_RECEIPT_VALID" else "FAIL")
    )
    return 0 if receipt["disposition"] == "BASELINE_RECEIPT_VALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
