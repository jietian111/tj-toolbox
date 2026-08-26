from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "library.py"
SPEC = importlib.util.spec_from_file_location("image_prompt_library", SCRIPT)
library_module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(library_module)
LibraryError = library_module.LibraryError
PromptLibrary = library_module.PromptLibrary


class PromptLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.library = PromptLibrary(self.root)

    def tearDown(self) -> None:
        self.library.close()
        self.temp.cleanup()

    def sample(self, name: str = "同人物自然精修", prompt: str | None = None) -> dict:
        return {
            "name": name,
            "category": "人像",
            "subcategory": "自然精修",
            "tags": ["身份保持", "真实肤质", "轻微小脸"],
            "suitable_for": ["日常人像", "背景略杂乱"],
            "avoid_when": ["证件真实性审核"],
            "strengths": ["自然", "保持五官"],
            "prompt_text": prompt or "保持本人身份与五官特征，轻微优化脸型，保留真实皮肤纹理。",
            "notes": "中文测试",
        }

    def test_full_lifecycle_and_utf8_persistence(self) -> None:
        self.assertTrue(self.library.init_info()["empty"])
        created = self.library.add(self.sample())
        self.assertEqual("created", created["status"])
        self.assertEqual("P001", created["prompt"]["id"])
        self.assertEqual("同人物自然精修", self.library.get("P001")["name"])

        updated = self.library.update("P001", {"name": "自然高级人像精修", "tags": "身份保持,自然美颜,中文标签"})
        self.assertEqual(1, updated["prompt"]["version"])
        self.assertEqual(1, len(self.library.version_list("P001")["versions"]))
        self.assertEqual(1, self.library.search("中文标签")["count"])
        self.assertEqual(1, self.library.search("找一下保持本人长相并稍微小脸的提示词")["count"])

        used = self.library.use("P001", "一张室内人像")
        self.assertEqual(1, used["prompt"]["use_count"])
        self.assertTrue(Path(used["backup"]).exists())
        self.library.feedback("P001", "positive", "这个效果很好")
        self.library.feedback("P001", "negative", "这次不太适合")
        rated = self.library.rate("P001", 5)
        self.assertEqual(5, rated["prompt"]["user_rating"])
        self.assertEqual(1, rated["prompt"]["positive_count"])
        self.assertEqual(1, rated["prompt"]["negative_count"])

        self.assertTrue(self.library.set_flag("P001", "disabled", True)["prompt"]["disabled"])
        self.assertEqual(0, self.library.candidates("人像", None, "身份保持", "自然", 5)["count"])
        self.assertFalse(self.library.set_flag("P001", "disabled", False)["prompt"]["disabled"])
        self.assertTrue(self.library.set_flag("P001", "favorite", True)["prompt"]["favorite"])

        export = self.library.export_json()
        exported = json.loads(Path(export["path"]).read_text(encoding="utf-8"))
        self.assertEqual("自然高级人像精修", exported["prompts"][0]["name"])
        self.assertIn("保持本人身份", exported["prompts"][0]["prompt_text"])
        self.assertTrue(Path(self.library.backup("test")["backup"]).exists())

        self.library.close()
        self.library = PromptLibrary(self.root)
        persisted = self.library.get("P001")
        self.assertEqual("自然高级人像精修", persisted["name"])
        self.assertEqual(1, persisted["use_count"])

    def test_use_only_operation_and_undo(self) -> None:
        self.library.add(self.sample())
        self.library.get("P001")
        self.library.list_prompts()
        self.library.search("人像")
        self.library.candidates("人像", None, "身份保持", "日常", 5)
        self.assertEqual(0, self.library.get("P001")["use_count"])
        self.library.use("P001")
        undone = self.library.undo_use("P001")
        self.assertEqual(0, undone["prompt"]["use_count"])
        with self.assertRaisesRegex(LibraryError, "没有可撤回"):
            self.library.undo_use("P001")

    def test_duplicate_detection_and_explicit_add(self) -> None:
        self.library.add(self.sample())
        duplicate = self.library.add(self.sample(name="相同内容的新名字"))
        self.assertEqual("duplicate_found", duplicate["status"])
        self.assertEqual(1, self.library.stats()["total"])
        explicit = self.library.add(self.sample(name="相同内容的新名字"), "add")
        self.assertEqual("P002", explicit["prompt"]["id"])
        self.assertEqual(2, self.library.stats()["total"])

    def test_merge_preserves_statistics_and_history(self) -> None:
        self.library.add(self.sample())
        self.library.add(self.sample("胶片自然人像", "加入柔和胶片色调，但保持人物身份与真实皮肤。"), "add")
        self.library.use("P001")
        self.library.use("P002")
        self.library.feedback("P002", "positive")
        result = self.library.merge("P001", "P002")
        self.assertEqual(2, result["prompt"]["use_count"])
        self.assertEqual(1, result["prompt"]["positive_count"])
        with self.assertRaisesRegex(LibraryError, "未找到"):
            self.library.get("P002")
        history_count = self.library.conn.execute("SELECT COUNT(*) FROM history WHERE prompt_id='P001'").fetchone()[0]
        self.assertGreaterEqual(history_count, 6)

    def test_import_validation_conflict_and_remap(self) -> None:
        self.library.add(self.sample())
        export_path = Path(self.library.export_json()["path"])
        other_root = self.root / "other"
        other = PromptLibrary(other_root)
        try:
            first = other.import_json(export_path)
            self.assertEqual(["P001"], first["created"])
            second = other.import_json(export_path, "skip")
            self.assertTrue(second["skipped"])
        finally:
            other.close()
        bad = self.root / "bad.json"
        bad.write_text('{"format":"wrong","prompts":[]}', encoding="utf-8")
        with self.assertRaisesRegex(LibraryError, "格式无效"):
            self.library.import_json(bad)

    def test_delete_requires_confirmation_and_ids_never_reused(self) -> None:
        self.library.add(self.sample())
        with self.assertRaisesRegex(LibraryError, "明确确认"):
            self.library.delete("P001", False)
        self.library.delete("P001", True)
        created = self.library.add(self.sample("新条目"), "add")
        self.assertEqual("P002", created["prompt"]["id"])

    def test_invalid_id_has_clear_error(self) -> None:
        with self.assertRaisesRegex(LibraryError, "非法 Prompt ID"):
            self.library.get("7")
        with self.assertRaisesRegex(LibraryError, "未找到 Prompt：P999"):
            self.library.get("P999")

    def test_cli_restart_and_machine_readable_json(self) -> None:
        cli_root = self.root / "cli"
        base = [sys.executable, str(SCRIPT), "--data-dir", str(cli_root), "--json"]
        init = subprocess.run(base + ["init"], check=True, capture_output=True, text=True, encoding="utf-8")
        self.assertTrue(json.loads(init.stdout)["empty"])
        add = subprocess.run(base + ["add", "--name", "中文产品精修", "--category", "产品摄影",
                                     "--tags", "干净背景,材质", "--prompt-text", "突出产品材质并清理背景杂物。"],
                             check=True, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual("P001", json.loads(add.stdout)["prompt"]["id"])
        get = subprocess.run(base + ["get", "P001"], check=True, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual("中文产品精修", json.loads(get.stdout)["prompt"]["name"])
        bad = subprocess.run(base + ["get", "BAD"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(1, bad.returncode)
        self.assertIn("非法 Prompt ID", json.loads(bad.stderr)["error"])

    def add_recommendation_fixtures(self) -> None:
        fixtures = [
            ("日系手账 PLOG", "旅行照片", "日系记录", "旅行,日系,PLOG", "把旅行照片处理成清爽日系手账记录。"),
            ("毕业史诗海报", "海报设计", "毕业", "毕业,史诗,海报", "制作宏大电影感毕业海报。"),
            ("萌系涂鸦", "插画风格", "萌系", "萌系,涂鸦,可爱", "添加可爱萌系彩色涂鸦。"),
        ]
        for name, category, subcategory, tags, prompt in fixtures:
            self.library.add({
                "name": name, "category": category, "subcategory": subcategory,
                "tags": tags, "suitable_for": tags, "avoid_when": "",
                "strengths": tags, "prompt_text": prompt, "notes": "",
            }, "add")

    def test_recommendation_ids_quality_gate_and_real_statistics(self) -> None:
        self.add_recommendation_fixtures()
        for _ in range(3):
            self.library.use("P001")
        for _ in range(2):
            self.library.feedback("P001", "positive")
        result = self.library.recommend({"P001": 72, "P002": 38, "P003": 27}, "蓝天 古塔 秋叶")
        self.assertEqual("coverage_gap", result["coverage"])
        self.assertTrue(result["needs_temporary_prompt"])
        self.assertEqual(1, result["recommended_count"])
        item = result["recommended"][0]
        self.assertEqual({"prompt_id", "name", "match_score", "use_count",
                          "positive_count", "negative_count"},
                         {"prompt_id", "name", "match_score", "use_count",
                          "positive_count", "negative_count"} & item.keys())
        self.assertEqual("P001", item["prompt_id"])
        self.assertEqual(72, item["match_score"])
        self.assertEqual(3, item["use_count"])
        self.assertEqual(2, item["positive_count"])

    def test_low_matches_are_hidden_unless_show_all(self) -> None:
        self.add_recommendation_fixtures()
        hidden = self.library.recommend({"P001": 72, "P002": 38, "P003": 27})
        self.assertNotIn("excluded", hidden)
        shown = self.library.recommend({"P001": 72, "P002": 38, "P003": 27}, show_all=True)
        self.assertEqual(["P002", "P003"], [item["prompt_id"] for item in shown["excluded"]])

    def test_no_match_requires_temporary_prompt(self) -> None:
        self.add_recommendation_fixtures()
        result = self.library.recommend({"P001": 49, "P002": 38, "P003": 27})
        self.assertEqual("no_match", result["coverage"])
        self.assertEqual([], result["recommended"])
        self.assertTrue(result["needs_temporary_prompt"])
        self.assertEqual("first", result["temporary_priority"])

    def test_recommend_excludes_disabled_and_avoid_when_conflicts(self) -> None:
        self.add_recommendation_fixtures()
        self.library.set_flag("P001", "disabled", True)
        self.library.update("P002", {"avoid_when": "古建筑旅行照片"})
        result = self.library.recommend(
            {"P001": 95, "P002": 88, "P003": 70}, "蓝天古塔秋叶的古建筑旅行照片", show_all=True
        )
        self.assertEqual(["P003"], [item["prompt_id"] for item in result["recommended"]])
        reasons = {item["prompt_id"]: item["excluded_reason"] for item in result["excluded"]}
        self.assertEqual("disabled", reasons["P001"])
        self.assertEqual("avoid_when", reasons["P002"])

    def test_use_and_feedback_changes_persist_with_before_after_values(self) -> None:
        self.library.add(self.sample())
        for _ in range(3):
            self.library.use("P001")
        used = self.library.use("P001")
        self.assertEqual((3, 4), (used["use_count_before"], used["use_count_after"]))
        for _ in range(2):
            self.library.feedback("P001", "positive")
        positive = self.library.feedback("P001", "positive")
        self.assertEqual((2, 3), (positive["positive_count_before"], positive["positive_count_after"]))
        weight_before = positive["preference_weight_after"]
        negative = self.library.feedback("P001", "negative")
        self.assertEqual((0, 1), (negative["negative_count_before"], negative["negative_count_after"]))
        self.assertLess(negative["preference_weight_after"], weight_before)
        self.library.close()
        self.library = PromptLibrary(self.root)
        prompt = self.library.get("P001")
        self.assertEqual(4, prompt["use_count"])
        self.assertEqual(3, prompt["positive_count"])
        self.assertEqual(1, prompt["negative_count"])

    def test_temporary_prompt_lifecycle_and_statistics_migration(self) -> None:
        temporary = self.library.create_temporary({
            "name": "古建筑旅行自然精修", "category": "旅行照片", "subcategory": "建筑",
            "tags": "古建筑,自然精修,透视,天空,秋叶",
            "suitable_for": "蓝天古塔,秋叶旅行照", "avoid_when": "建筑结构需要学术复原",
            "strengths": "保持真实性,控制天空,透视校正",
            "prompt_text": "保持古塔真实结构，轻微透视校正，提亮暗部并压制过亮天空，增强秋叶暖色。",
            "notes": "模拟验收",
        }, "蓝天 + 古塔 + 秋叶的旅行照片")
        self.assertEqual("T001", temporary["temporary_prompt"]["temp_id"])
        self.assertEqual(0, self.library.stats()["total"])
        self.assertEqual("1", self.library.conn.execute(
            "SELECT value FROM meta WHERE key='next_prompt_number'"
        ).fetchone()[0])
        used = self.library.use_temporary("T001")
        self.assertEqual((0, 1), (used["use_count_before"], used["use_count_after"]))
        feedback = self.library.feedback_last("positive", "挺不错的")
        self.assertEqual(1, feedback["positive_count_after"])
        saved = self.library.save_temporary("T001")
        self.assertEqual("P001", saved["prompt"]["id"])
        self.assertEqual(1, saved["prompt"]["use_count"])
        self.assertEqual(1, saved["prompt"]["positive_count"])
        self.assertEqual("saved", self.library.get_temporary("T001")["status"])

    def test_temporary_prompt_becomes_p004_in_acceptance_scenario(self) -> None:
        self.add_recommendation_fixtures()
        temp = self.library.create_temporary({
            "name": "古建筑旅行自然精修", "category": "旅行照片", "subcategory": "建筑",
            "tags": "古建筑,自然精修,透视,天空,秋叶", "suitable_for": "古建筑旅行照",
            "avoid_when": "", "strengths": "保持建筑真实性", "prompt_text": "保持结构并自然精修。",
            "notes": "",
        })
        self.library.use_temporary(temp["temporary_prompt"]["temp_id"])
        self.library.feedback_temporary("T001", "positive")
        saved = self.library.save_temporary("T001")
        self.assertEqual("P004", saved["prompt"]["id"])
        self.assertEqual(1, saved["prompt"]["use_count"])
        self.assertEqual(1, saved["prompt"]["positive_count"])
        self.assertEqual(0, self.library.get("P001")["use_count"])

    def test_feedback_last_binds_actual_use_not_browse(self) -> None:
        self.library.add(self.sample("方案一"), "add")
        self.library.add(self.sample("方案二", "另一套完全不同的照片处理方法。"), "add")
        self.library.use("P001")
        self.library.get("P002")
        self.library.search("方案二")
        result = self.library.feedback_last("positive")
        self.assertEqual("P001", result["prompt"]["id"])
        self.assertEqual(0, self.library.get("P002")["positive_count"])

    def test_v1_database_auto_migrates_without_data_loss(self) -> None:
        self.library.add(self.sample())
        self.library.close()
        connection = sqlite3.connect(self.root / "prompts.db")
        connection.execute("DROP TABLE temporary_prompts")
        connection.execute("DELETE FROM meta WHERE key='next_temp_number'")
        connection.execute("PRAGMA user_version=0")
        connection.commit()
        connection.close()
        self.library = PromptLibrary(self.root)
        self.assertEqual("同人物自然精修", self.library.get("P001")["name"])
        self.assertEqual(3, self.library.conn.execute("PRAGMA user_version").fetchone()[0])
        self.assertIsNotNone(self.library.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='temporary_prompts'"
        ).fetchone())
        self.assertTrue(list((self.root / "backups").glob("*before-schema-v2.db")))

    def test_database_status_reports_persistent_totals(self) -> None:
        self.library.add(self.sample())
        self.library.use("P001")
        self.library.feedback("P001", "positive")
        status = self.library.stats()
        self.assertEqual("ok", status["database_status"])
        self.assertEqual(1, status["total_use_count"])
        self.assertEqual(1, status["total_positive_count"])
        self.assertEqual(0, status["total_negative_count"])
        self.assertTrue(status["database"].endswith("prompts.db"))

    def test_empty_status_includes_actionable_onboarding(self) -> None:
        empty = self.library.stats()
        self.assertTrue(empty["library_empty"])
        self.assertTrue(empty["onboarding"]["required"])
        self.assertIn("收进图片库", " ".join(empty["onboarding"]["examples"]))

        self.library.add(self.sample())
        populated = self.library.stats()
        self.assertFalse(populated["library_empty"])
        self.assertIsNone(populated["onboarding"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
