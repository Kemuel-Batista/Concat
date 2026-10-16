import importlib.util
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from concat_automation.media import adapt_cuts, valid_words, write_captions  # noqa: E402 -- local CLI package bootstrap
from concat_automation import skills  # noqa: E402 -- local CLI package bootstrap
from concat_automation.config import local_path, native_path  # noqa: E402 -- local CLI package bootstrap
from concat_automation.cli import imported_media, remember_projects  # noqa: E402 -- local CLI package bootstrap


class SpeechPlanTests(unittest.TestCase):
    def test_conservative_cut_restores_a_meaningful_short_word(self):
        raw = {
            "palavras": [
                {"w": "é", "ini": 0.3, "fim": 0.4},
                {"w": "essa", "ini": 0.5, "fim": 0.8},
            ],
            "manter": [[0.5, 1]],
            "fora": [0],
            "removidos": [
                {"ini": 0.3, "fim": 0.4, "texto": "é", "motivo": "palavra travada"}
            ],
        }
        result = adapt_cuts(raw, 2, 0.1, 60)
        self.assertEqual(result["fora"], [])
        self.assertLessEqual(result["manter"][0][0], 0.3)
        self.assertEqual(len(result["revisar"]), 1)

    def test_invalid_transcript_cannot_create_a_destructive_edit(self):
        for words in [
            [],
            [{"w": "oi", "ini": 0, "fim": math.nan}],
            [{"w": "oi", "ini": 0, "fim": 20}],
        ]:
            with self.assertRaises(ValueError):
                valid_words(words, 10)

    def test_pause_cut_preserves_all_retained_words_and_order(self):
        raw = {
            "palavras": [
                {"w": "Pontos", "ini": 1, "fim": 1.5},
                {"w": "Milhas", "ini": 5, "fim": 5.5},
            ],
            "manter": [[0.9, 1.6], [4.9, 5.6]],
            "fora": [],
            "removidos": [],
        }
        result = adapt_cuts(raw, 7, 0.1, 60)
        self.assertEqual(len(result["manter"]), 2)
        self.assertLess(result["duracao_final"], 7)
        for word in raw["palavras"]:
            self.assertTrue(
                any(a <= word["ini"] and b >= word["fim"] for a, b in result["manter"])
            )

    def test_stock_originals_are_unchanged(self):
        skills.verify()
        self.assertEqual(
            len(__import__("json").loads((ROOT / "skills.lock.json").read_text())), 5
        )

    def test_windows_and_wsl_paths_roundtrip(self):
        path = Path("/mnt/c/Users/kemuel/Downloads/aula com espaços.mp4")
        self.assertEqual(local_path(native_path(path)), path)

    def test_import_watch_reads_saved_project_without_touching_it(self):
        import json

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            video = folder / "aula.mp4"
            video.write_bytes(b"fixture")
            document = json.dumps(
                {"media": [{"path": str(video), "kind": "video", "hasAudio": True}]}
            )
            manifest = folder / "concat.json"
            manifest.write_text(document)
            self.assertEqual(imported_media([{"path": str(folder)}]), [video])
            self.assertEqual(manifest.read_text(), document)
            (folder / "personal-automation.json").write_text('{"generated":true}')
            self.assertEqual(imported_media([{"path": str(folder)}]), [])

    def test_caption_rounding_carries_into_next_second(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "legendas.srt"
            write_captions([{"ini": 59.9996, "fim": 61, "texto": "Olá"}], output)
            self.assertIn("00:01:00,000 --> 00:01:01,000", output.read_text())

    def test_source_project_survives_recent_list_eviction(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "watched.json"
            source = [{"path": str(Path(directory) / "aula")}]
            remember_projects(source, store)
            self.assertEqual(remember_projects([], store), source)

    def test_upstream_api_contract_is_supported(self):
        spec = importlib.util.spec_from_file_location("updater", ROOT / "update.py")
        updater = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(updater)
        updater.validate_source(ROOT.parent)


if __name__ == "__main__":
    unittest.main()
