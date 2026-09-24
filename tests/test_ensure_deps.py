"""Latin-1 SDK sources are rewritten before the start script imports them."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


def _load_ensure_deps():
    path = Path(__file__).resolve().parents[1] / "packaging" / "ensure_deps.py"
    spec = importlib.util.spec_from_file_location("ensure_deps", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ensure_deps = _load_ensure_deps()


class RewriteLatin1SourcesTests(unittest.TestCase):
    def test_latin1_comment_becomes_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lib" / "websockets_testV2.py"
            source.parent.mkdir()
            source.write_bytes("comment = 'échec'\n".encode("latin-1"))
            cache = source.parent / "__pycache__"
            cache.mkdir()
            stale = cache / "websockets_testV2.cpython-314.pyc"
            stale.write_bytes(b"stale")

            rewritten = ensure_deps.rewrite_latin1_sources(root)

            self.assertEqual(rewritten, [source])
            self.assertEqual(source.read_text(encoding="utf-8"), "comment = 'échec'\n")
            self.assertFalse(stale.exists())
            compile(source.read_text(encoding="utf-8"), str(source), "exec")

    def test_valid_utf8_is_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "ok.py"
            original = "# déjà utf-8\n".encode("utf-8")
            source.write_bytes(original)

            rewritten = ensure_deps.rewrite_latin1_sources(root)

            self.assertEqual(rewritten, [])
            self.assertEqual(source.read_bytes(), original)

    def test_missing_directory_is_a_no_op(self):
        self.assertEqual(ensure_deps.rewrite_latin1_sources(Path("does-not-exist")), [])


if __name__ == "__main__":
    unittest.main()
