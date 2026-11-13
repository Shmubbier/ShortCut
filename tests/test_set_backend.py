import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("set_backend", Path(__file__).resolve().parent.parent / "deploy" / "set_backend.py")
set_backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(set_backend)


class BuildConfig(unittest.TestCase):
    def test_rewrites_and_build_settings(self):
        cfg = set_backend.build_config("https://x.up.railway.app/")
        sources = [r["source"] for r in cfg["rewrites"]]
        self.assertEqual(len(sources), 9)
        self.assertIn("/admin", sources)
        self.assertIn("/admin/:path*", sources)
        self.assertFalse([s for s in sources if s.startswith(("/demo", "/_app"))])
        self.assertTrue(all(r["destination"].startswith("https://x.up.railway.app/") for r in cfg["rewrites"]))
        self.assertEqual((cfg["framework"], cfg["buildCommand"], cfg["outputDirectory"]), ("vite", "npm run build", "dist"))

    def test_rejects_non_https(self):
        with self.assertRaises(ValueError):
            set_backend.build_config("http://x.example.com")


if __name__ == "__main__":
    unittest.main()
