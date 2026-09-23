import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCK = ROOT / "experiments" / "needle3-deployment-canary" / "v1" / "requirements.lock.txt"


class Needle3DependencyLockTests(unittest.TestCase):
    def test_lock_is_complete_exact_and_hash_bound(self):
        lines = [
            line.strip()
            for line in LOCK.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        self.assertEqual(len(lines), 44)
        for line in lines:
            self.assertRegex(line, r"^[A-Za-z0-9_.-]+==[^ ]+ --hash=sha256:[0-9a-f]{64}  # .+\.whl$")

    def test_release_tested_direct_versions_are_pinned(self):
        text = LOCK.read_text(encoding="utf-8")
        expected = {
            "cactus-needle": "3.0.4",
            "huggingface_hub": "1.32.0",
            "numpy": "2.5.3",
            "jax": "0.11.2",
            "jaxlib": "0.11.2",
            "flax": "0.12.9",
            "optax": "0.2.8",
            "safetensors": "0.8.0",
            "sentencepiece": "0.2.2",
        }
        for name, version in expected.items():
            self.assertRegex(text, rf"(?m)^{re.escape(name)}=={re.escape(version)} ")


if __name__ == "__main__":
    unittest.main()
