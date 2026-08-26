from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "library.py"
SPEC = importlib.util.spec_from_file_location("image_prompt_library_v3", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)
LibraryError = module.LibraryError
PromptLibrary = module.PromptLibrary


class PromptLibraryV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.library = PromptLibrary(self.root)

    def tearDown(self) -> None:
        self.library.close()
        self.temp.cleanup()

    @staticmethod
    def sample(name: str = "古塔自然精修", text: str = "保持古塔结构，天空自然，保留木质纹理。") -> dict:
        return {
            "name": name, "category": "旅行照片", "subcategory": "建筑",
            "tags": "古塔,蓝天,自然", "suitable_for": "户外古建筑",
            "avoid_when": "学术复原", "strengths": "结构保持,自然色彩",
            "prompt_text": text, "notes": "中文 V3 测试",
        }

    def add(self, **extra):
        data = self.sample()
        data.update(extra)
        return self.library.add(data, "add")["prompt"]

    def make_legacy_v2(self) -> PromptLibrary:
        legacy_root = self.root / "legacy-v2"
        legacy_root.mkdir()
        conn = sqlite3.connect(legacy_root / "prompts.db")
        conn.executescript(
            """
            CREATE TABLE prompts (
                id TEXT PRIMARY KEY,name TEXT NOT NULL,category TEXT NOT NULL DEFAULT '其他',
                subcategory TEXT NOT NULL DEFAULT '',tags TEXT NOT NULL DEFAULT '[]',
                suitable_for TEXT NOT NULL DEFAULT '[]',avoid_when TEXT NOT NULL DEFAULT '[]',
                strengths TEXT NOT NULL DEFAULT '[]',prompt_text TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '',
                use_count INTEGER NOT NULL DEFAULT 0,positive_count INTEGER NOT NULL DEFAULT 0,
                negative_count INTEGER NOT NULL DEFAULT 0,user_rating REAL,preference_weight REAL NOT NULL DEFAULT 0,
                favorite INTEGER NOT NULL DEFAULT 0,disabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,updated_at TEXT NOT NULL,last_used_at TEXT,version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE history (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,prompt_id TEXT,event_type TEXT NOT NULL,
                event_value TEXT,context TEXT,timestamp TEXT NOT NULL
            );
            CREATE TABLE meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
            INSERT INTO meta VALUES('next_prompt_number','12');
            INSERT INTO meta VALUES('next_temp_number','1');
            INSERT INTO prompts(id,name,category,subcategory,tags,suitable_for,avoid_when,strengths,
                prompt_text,notes,use_count,positive_count,negative_count,created_at,updated_at,version)
            VALUES('P011','古塔蓝天秋色自然建筑精修','旅行照片','建筑','["古塔","蓝天"]','[]','[]','[]',
                '保持古塔结构并自然处理天空。','',5,3,1,'2026-08-26T00:00:00+08:00','2026-08-26T00:00:00+08:00',4);
            PRAGMA user_version=2;
            """
        )
        conn.commit()
        conn.close()
        return PromptLibrary(legacy_root)

    def test_01_v2_migration_creates_v1(self):
        legacy = self.make_legacy_v2()
        try:
            self.assertEqual([1], [v["version"] for v in legacy.version_list("P011")["versions"]])
            self.assertEqual(1, legacy.get("P011")["version"])
        finally:
            legacy.close()

    def test_02_v2_migration_preserves_counts(self):
        legacy = self.make_legacy_v2()
        try:
            self.assertEqual((5, 3, 1), tuple(legacy.get("P011")[k] for k in
                                             ("use_count", "positive_count", "negative_count")))
        finally:
            legacy.close()

    def test_03_v2_migration_does_not_invent_runs(self):
        legacy = self.make_legacy_v2()
        try:
            self.assertEqual(0, legacy.run_list("P011")["count"])
            self.assertEqual(5, legacy.stats_check("P011")["checks"][0]["legacy_aggregate"]["use_count"])
        finally:
            legacy.close()

    def test_04_new_prompt_creates_v1(self):
        prompt = self.add()
        self.assertEqual(1, self.library.version_get(prompt["id"], 1)["version"])

    def test_05_prompt_text_change_creates_v2(self):
        prompt = self.add()
        changed = self.library.update(prompt["id"], {"prompt_text": "天空更自然，不要过蓝。", "change_note": "控制蓝色"})
        self.assertEqual(2, changed["prompt"]["version"])
        self.assertEqual("控制蓝色", self.library.version_get(prompt["id"], 2)["change_note"])

    def test_06_name_change_does_not_create_version(self):
        prompt = self.add()
        self.library.update(prompt["id"], {"name": "古塔自然精修新版名称"})
        self.assertEqual(1, len(self.library.version_list(prompt["id"])["versions"]))

    def test_07_run_binds_current_version(self):
        prompt = self.add()
        self.library.update(prompt["id"], {"prompt_text": "v2 天空更自然"})
        run = self.library.run_start(prompt["id"], {"scene": "古塔"})["run"]
        self.assertEqual(2, run["prompt_version"])

    def test_08_run_saves_prompt_snapshot(self):
        prompt = self.add()
        run = self.library.run_start(prompt["id"], {"scene": "古塔"})["run"]
        self.assertEqual(prompt["prompt_text"], run["prompt_snapshot"])

    def test_09_old_run_snapshot_is_immutable(self):
        prompt = self.add()
        run_id = self.library.run_start(prompt["id"])["run"]["run_id"]
        self.library.update(prompt["id"], {"prompt_text": "完全新的 v2"})
        self.assertNotEqual(self.library.get(prompt["id"])["prompt_text"], self.library.run_get(run_id)["prompt_snapshot"])

    def test_10_success_run_increments_use(self):
        prompt = self.add()
        run_id = self.library.run_start(prompt["id"])["run"]["run_id"]
        self.library.run_complete(run_id)
        self.assertEqual(1, self.library.get(prompt["id"])["use_count"])

    def test_11_failed_run_does_not_increment_use(self):
        prompt = self.add()
        run_id = self.library.run_start(prompt["id"])["run"]["run_id"]
        self.library.run_fail(run_id, "工具失败")
        self.assertEqual(0, self.library.get(prompt["id"])["use_count"])

    def test_12_positive_feedback_binds_run(self):
        prompt = self.add()
        run_id = self.library.run_start(prompt["id"])["run"]["run_id"]
        self.library.run_complete(run_id)
        self.library.run_feedback(run_id, "positive")
        self.assertEqual("positive", self.library.run_get(run_id)["feedback"])

    def test_13_feedback_change_repairs_aggregates(self):
        prompt = self.add()
        run_id = self.library.run_start(prompt["id"])["run"]["run_id"]
        self.library.run_complete(run_id)
        self.library.run_feedback(run_id, "positive")
        self.library.run_feedback(run_id, "negative")
        current = self.library.get(prompt["id"])
        self.assertEqual((0, 1), (current["positive_count"], current["negative_count"]))

    def test_14_run_can_be_queried(self):
        prompt = self.add()
        run_id = self.library.run_start(prompt["id"])["run"]["run_id"]
        self.assertEqual(run_id, self.library.run_get(run_id)["run_id"])
        self.assertEqual(1, self.library.run_list(prompt["id"])["count"])

    def test_15_version_list_reports_run_statistics(self):
        prompt = self.add()
        run_id = self.library.run_start(prompt["id"])["run"]["run_id"]
        self.library.run_complete(run_id)
        self.library.run_feedback(run_id, "positive")
        version = self.library.version_list(prompt["id"])["versions"][0]
        self.assertEqual((1, 1), (version["runs"], version["positive_runs"]))

    def test_16_version_diff_uses_standard_library(self):
        prompt = self.add()
        self.library.update(prompt["id"], {"prompt_text": "增加天空高光控制"})
        self.assertTrue(self.library.version_diff(prompt["id"], 1, 2)["diff"])

    def test_17_restore_creates_new_version(self):
        prompt = self.add()
        original = prompt["prompt_text"]
        self.library.update(prompt["id"], {"prompt_text": "v2"})
        restored = self.library.version_restore(prompt["id"], 1)["prompt"]
        self.assertEqual((3, original), (restored["version"], restored["prompt_text"]))

    def test_18_temporary_run_migrates_to_formal_v1(self):
        temp = self.library.create_temporary(self.sample(), '{"scene":"古塔"}')["temporary_prompt"]
        run_id = self.library.run_start(temp["temp_id"])["run"]["run_id"]
        self.library.run_complete(run_id)
        formal = self.library.save_temporary(temp["temp_id"])["prompt"]
        run = self.library.run_get(run_id)
        self.assertEqual((formal["id"], 1, None), (run["prompt_id"], run["prompt_version"], run["temporary_prompt_id"]))

    def test_19_temporary_feedback_survives_promotion(self):
        temp = self.library.create_temporary(self.sample())["temporary_prompt"]
        run_id = self.library.run_start(temp["temp_id"])["run"]["run_id"]
        self.library.run_complete(run_id)
        self.library.run_feedback(run_id, "positive")
        formal = self.library.save_temporary(temp["temp_id"])["prompt"]
        self.assertEqual(1, formal["positive_count"])

    def test_20_temporary_provenance_is_recorded(self):
        temp = self.library.create_temporary(self.sample())["temporary_prompt"]
        formal = self.library.save_temporary(temp["temp_id"])["prompt"]
        source = self.library.provenance(formal["id"])["provenance"]
        self.assertEqual(("temporary_generated", temp["temp_id"]),
                         (source["source_type"], source["origin_temporary_id"]))

    def test_21_derived_prompt_records_parent(self):
        parent = self.add()
        child = self.add(name="古塔夜景", prompt_text="夜景古塔自然降噪", parent_prompt_id=parent["id"])
        source = self.library.provenance(child["id"])["provenance"]
        self.assertEqual(("derived", parent["id"], 1),
                         (source["source_type"], source["parent_prompt_id"], source["parent_prompt_version"]))

    def test_22_delete_defaults_to_trash_workflow(self):
        prompt = self.add()
        self.library.trash(prompt["id"])
        self.assertIsNotNone(self.library.get(prompt["id"])["deleted_at"])
        self.assertEqual(1, self.library.trash_list()["count"])

    def test_23_trashed_prompt_is_not_recommended(self):
        prompt = self.add()
        self.library.trash(prompt["id"])
        result = self.library.recommend({prompt["id"]: 95})
        self.assertEqual([], result["recommended"])

    def test_24_trash_restore_works(self):
        prompt = self.add()
        self.library.trash(prompt["id"])
        self.library.trash_restore(prompt["id"])
        self.assertIsNone(self.library.get(prompt["id"])["deleted_at"])

    def test_25_permanent_purge_requires_confirmation(self):
        prompt = self.add()
        self.library.trash(prompt["id"])
        with self.assertRaisesRegex(LibraryError, "明确确认"):
            self.library.trash_purge(prompt["id"], False)

    def test_26_v3_data_persists_after_restart(self):
        prompt = self.add()
        run_id = self.library.run_start(prompt["id"])["run"]["run_id"]
        self.library.run_complete(run_id)
        self.library.close()
        self.library = PromptLibrary(self.root)
        self.assertEqual("success", self.library.run_get(run_id)["status"])

    def test_27_utf8_prompt_metadata_and_context(self):
        prompt = self.add(prompt_text="保持古塔木质纹理，天空不要过蓝。")
        run = self.library.run_start(prompt["id"], {"问题": ["塔身暗部偏重", "天空较亮"]})["run"]
        self.assertIn("天空", run["prompt_snapshot"])
        self.assertEqual("塔身暗部偏重", run["image_context"]["问题"][0])

    def test_28_stats_check_reconciles_legacy_and_runs(self):
        prompt = self.add()
        self.library.use(prompt["id"])
        self.assertTrue(self.library.stats_check(prompt["id"])["checks"][0]["ok"])

    def test_29_sqlite_integrity_is_ok(self):
        self.add()
        self.assertEqual("ok", self.library.stats()["database_status"])
        self.assertEqual(0, self.library.stats()["prompts_without_versions"])

    def test_30_run_ids_are_monotonic_and_not_reused(self):
        prompt = self.add()
        first = self.library.run_start(prompt["id"])["run"]["run_id"]
        self.library.run_fail(first, "失败")
        second = self.library.run_start(prompt["id"])["run"]["run_id"]
        self.assertEqual(("R000001", "R000002"), (first, second))

    def test_31_export_import_preserves_versions_runs_and_feedback(self):
        prompt = self.add()
        self.library.update(prompt["id"], {"prompt_text": "v2 天空更自然"})
        run_id = self.library.run_start(prompt["id"], {"scene": "古塔"})["run"]["run_id"]
        self.library.run_complete(run_id)
        self.library.run_feedback(run_id, "positive")
        export_path = Path(self.library.export_json()["path"])
        imported = PromptLibrary(self.root / "imported-v3")
        try:
            result = imported.import_json(export_path)
            self.assertEqual((2, 1), (result["versions_imported"], result["runs_imported"]))
            self.assertEqual("positive", imported.run_get(run_id)["feedback"])
            self.assertTrue(imported.stats_check(prompt["id"])["checks"][0]["ok"])
        finally:
            imported.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
