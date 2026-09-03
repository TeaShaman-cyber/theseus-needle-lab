import json
import pathlib
import unittest

from scripts.build_realistic_sft_dataset import build_semantic_cases, project_needle_case, build_outputs


ROOT = pathlib.Path(__file__).resolve().parents[1]
FAMILIES = ROOT / "experiments" / "needle-realistic-sft" / "source" / "families.json"


class RealisticSftSemanticDatasetContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.family_spec = json.loads(FAMILIES.read_text(encoding="utf-8"))
        cls.train, cls.heldout = build_semantic_cases(cls.family_spec)

    def test_exact_train_and_heldout_geometry(self):
        self.assertEqual(len(self.train), 360)
        self.assertEqual(len(self.heldout), 96)

        def counts(rows):
            out = {"PROBE": 0, "READY": 0, "UNKNOWN": 0, "NONE": 0}
            for row in rows:
                key = row["expected_decision"] or "NONE"
                out[key] += 1
            return out

        self.assertEqual(counts(self.train), {"PROBE": 100, "READY": 100, "UNKNOWN": 100, "NONE": 60})
        self.assertEqual(counts(self.heldout), {"PROBE": 24, "READY": 24, "UNKNOWN": 24, "NONE": 24})

    def test_case_ids_queries_and_family_splits_are_disjoint(self):
        all_rows = self.train + self.heldout
        case_ids = [row["case_id"] for row in all_rows]
        queries = [row["query"] for row in all_rows]
        self.assertEqual(len(case_ids), len(set(case_ids)))
        self.assertEqual(len(queries), len(set(queries)))

        train_families = {row["family_id"] for row in self.train}
        heldout_families = {row["family_id"] for row in self.heldout}
        self.assertTrue(train_families.isdisjoint(heldout_families))

    def test_every_record_is_repository_authored_and_contract_complete(self):
        required = {
            "case_id",
            "family_id",
            "split",
            "applicability",
            "expected_decision",
            "semantic_rule",
            "query",
            "rationale",
            "derivation_family",
            "entity_variant",
            "schema_contract",
            "source_kind",
        }
        for row in self.train + self.heldout:
            self.assertEqual(set(row), required)
            self.assertEqual(row["source_kind"], "synthetic_repo_authored")
            self.assertEqual(row["schema_contract"], "needle-route-uppercase-v1")
            if row["applicability"] == "route":
                self.assertIn(row["expected_decision"], {"PROBE", "READY", "UNKNOWN"})
            else:
                self.assertEqual(row["applicability"], "none")
                self.assertIsNone(row["expected_decision"])


if __name__ == "__main__":
    unittest.main()


class RealisticSftProjectionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.family_spec = json.loads(FAMILIES.read_text(encoding="utf-8"))
        cls.train, cls.heldout = build_semantic_cases(cls.family_spec)
        cls.schema = {
            "name": "route",
            "parameters": {
                "type": "object",
                "properties": {"decision": {"type": "string", "enum": ["PROBE", "READY", "UNKNOWN"]}},
                "required": ["decision"],
            },
            "description": "Classify the current evidence state. Always use route for this classification. PROBE = current verification is needed and safely possible. READY = current authoritative evidence verifies the state. UNKNOWN = evidence is insufficient and no safe current probe is available.",
        }
        cls.prefix = "Use route to classify the following evidence:\n\n"

    def test_positive_and_negative_projection_are_exact_and_do_not_leak_audit_metadata(self):
        positive = next(row for row in self.train if row["expected_decision"] == "PROBE")
        negative = next(row for row in self.train if row["expected_decision"] is None)

        pos = project_needle_case(positive, self.schema, self.prefix)
        neg = project_needle_case(negative, self.schema, self.prefix)

        self.assertEqual(pos["query"], self.prefix + positive["query"])
        self.assertEqual(pos["tools"], [self.schema])
        self.assertEqual(pos["answers"], [{"name": "route", "arguments": {"decision": "PROBE"}}])
        self.assertEqual(neg["query"], negative["query"])
        self.assertEqual(neg["tools"], [self.schema])
        self.assertEqual(neg["answers"], [])
        for projected in (pos, neg):
            rendered = json.dumps(projected, ensure_ascii=False)
            self.assertNotIn("rationale", rendered)
            self.assertNotIn("semantic_rule", rendered)
            self.assertNotIn("reasoning", projected)
            self.assertNotIn("system", projected)

    def test_frozen_route_contract_bytes_match_accepted_stage_a_digests(self):
        import hashlib
        outputs = build_outputs(self.family_spec, self.schema, self.prefix)
        self.assertEqual(
            hashlib.sha256(outputs["files"]["contract/route-schema.json"]).hexdigest(),
            "e0892212cf97e9d728d8106f4c3fb35bbb09cf0a71bdd9a032b5f457a54ccb7a",
        )
        self.assertEqual(
            hashlib.sha256(outputs["files"]["contract/route-positive-prefix.txt"]).hexdigest(),
            "b8b1697130db2487e50125e2290cf623e3cc259a0647848b19bdf8c9fd465df7",
        )

    def test_build_outputs_are_byte_stable_and_manifests_bind_generated_files(self):
        first = build_outputs(self.family_spec, self.schema, self.prefix)
        second = build_outputs(self.family_spec, self.schema, self.prefix)
        self.assertEqual(first, second)

        for name in ["source/semantic-cases.jsonl", "data/train.needle.jsonl", "data/heldout.eval.jsonl"]:
            self.assertIn(name, first["files"])

        dataset_manifest = json.loads(first["files"]["manifests/dataset-manifest.json"].decode("utf-8"))
        heldout_manifest = json.loads(first["files"]["manifests/heldout-manifest.json"].decode("utf-8"))
        self.assertEqual(dataset_manifest["train_rows"], 360)
        self.assertEqual(heldout_manifest["heldout_rows"], 96)
        self.assertEqual(dataset_manifest["source_kind"], "synthetic_repo_authored")
        self.assertEqual(heldout_manifest["source_kind"], "synthetic_repo_authored")
        for manifest in (dataset_manifest, heldout_manifest):
            for binding in manifest["bindings"]:
                self.assertRegex(binding["sha256"], r"^[0-9a-f]{64}$")
                self.assertIn(binding["path"], first["files"])


class RealisticSftValidatorContractTest(unittest.TestCase):
    def _copy_fixture(self):
        import shutil
        import tempfile
        root = pathlib.Path(tempfile.mkdtemp(prefix="needle-stage-b-test-"))
        src = ROOT / "experiments" / "needle-realistic-sft"
        dst = root / "experiments" / "needle-realistic-sft"
        dst.parent.mkdir(parents=True)
        shutil.copytree(src, dst)
        return root

    def test_validator_rejects_altered_generated_projection(self):
        from scripts.validate_realistic_sft_dataset import validate_repository
        root = self._copy_fixture()
        target = root / "experiments" / "needle-realistic-sft" / "data" / "train.needle.jsonl"
        target.write_bytes(target.read_bytes().replace(b"PROBE", b"READY", 1))
        with self.assertRaisesRegex(ValueError, "generated byte mismatch"):
            validate_repository(root)

    def test_validator_rejects_non_repository_authored_semantic_record(self):
        from scripts.validate_realistic_sft_dataset import validate_repository
        root = self._copy_fixture()
        target = root / "experiments" / "needle-realistic-sft" / "source" / "semantic-cases.jsonl"
        lines = target.read_text(encoding="utf-8").splitlines()
        row = json.loads(lines[0])
        row["source_kind"] = "external_teacher"
        lines[0] = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source kind"):
            validate_repository(root)

    def test_validator_rejects_train_heldout_family_overlap(self):
        from scripts.validate_realistic_sft_dataset import validate_repository
        root = self._copy_fixture()
        target = root / "experiments" / "needle-realistic-sft" / "source" / "families.json"
        spec = json.loads(target.read_text(encoding="utf-8"))
        train_id = next(f["family_id"] for f in spec["families"] if f["split"] == "train")
        held = next(f for f in spec["families"] if f["split"] == "heldout")
        held["family_id"] = train_id
        target.write_text(json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "family overlap"):
            validate_repository(root)

    def test_validator_cli_runs_from_repository_root(self):
        import subprocess
        result = subprocess.run(
            ["python3", "scripts/validate_realistic_sft_dataset.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"status": "VERIFIED"', result.stdout)

    def test_contract_workflow_is_read_only_and_never_trains(self):
        workflow = ROOT / ".github" / "workflows" / "needle-realistic-sft-contract.yml"
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("contents: read", text)
        self.assertIn("actions/checkout@11d5960a326750d5838078e36cf38b85af677262", text)
        self.assertIn("python3 -m unittest discover -s tests -v", text)
        self.assertIn("scripts/build_realistic_sft_dataset.py", text)
        self.assertIn("scripts/validate_realistic_sft_dataset.py", text)
        self.assertNotIn("needle finetune", text)
        self.assertNotIn("workflow_dispatch", text)
        self.assertNotIn("secrets.", text)
