import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_tracked_whitespace.py"

spec = importlib.util.spec_from_file_location("check_tracked_whitespace", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class TrackedWhitespaceTests(unittest.TestCase):
    def test_plain_trailing_space_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.py"
            path.write_bytes(b"x = 1 \n")
            self.assertEqual(len(module.find_violations([path])), 1)

    def test_markdown_exact_two_space_hard_break_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.md"
            path.write_bytes(b"line  \n")
            self.assertEqual(module.find_violations([path]), [])

    def test_markdown_one_or_three_spaces_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            one = Path(tmp) / "one.md"
            three = Path(tmp) / "three.md"
            one.write_bytes(b"line \n")
            three.write_bytes(b"line   \n")
            self.assertEqual(len(module.find_violations([one, three])), 2)

    def test_binary_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blob.bin"
            path.write_bytes(b"abc\0def \n")
            self.assertEqual(module.find_violations([path]), [])


if __name__ == "__main__":
    unittest.main()
