#!/usr/bin/env python3
"""Local SQLite prompt library for the image-prompt-manager Skill.

Only Python's standard library is required. All mutating commands use transactions;
important content mutations also create rotating online backups.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import math
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Sequence


FORMAT_NAME = "image-prompt-manager"
FORMAT_VERSION = 2
SCHEMA_VERSION = 3
DEFAULT_SETTINGS = {"backup_keep": 25, "duplicate_threshold": 0.85}
HIGH_MATCH_THRESHOLD = 80.0
MIN_MATCH_THRESHOLD = 65.0
JSON_FIELDS = ("tags", "suitable_for", "avoid_when", "strengths")
EDITABLE_FIELDS = (
    "name", "category", "subcategory", "tags", "suitable_for", "avoid_when",
    "strengths", "prompt_text", "notes",
)
VERSION_METADATA_FIELDS = (
    "name", "category", "subcategory", "tags", "suitable_for", "avoid_when", "strengths",
)
SOURCE_TYPES = {"manual", "chat_capture", "temporary_generated", "derived", "imported", "unknown"}
RUN_STATUSES = {"running", "success", "failed", "cancelled"}
RUN_FEEDBACK = {"positive", "neutral", "negative", "never"}


class LibraryError(Exception):
    """Expected user-facing error."""


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def split_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[,，/；;\n]+", str(value))
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def json_text(value: Any) -> str:
    return json.dumps(split_list(value), ensure_ascii=False, separators=(",", ":"))


def parse_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return split_list(value)
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return split_list(value)
    return split_list(decoded)


def normalize_id(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"P\d{3,}", value):
        raise LibraryError(f"非法 Prompt ID：{value or '(empty)'}；应类似 P007")
    return value


def normalize_temp_id(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"T\d{3,}", value):
        raise LibraryError(f"非法临时 Prompt ID：{value or '(empty)'}；应类似 T001")
    return value


def normalize_run_id(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"R\d{6,}", value):
        raise LibraryError(f"非法 Run ID：{value or '(empty)'}；应类似 R000021")
    return value


def compact_json(value: Any) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "{}"
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = {"summary": text}
    else:
        decoded = value
    return json.dumps(decoded, ensure_ascii=False, separators=(",", ":"))


def parse_match_scores(value: str) -> dict[str, float]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        decoded = {}
        for part in re.split(r"[,，;；]+", value):
            if not part.strip():
                continue
            try:
                key, score = part.split("=", 1)
                decoded[key.strip()] = float(score.strip())
            except (ValueError, TypeError) as exc:
                raise LibraryError("匹配分数格式应为 JSON 对象或 P001=72,P002=38") from exc
    if not isinstance(decoded, dict) or not decoded:
        raise LibraryError("至少需要一个 Prompt 匹配分数")
    result: dict[str, float] = {}
    for key, score in decoded.items():
        prompt_id = normalize_id(str(key))
        try:
            number = float(score)
        except (TypeError, ValueError) as exc:
            raise LibraryError(f"{prompt_id} 的匹配分数无效") from exc
        if not 0 <= number <= 100:
            raise LibraryError(f"{prompt_id} 的匹配分数必须在 0 到 100 之间")
        result[prompt_id] = number
    return result


def query_terms(value: str) -> list[str]:
    """Tokenize Latin words and Chinese runs without third-party segmenters."""
    terms: list[str] = []
    terms.extend(word.casefold() for word in re.findall(r"[a-zA-Z0-9_]+", value))
    for run in re.findall(r"[\u3400-\u9fff]+", value):
        if len(run) == 1:
            terms.append(run)
        else:
            terms.extend(run[i:i + 2] for i in range(len(run) - 1))
    return list(dict.fromkeys(terms))


class PromptLibrary:
    def __init__(self, data_dir: Path):
        self.root = data_dir.expanduser().resolve()
        self.db_path = self.root / "prompts.db"
        self.settings_path = self.root / "settings.json"
        self.backups_dir = self.root / "backups"
        self.exports_dir = self.root / "exports"
        self._ensure_layout()
        self.settings = self._load_settings()
        self.conn = sqlite3.connect(self.db_path, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = FULL")
        self.conn.execute("PRAGMA busy_timeout = 10000")
        self._create_schema()

    def close(self) -> None:
        self.conn.close()

    def _ensure_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(exist_ok=True)
        self.exports_dir.mkdir(exist_ok=True)

    def _load_settings(self) -> dict[str, Any]:
        if self.settings_path.exists():
            try:
                data = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("settings root must be an object")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise LibraryError(f"settings.json 无法读取：{exc}") from exc
            return {**DEFAULT_SETTINGS, **data}
        temp = self.settings_path.with_suffix(".tmp")
        temp.write_text(json.dumps(DEFAULT_SETTINGS, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.settings_path)
        return dict(DEFAULT_SETTINGS)

    def _create_schema(self) -> None:
        existing_tables = {
            row[0] for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        needs_v2_backup = "prompts" in existing_tables and "temporary_prompts" not in existing_tables
        needs_v3_backup = "prompts" in existing_tables and "prompt_versions" not in existing_tables
        if needs_v2_backup:
            self.backup("before-schema-v2")
        if needs_v3_backup:
            self.backup("before-schema-v3")
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS prompts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '其他',
                    subcategory TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    suitable_for TEXT NOT NULL DEFAULT '[]',
                    avoid_when TEXT NOT NULL DEFAULT '[]',
                    strengths TEXT NOT NULL DEFAULT '[]',
                    prompt_text TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    use_count INTEGER NOT NULL DEFAULT 0 CHECK(use_count >= 0),
                    positive_count INTEGER NOT NULL DEFAULT 0 CHECK(positive_count >= 0),
                    negative_count INTEGER NOT NULL DEFAULT 0 CHECK(negative_count >= 0),
                    user_rating REAL CHECK(user_rating IS NULL OR (user_rating >= 1 AND user_rating <= 5)),
                    preference_weight REAL NOT NULL DEFAULT 0,
                    favorite INTEGER NOT NULL DEFAULT 0 CHECK(favorite IN (0,1)),
                    disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0,1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used_at TEXT,
                    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1)
                );
                CREATE TABLE IF NOT EXISTS history (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_id TEXT REFERENCES prompts(id) ON UPDATE CASCADE ON DELETE SET NULL,
                    event_type TEXT NOT NULL,
                    event_value TEXT,
                    context TEXT,
                    timestamp TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_prompts_category ON prompts(category, subcategory);
                CREATE INDEX IF NOT EXISTS idx_prompts_disabled ON prompts(disabled);
                CREATE INDEX IF NOT EXISTS idx_history_prompt_time ON history(prompt_id, timestamp);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT OR IGNORE INTO meta(key, value) VALUES ('next_prompt_number', '1');
                INSERT OR IGNORE INTO meta(key, value) VALUES ('next_temp_number', '1');
                INSERT OR IGNORE INTO meta(key, value) VALUES ('next_run_number', '1');
                CREATE TABLE IF NOT EXISTS temporary_prompts (
                    temp_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '其他',
                    subcategory TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    suitable_for TEXT NOT NULL DEFAULT '[]',
                    avoid_when TEXT NOT NULL DEFAULT '[]',
                    strengths TEXT NOT NULL DEFAULT '[]',
                    prompt_text TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    image_context TEXT NOT NULL DEFAULT '',
                    use_count INTEGER NOT NULL DEFAULT 0 CHECK(use_count >= 0),
                    positive_count INTEGER NOT NULL DEFAULT 0 CHECK(positive_count >= 0),
                    negative_count INTEGER NOT NULL DEFAULT 0 CHECK(negative_count >= 0),
                    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','used','saved','discarded')),
                    formal_prompt_id TEXT REFERENCES prompts(id) ON UPDATE CASCADE ON DELETE SET NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_temporary_status ON temporary_prompts(status, updated_at);
                """
            )
            prompt_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(prompts)")}
            additions = {
                "deleted_at": "TEXT",
                "source_type": "TEXT NOT NULL DEFAULT 'unknown'",
                "source_ref": "TEXT",
                "source_note": "TEXT",
                "parent_prompt_id": "TEXT REFERENCES prompts(id) ON UPDATE CASCADE ON DELETE SET NULL",
                "parent_prompt_version": "INTEGER",
                "origin_temporary_id": "TEXT",
                "legacy_use_count": "INTEGER NOT NULL DEFAULT 0",
                "legacy_positive_count": "INTEGER NOT NULL DEFAULT 0",
                "legacy_negative_count": "INTEGER NOT NULL DEFAULT 0",
            }
            for column, definition in additions.items():
                if column not in prompt_columns:
                    self.conn.execute(f"ALTER TABLE prompts ADD COLUMN {column} {definition}")
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS prompt_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_id TEXT NOT NULL REFERENCES prompts(id) ON UPDATE CASCADE ON DELETE CASCADE,
                    version INTEGER NOT NULL CHECK(version >= 1),
                    prompt_text TEXT NOT NULL,
                    metadata_snapshot TEXT NOT NULL DEFAULT '{}',
                    change_note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(prompt_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_prompt_versions_prompt_version
                    ON prompt_versions(prompt_id, version);
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    prompt_id TEXT REFERENCES prompts(id) ON UPDATE CASCADE ON DELETE CASCADE,
                    prompt_version INTEGER,
                    temporary_prompt_id TEXT REFERENCES temporary_prompts(temp_id) ON UPDATE CASCADE ON DELETE SET NULL,
                    image_context TEXT NOT NULL DEFAULT '{}',
                    prompt_snapshot TEXT NOT NULL,
                    executor TEXT NOT NULL DEFAULT 'unknown',
                    model TEXT,
                    status TEXT NOT NULL CHECK(status IN ('running','success','failed','cancelled')),
                    result_ref TEXT,
                    result_path TEXT,
                    error_summary TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    feedback TEXT CHECK(feedback IS NULL OR feedback IN ('positive','neutral','negative','never')),
                    feedback_at TEXT,
                    CHECK(prompt_id IS NOT NULL OR temporary_prompt_id IS NOT NULL)
                );
                CREATE INDEX IF NOT EXISTS idx_runs_prompt ON runs(prompt_id);
                CREATE INDEX IF NOT EXISTS idx_runs_prompt_version ON runs(prompt_id, prompt_version);
                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
                CREATE INDEX IF NOT EXISTS idx_runs_completed ON runs(completed_at);
                CREATE INDEX IF NOT EXISTS idx_prompts_deleted ON prompts(deleted_at);
                """
            )
            if needs_v3_backup:
                self.conn.execute(
                    """UPDATE prompts SET version=1,source_type='unknown',
                       legacy_use_count=use_count,legacy_positive_count=positive_count,
                       legacy_negative_count=negative_count"""
                )
            for row in self.conn.execute("SELECT * FROM prompts ORDER BY id").fetchall():
                exists = self.conn.execute(
                    "SELECT 1 FROM prompt_versions WHERE prompt_id=? AND version=?",
                    (row["id"], row["version"]),
                ).fetchone()
                if not exists:
                    self._insert_version_snapshot(row["id"], row["version"], row["prompt_text"],
                                                  "V2 数据迁移生成初始快照" if needs_v3_backup else "初始快照")
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            highest = self.conn.execute(
                "SELECT COALESCE(MAX(CAST(SUBSTR(id,2) AS INTEGER)),0) FROM prompts"
            ).fetchone()[0]
            current = int(self.conn.execute(
                "SELECT value FROM meta WHERE key='next_prompt_number'"
            ).fetchone()[0])
            if current <= highest:
                self.conn.execute(
                    "UPDATE meta SET value=? WHERE key='next_prompt_number'", (str(highest + 1),)
                )

    def init_info(self) -> dict[str, Any]:
        count = self.conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]
        return {
            "status": "ok", "data_dir": str(self.root), "database": str(self.db_path),
            "prompt_count": count, "empty": count == 0,
        }

    def _next_id(self) -> str:
        number = int(self.conn.execute(
            "SELECT value FROM meta WHERE key='next_prompt_number'"
        ).fetchone()[0])
        self.conn.execute(
            "UPDATE meta SET value=? WHERE key='next_prompt_number'", (str(number + 1),)
        )
        return f"P{number:03d}"

    def _next_temp_id(self) -> str:
        number = int(self.conn.execute(
            "SELECT value FROM meta WHERE key='next_temp_number'"
        ).fetchone()[0])
        self.conn.execute(
            "UPDATE meta SET value=? WHERE key='next_temp_number'", (str(number + 1),)
        )
        return f"T{number:03d}"

    def _next_run_id(self) -> str:
        number = int(self.conn.execute(
            "SELECT value FROM meta WHERE key='next_run_number'"
        ).fetchone()[0])
        self.conn.execute(
            "UPDATE meta SET value=? WHERE key='next_run_number'", (str(number + 1),)
        )
        return f"R{number:06d}"

    def _version_metadata(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        decoded = self.decode_row(row) if isinstance(row, sqlite3.Row) else dict(row)
        return {field: decoded.get(field, [] if field in JSON_FIELDS else "")
                for field in VERSION_METADATA_FIELDS}

    def _insert_version_snapshot(self, prompt_id: str, version: int, prompt_text: str,
                                 change_note: str = "") -> None:
        row = self.conn.execute("SELECT * FROM prompts WHERE id=?", (prompt_id,)).fetchone()
        if row is None:
            raise LibraryError(f"未找到 Prompt：{prompt_id}")
        self.conn.execute(
            """INSERT INTO prompt_versions(prompt_id,version,prompt_text,metadata_snapshot,change_note,created_at)
               VALUES(?,?,?,?,?,?)""",
            (prompt_id, version, prompt_text,
             json.dumps(self._version_metadata(row), ensure_ascii=False, separators=(",", ":")),
             change_note or "", now()),
        )

    def _history(self, prompt_id: str | None, event_type: str, value: Any = None,
                 context: Any = None) -> int:
        if value is not None and not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if context is not None and not isinstance(context, str):
            context = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        cur = self.conn.execute(
            "INSERT INTO history(prompt_id,event_type,event_value,context,timestamp) VALUES(?,?,?,?,?)",
            (prompt_id, event_type, value, context, now()),
        )
        return int(cur.lastrowid)

    def _row(self, prompt_id: str) -> sqlite3.Row:
        prompt_id = normalize_id(prompt_id)
        row = self.conn.execute("SELECT * FROM prompts WHERE id=?", (prompt_id,)).fetchone()
        if row is None:
            raise LibraryError(f"未找到 Prompt：{prompt_id}")
        return row

    @staticmethod
    def decode_row(row: sqlite3.Row | dict[str, Any], include_prompt: bool = True) -> dict[str, Any]:
        data = dict(row)
        for field in JSON_FIELDS:
            data[field] = parse_json_list(data.get(field))
        data["favorite"] = bool(data.get("favorite"))
        data["disabled"] = bool(data.get("disabled"))
        if not include_prompt:
            data.pop("prompt_text", None)
            data.pop("notes", None)
        return data

    def get(self, prompt_id: str) -> dict[str, Any]:
        return self.decode_row(self._row(prompt_id))

    def backup(self, reason: str = "manual") -> dict[str, Any]:
        if not self.db_path.exists():
            raise LibraryError("数据库尚不存在，无法备份")
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        safe_reason = re.sub(r"[^a-zA-Z0-9_-]+", "-", reason).strip("-") or "backup"
        target = self.backups_dir / f"{stamp}-{safe_reason}.db"
        destination = sqlite3.connect(target)
        try:
            self.conn.backup(destination)
        finally:
            destination.close()
        keep = max(1, int(self.settings.get("backup_keep", 25)))
        backups = sorted(self.backups_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[keep:]:
            old.unlink()
        return {"status": "ok", "backup": str(target), "kept": min(len(backups), keep)}

    @staticmethod
    def _features(text: str) -> set[str]:
        normalized = re.sub(r"\s+", "", text.casefold())
        chunks = set(re.findall(r"[a-z0-9]+|[\u3400-\u9fff]", normalized))
        chunks.update(normalized[i:i + 2] for i in range(max(0, len(normalized) - 1)))
        return {x for x in chunks if x}

    @classmethod
    def similarity(cls, left: dict[str, Any], right: dict[str, Any]) -> float:
        a_prompt = re.sub(r"\s+", "", left.get("prompt_text", "").casefold())
        b_prompt = re.sub(r"\s+", "", right.get("prompt_text", "").casefold())
        prompt_seq = difflib.SequenceMatcher(None, a_prompt, b_prompt).ratio()
        a_text = " ".join([left.get("name", ""), left.get("prompt_text", "")])
        b_text = " ".join([right.get("name", ""), right.get("prompt_text", "")])
        seq = difflib.SequenceMatcher(None, re.sub(r"\s+", "", a_text.casefold()),
                                      re.sub(r"\s+", "", b_text.casefold())).ratio()
        a_set, b_set = cls._features(a_text), cls._features(b_text)
        jac = len(a_set & b_set) / len(a_set | b_set) if a_set | b_set else 0.0
        a_tags, b_tags = set(split_list(left.get("tags"))), set(split_list(right.get("tags")))
        tag_score = len(a_tags & b_tags) / len(a_tags | b_tags) if a_tags | b_tags else 0.0
        return round(max(prompt_seq, seq, 0.65 * prompt_seq + 0.25 * jac + 0.10 * tag_score), 4)

    def duplicates(self, candidate: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM prompts WHERE deleted_at IS NULL").fetchall()
        candidate_tags = set(split_list(candidate.get("tags")))
        narrowed: list[sqlite3.Row] = []
        for row in rows:
            tags = set(parse_json_list(row["tags"]))
            same_category = candidate.get("category") and row["category"] == candidate.get("category")
            if same_category or candidate_tags & tags or not candidate.get("category"):
                narrowed.append(row)
        scored = []
        for row in narrowed:
            decoded = self.decode_row(row)
            score = self.similarity(candidate, decoded)
            if score >= 0.45:
                scored.append({"id": row["id"], "name": row["name"], "similarity": score})
        return sorted(scored, key=lambda x: x["similarity"], reverse=True)[:limit]

    def add(self, data: dict[str, Any], duplicate_action: str = "check") -> dict[str, Any]:
        if not str(data.get("name", "")).strip():
            raise LibraryError("缺少名称：--name")
        if not str(data.get("prompt_text", "")).strip():
            raise LibraryError("缺少完整 Prompt：--prompt-text")
        clean = {
            "name": str(data["name"]).strip(),
            "category": str(data.get("category") or "其他").strip(),
            "subcategory": str(data.get("subcategory") or "").strip(),
            "tags": split_list(data.get("tags")),
            "suitable_for": split_list(data.get("suitable_for")),
            "avoid_when": split_list(data.get("avoid_when")),
            "strengths": split_list(data.get("strengths")),
            "prompt_text": str(data["prompt_text"]).strip(),
            "notes": str(data.get("notes") or "").strip(),
        }
        source_type = str(data.get("source_type") or "manual").strip()
        if source_type not in SOURCE_TYPES:
            raise LibraryError(f"不支持的来源类型：{source_type}")
        parent_id = data.get("parent_prompt_id")
        parent_version = data.get("parent_prompt_version")
        if parent_id:
            parent = self.get(str(parent_id))
            parent_id = parent["id"]
            parent_version = int(parent_version or parent["version"])
            self.version_get(parent_id, parent_version)
            source_type = "derived"
        provenance = {
            "source_type": source_type,
            "source_ref": str(data.get("source_ref") or "").strip() or None,
            "source_note": str(data.get("source_note") or "").strip() or None,
            "parent_prompt_id": parent_id,
            "parent_prompt_version": parent_version,
            "origin_temporary_id": data.get("origin_temporary_id"),
        }
        matches = self.duplicates(clean)
        threshold = float(self.settings.get("duplicate_threshold", 0.85))
        strong = [item for item in matches if item["similarity"] >= threshold]
        if strong and duplicate_action == "check":
            return {"status": "duplicate_found", "candidates": strong, "proposed": clean}
        if strong and duplicate_action in {"merge", "replace"}:
            target = strong[0]["id"]
            if duplicate_action == "replace":
                result = self.update(target, clean, event_type="replace")
                result["duplicate_similarity"] = strong[0]["similarity"]
                return result
            # Add a temporary stable record then use the ordinary merge path.
            created = self._insert(clean, event_type="add_for_merge", provenance=provenance)
            return self.merge(target, created["prompt"]["id"])
        result = self._insert(clean, provenance=provenance)
        result["similar_candidates"] = matches
        return result

    def _insert(self, clean: dict[str, Any], event_type: str = "add",
                provenance: dict[str, Any] | None = None) -> dict[str, Any]:
        timestamp = now()
        provenance = provenance or {"source_type": "manual"}
        with self.conn:
            prompt_id = self._next_id()
            self.conn.execute(
                """INSERT INTO prompts(
                    id,name,category,subcategory,tags,suitable_for,avoid_when,strengths,
                    prompt_text,notes,created_at,updated_at,source_type,source_ref,source_note,
                    parent_prompt_id,parent_prompt_version,origin_temporary_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (prompt_id, clean["name"], clean["category"], clean["subcategory"],
                 json_text(clean["tags"]), json_text(clean["suitable_for"]),
                 json_text(clean["avoid_when"]), json_text(clean["strengths"]),
                 clean["prompt_text"], clean["notes"], timestamp, timestamp,
                 provenance.get("source_type", "manual"), provenance.get("source_ref"),
                 provenance.get("source_note"), provenance.get("parent_prompt_id"),
                 provenance.get("parent_prompt_version"), provenance.get("origin_temporary_id")),
            )
            self._insert_version_snapshot(prompt_id, 1, clean["prompt_text"], "创建正式 Prompt")
            self._history(prompt_id, event_type, {"version": 1})
        backup = self.backup(event_type)
        return {"status": "created", "prompt": self.get(prompt_id), "backup": backup["backup"]}

    def update(self, prompt_id: str, changes: dict[str, Any], event_type: str = "update") -> dict[str, Any]:
        prompt_id = normalize_id(prompt_id)
        before = self.get(prompt_id)
        assignments, values = [], []
        recorded: dict[str, Any] = {}
        for field in EDITABLE_FIELDS:
            if field not in changes or changes[field] is None:
                continue
            value = changes[field]
            if field in JSON_FIELDS:
                value = json_text(value)
                recorded[field] = parse_json_list(value)
            else:
                value = str(value).strip()
                if field in {"name", "prompt_text"} and not value:
                    raise LibraryError(f"{field} 不能为空")
                recorded[field] = value
            assignments.append(f"{field}=?")
            values.append(value)
        if not assignments:
            raise LibraryError("没有提供可修改字段")
        changes_prompt = "prompt_text" in recorded and recorded["prompt_text"] != before["prompt_text"]
        new_version = before["version"] + 1 if changes_prompt else before["version"]
        assignments.append("updated_at=?")
        values.append(now())
        if changes_prompt:
            assignments.append("version=?")
            values.append(new_version)
        values.append(prompt_id)
        with self.conn:
            self.conn.execute(f"UPDATE prompts SET {','.join(assignments)} WHERE id=?", values)
            if changes_prompt:
                self._insert_version_snapshot(
                    prompt_id, new_version, recorded["prompt_text"],
                    str(changes.get("change_note") or "Prompt 正文更新"),
                )
            self._history(prompt_id, event_type, {
                "changes": recorded, "previous_version": before["version"],
                "new_version": new_version, "version_created": changes_prompt,
            })
        backup = self.backup(event_type)
        return {"status": "updated", "prompt": self.get(prompt_id), "backup": backup["backup"]}

    def list_prompts(self, category: str | None = None, include_disabled: bool = False,
                     limit: int = 100) -> dict[str, Any]:
        clauses, params = [], []
        if category:
            clauses.append("category=?")
            params.append(category)
        if not include_disabled:
            clauses.append("disabled=0")
        clauses.append("deleted_at IS NULL")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM prompts{where} ORDER BY category,name,id LIMIT ?", (*params, limit)
        ).fetchall()
        return {"status": "ok", "count": len(rows),
                "prompts": [self.decode_row(r, include_prompt=False) for r in rows]}

    def stats(self) -> dict[str, Any]:
        total = self.conn.execute("SELECT COUNT(*) FROM prompts WHERE deleted_at IS NULL").fetchone()[0]
        active = self.conn.execute("SELECT COUNT(*) FROM prompts WHERE disabled=0 AND deleted_at IS NULL").fetchone()[0]
        trash = self.conn.execute("SELECT COUNT(*) FROM prompts WHERE deleted_at IS NOT NULL").fetchone()[0]
        categories = [dict(r) for r in self.conn.execute(
            "SELECT category,COUNT(*) AS count FROM prompts WHERE disabled=0 AND deleted_at IS NULL GROUP BY category ORDER BY count DESC,category"
        )]
        totals = self.conn.execute(
            "SELECT COALESCE(SUM(use_count),0),COALESCE(SUM(positive_count),0),"
            "COALESCE(SUM(negative_count),0) FROM prompts WHERE deleted_at IS NULL"
        ).fetchone()
        integrity = self.conn.execute("PRAGMA integrity_check").fetchone()[0]
        versions = self.conn.execute("SELECT COUNT(*) FROM prompt_versions").fetchone()[0]
        runs = self.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        success_runs = self.conn.execute("SELECT COUNT(*) FROM runs WHERE status='success'").fetchone()[0]
        failed_runs = self.conn.execute("SELECT COUNT(*) FROM runs WHERE status='failed'").fetchone()[0]
        missing_versions = self.conn.execute(
            """SELECT COUNT(*) FROM prompts p WHERE NOT EXISTS
               (SELECT 1 FROM prompt_versions v WHERE v.prompt_id=p.id)"""
        ).fetchone()[0]
        orphan_versions = self.conn.execute(
            """SELECT COUNT(*) FROM prompt_versions v
               LEFT JOIN prompts p ON p.id=v.prompt_id WHERE p.id IS NULL"""
        ).fetchone()[0]
        orphan_runs = self.conn.execute(
            """SELECT COUNT(*) FROM runs r
               LEFT JOIN prompts p ON p.id=r.prompt_id
               LEFT JOIN temporary_prompts t ON t.temp_id=r.temporary_prompt_id
               WHERE (r.prompt_id IS NOT NULL AND p.id IS NULL)
                  OR (r.temporary_prompt_id IS NOT NULL AND t.temp_id IS NULL)"""
        ).fetchone()[0]
        aggregate_warnings = sum(1 for item in self.stats_check()["checks"] if not item["ok"])
        return {"status": "ok", "database_status": integrity, "database": str(self.db_path),
                "total": total, "active": active, "disabled": total - active,
                "total_use_count": totals[0], "total_positive_count": totals[1],
                "total_negative_count": totals[2], "categories": categories,
                "schema_version": SCHEMA_VERSION, "prompt_versions": versions, "runs": runs,
                "successful_runs": success_runs, "failed_runs": failed_runs, "trash": trash,
                "orphan_versions": orphan_versions, "orphan_runs": orphan_runs,
                "prompts_without_versions": missing_versions, "aggregate_warnings": aggregate_warnings,
                "legacy_aggregate_info": self.conn.execute(
                    "SELECT COUNT(*) FROM prompts WHERE legacy_use_count>0 OR legacy_positive_count>0 OR legacy_negative_count>0"
                ).fetchone()[0]}

    def search(self, query: str, limit: int = 20, include_disabled: bool = False) -> dict[str, Any]:
        terms = query_terms(query)
        if not terms:
            raise LibraryError("搜索词不能为空")
        rows = self.conn.execute(
            "SELECT * FROM prompts WHERE deleted_at IS NULL" + ("" if include_disabled else " AND disabled=0")
        ).fetchall()
        scored = []
        for row in rows:
            decoded = self.decode_row(row)
            fields = [decoded.get("name", ""), decoded.get("category", ""),
                      decoded.get("subcategory", ""), decoded.get("prompt_text", ""),
                      decoded.get("notes", "")] + sum((decoded[f] for f in JSON_FIELDS), [])
            haystack = " ".join(map(str, fields)).casefold()
            hits = sum(haystack.count(term) for term in terms)
            if hits:
                score = hits + sum(2 for term in terms if term in decoded["name"].casefold())
                item = self.decode_row(row, include_prompt=False)
                item["search_score"] = score
                scored.append(item)
        scored.sort(key=lambda x: (-x["search_score"], -x["preference_weight"], x["id"]))
        return {"status": "ok", "query": query, "count": min(len(scored), limit),
                "results": scored[:limit]}

    def candidates(self, category: str | None, subcategory: str | None, tags: Any,
                   query: str | None, limit: int = 12) -> dict[str, Any]:
        wanted_tags = set(split_list(tags))
        terms = query_terms(query or "")
        rows = self.conn.execute("SELECT * FROM prompts WHERE disabled=0 AND deleted_at IS NULL").fetchall()
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            item = self.decode_row(row)
            score = 0.0
            if category:
                if item["category"].casefold() == category.casefold():
                    score += 40
                else:
                    score -= 12
            if subcategory:
                score += 20 if item["subcategory"].casefold() == subcategory.casefold() else 0
            overlap = wanted_tags & set(item["tags"] + item["suitable_for"] + item["strengths"])
            score += 12 * len(overlap)
            text = " ".join([item["name"], item["category"], item["subcategory"], item["prompt_text"]]
                            + item["tags"] + item["suitable_for"] + item["strengths"]).casefold()
            score += 4 * sum(1 for term in terms if term in text)
            avoid_text = " ".join(item["avoid_when"]).casefold()
            avoid_hits = sum(1 for term in terms if term and term in avoid_text)
            score -= 35 * avoid_hits
            # Preference/history are deliberately small tie-breakers; image fit is decided by the model.
            score += max(-5, min(5, float(item["preference_weight"])))
            score += min(3, math.log1p(item["use_count"]))
            if category or subcategory or wanted_tags or terms:
                if score <= 0:
                    continue
            item["candidate_score"] = round(score, 3)
            scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
        return {"status": "ok", "count": min(len(scored), limit),
                "candidates": [item for _, item in scored[:limit]]}

    def use(self, prompt_id: str, context: str | None = None) -> dict[str, Any]:
        before = self.get(prompt_id)
        started = self.run_start(prompt_id, context, "legacy-use", None)
        completed = self.run_complete(started["run"]["run_id"])
        after = self.get(prompt_id)
        return {"status": "used", "event_id": completed["event_id"],
                "run": completed["run"], "use_count_before": before["use_count"],
                "use_count_after": after["use_count"], "prompt": after,
                "backup": completed["backup"]}

    def undo_use(self, prompt_id: str | None = None) -> dict[str, Any]:
        params: list[Any] = []
        clause = ""
        if prompt_id:
            prompt_id = normalize_id(prompt_id)
            self._row(prompt_id)
            clause = " AND prompt_id=?"
            params.append(prompt_id)
        row = self.conn.execute(
            "SELECT * FROM runs WHERE status='success'" + clause +
            " ORDER BY COALESCE(completed_at,started_at) DESC,run_id DESC LIMIT 1", params
        ).fetchone()
        if row is None:
            raise LibraryError("没有可撤回的使用记录")
        target = row["prompt_id"]
        with self.conn:
            if target:
                current = self._row(target)["use_count"]
                if current <= 0:
                    raise LibraryError("使用次数已经是 0，无法撤回")
                pos = 1 if row["feedback"] == "positive" else 0
                neg = 1 if row["feedback"] in {"negative", "never"} else 0
                self.conn.execute(
                    """UPDATE prompts SET use_count=use_count-1,
                       positive_count=MAX(0,positive_count-?),negative_count=MAX(0,negative_count-?),
                       updated_at=? WHERE id=?""", (pos, neg, now(), target)
                )
            else:
                temp_id = row["temporary_prompt_id"]
                self.conn.execute(
                    "UPDATE temporary_prompts SET use_count=MAX(0,use_count-1),updated_at=? WHERE temp_id=?",
                    (now(), temp_id),
                )
            self.conn.execute(
                "UPDATE runs SET status='cancelled',error_summary='use undone' WHERE run_id=?", (row["run_id"],)
            )
            event_id = self._history(target, "use_undo", -1, {"run_id": row["run_id"]})
        result = {"status": "use_undone", "event_id": event_id, "run_id": row["run_id"]}
        if target:
            result["prompt"] = self.get(target)
        return result

    def feedback(self, prompt_id: str, kind: str, context: str | None = None) -> dict[str, Any]:
        prompt_id = normalize_id(prompt_id)
        before = self.get(prompt_id)
        mapping = {
            "positive": (1, 0, 0.5, 0),
            "neutral": (0, 0, -0.25, 0),
            "negative": (0, 1, -1.0, 0),
            "never": (0, 1, -5.0, 1),
        }
        pos, neg, delta, disabled = mapping[kind]
        with self.conn:
            self.conn.execute(
                """UPDATE prompts SET positive_count=positive_count+?,negative_count=negative_count+?,
                   legacy_positive_count=legacy_positive_count+?,legacy_negative_count=legacy_negative_count+?,
                   preference_weight=preference_weight+?,disabled=MAX(disabled,?),updated_at=? WHERE id=?""",
                (pos, neg, pos, neg, delta, disabled, now(), prompt_id),
            )
            self._history(prompt_id, f"{kind}_feedback", {"preference_delta": delta}, context)
        after = self.get(prompt_id)
        return {"status": "feedback_recorded", "feedback": kind,
                "positive_count_before": before["positive_count"],
                "positive_count_after": after["positive_count"],
                "negative_count_before": before["negative_count"],
                "negative_count_after": after["negative_count"],
                "preference_weight_before": before["preference_weight"],
                "preference_weight_after": after["preference_weight"],
                "prompt": after}

    def rate(self, prompt_id: str, rating: float, context: str | None = None) -> dict[str, Any]:
        if not 1 <= rating <= 5:
            raise LibraryError("评分必须在 1 到 5 之间")
        prompt_id = normalize_id(prompt_id)
        self._row(prompt_id)
        with self.conn:
            self.conn.execute("UPDATE prompts SET user_rating=?,updated_at=? WHERE id=?", (rating, now(), prompt_id))
            self._history(prompt_id, "rating", rating, context)
        return {"status": "rated", "prompt": self.get(prompt_id)}

    def preference(self, prompt_id: str, delta: float, context: str | None = None) -> dict[str, Any]:
        if not -20 <= delta <= 20:
            raise LibraryError("单次偏好调整必须在 -20 到 20 之间")
        prompt_id = normalize_id(prompt_id)
        self._row(prompt_id)
        with self.conn:
            self.conn.execute(
                "UPDATE prompts SET preference_weight=preference_weight+?,updated_at=? WHERE id=?",
                (delta, now(), prompt_id),
            )
            self._history(prompt_id, "preference", delta, context)
        return {"status": "preference_updated", "prompt": self.get(prompt_id)}

    def set_flag(self, prompt_id: str, field: str, value: bool) -> dict[str, Any]:
        if field not in {"disabled", "favorite"}:
            raise LibraryError("不支持的标记字段")
        prompt_id = normalize_id(prompt_id)
        self._row(prompt_id)
        with self.conn:
            self.conn.execute(f"UPDATE prompts SET {field}=?,updated_at=? WHERE id=?", (int(value), now(), prompt_id))
            self._history(prompt_id, field, int(value))
        return {"status": "updated", "prompt": self.get(prompt_id)}

    def delete(self, prompt_id: str, confirmed: bool) -> dict[str, Any]:
        prompt_id = normalize_id(prompt_id)
        row = self.get(prompt_id)
        if not confirmed:
            raise LibraryError("永久删除需要明确确认：重新运行并添加 --confirm；也可先使用 disable")
        pre = self.backup("before-delete")
        with self.conn:
            self._history(prompt_id, "delete", {"id": prompt_id, "name": row["name"]})
            self.conn.execute("DELETE FROM prompts WHERE id=?", (prompt_id,))
        post = self.backup("delete")
        return {"status": "deleted", "id": prompt_id, "backup_before": pre["backup"],
                "backup_after": post["backup"]}

    def merge(self, target_id: str, source_id: str) -> dict[str, Any]:
        target_id, source_id = normalize_id(target_id), normalize_id(source_id)
        if target_id == source_id:
            raise LibraryError("不能把 Prompt 与自身合并")
        target, source = self.get(target_id), self.get(source_id)
        pre = self.backup("before-merge")
        total_uses = target["use_count"] + source["use_count"]
        ratings = [(target["user_rating"], max(1, target["use_count"])),
                   (source["user_rating"], max(1, source["use_count"]))]
        present = [(r, w) for r, w in ratings if r is not None]
        rating = round(sum(r * w for r, w in present) / sum(w for _, w in present), 3) if present else None
        merged_lists = {f: json_text(target[f] + source[f]) for f in JSON_FIELDS}
        note_addition = f"\n\n[Merged from {source_id} v{source['version']}]\n{source['prompt_text']}"
        preference = max((target["preference_weight"], source["preference_weight"]), key=abs)
        with self.conn:
            self.conn.execute(
                """UPDATE prompts SET tags=?,suitable_for=?,avoid_when=?,strengths=?,notes=?,
                   use_count=?,positive_count=?,negative_count=?,user_rating=?,preference_weight=?,
                   favorite=?,disabled=?,last_used_at=?,updated_at=?,
                   legacy_use_count=?,legacy_positive_count=?,legacy_negative_count=? WHERE id=?""",
                (merged_lists["tags"], merged_lists["suitable_for"], merged_lists["avoid_when"],
                 merged_lists["strengths"], target["notes"] + note_addition, total_uses,
                 target["positive_count"] + source["positive_count"],
                 target["negative_count"] + source["negative_count"], rating, preference,
                 int(target["favorite"] or source["favorite"]),
                 int(target["disabled"] and source["disabled"]),
                 max(filter(None, [target["last_used_at"], source["last_used_at"]]), default=None),
                 now(), target["legacy_use_count"] + source["legacy_use_count"],
                 target["legacy_positive_count"] + source["legacy_positive_count"],
                 target["legacy_negative_count"] + source["legacy_negative_count"], target_id),
            )
            self.conn.execute("UPDATE history SET prompt_id=? WHERE prompt_id=?", (target_id, source_id))
            self.conn.execute(
                "UPDATE runs SET prompt_id=?,prompt_version=? WHERE prompt_id=?",
                (target_id, target["version"], source_id),
            )
            self._history(target_id, "merge", {"source_id": source_id, "source": source})
            self.conn.execute("DELETE FROM prompts WHERE id=?", (source_id,))
        post = self.backup("merge")
        return {"status": "merged", "prompt": self.get(target_id), "source_id": source_id,
                "backup_before": pre["backup"], "backup_after": post["backup"]}

    def recommend(self, scores: dict[str, float], image_context: str = "",
                  show_all: bool = False, force_temporary: bool = False) -> dict[str, Any]:
        """Apply quality gates to model-supplied image-fit scores using real DB statistics."""
        context_text = image_context.casefold()
        context_terms = set(query_terms(image_context))
        ranked: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        missing: list[str] = []
        for prompt_id, score in scores.items():
            try:
                prompt = self.get(prompt_id)
            except LibraryError:
                missing.append(prompt_id)
                continue
            avoid_conflicts = []
            for phrase in prompt["avoid_when"]:
                phrase_terms = set(query_terms(phrase))
                overlap = len(phrase_terms & context_terms)
                if phrase.casefold() in context_text or (
                    phrase_terms and overlap >= max(1, math.ceil(len(phrase_terms) * 0.6))
                ):
                    avoid_conflicts.append(phrase)
            item = {
                "prompt_id": prompt["id"], "name": prompt["name"],
                "match_score": round(float(score), 2), "use_count": prompt["use_count"],
                "positive_count": prompt["positive_count"],
                "negative_count": prompt["negative_count"],
                "user_rating": prompt["user_rating"],
                "preference_weight": prompt["preference_weight"],
                "last_used_at": prompt["last_used_at"],
                "avoid_conflicts": avoid_conflicts,
            }
            if prompt.get("deleted_at"):
                item["excluded_reason"] = "trashed"
                excluded.append(item)
                continue
            if prompt["disabled"]:
                item["excluded_reason"] = "disabled"
                excluded.append(item)
                continue
            if avoid_conflicts:
                item["excluded_reason"] = "avoid_when"
                excluded.append(item)
                continue
            if score >= HIGH_MATCH_THRESHOLD:
                item["match_tier"] = "high"
                ranked.append(item)
            elif score >= MIN_MATCH_THRESHOLD:
                item["match_tier"] = "usable"
                ranked.append(item)
            else:
                item["match_tier"] = "low"
                item["excluded_reason"] = "below_minimum_match"
                excluded.append(item)
        ranked.sort(key=lambda item: (-item["match_score"], item["prompt_id"]))
        excluded.sort(key=lambda item: (-item["match_score"], item["prompt_id"]))
        highest = ranked[0]["match_score"] if ranked else max(
            (item["match_score"] for item in excluded if item.get("excluded_reason") == "below_minimum_match"),
            default=None,
        )
        has_high = any(item["match_tier"] == "high" for item in ranked)
        needs_temporary = force_temporary or not has_high
        if has_high and not force_temporary:
            coverage = "sufficient"
        elif ranked:
            coverage = "coverage_gap"
        else:
            coverage = "no_match"
        result = {
            "status": "ok", "coverage": coverage,
            "thresholds": {"high": HIGH_MATCH_THRESHOLD, "minimum": MIN_MATCH_THRESHOLD},
            "recommended": ranked, "recommended_count": len(ranked),
            "needs_temporary_prompt": needs_temporary,
            "temporary_priority": "first" if highest is None or highest < 50 else "after_existing",
            "highest_match_score": highest, "missing_prompt_ids": missing,
            "excluded_count": len(excluded),
        }
        if show_all:
            result["excluded"] = excluded
        return result

    @staticmethod
    def decode_run(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = dict(row)
        try:
            data["image_context"] = json.loads(data.get("image_context") or "{}")
        except json.JSONDecodeError:
            data["image_context"] = {"summary": data.get("image_context")}
        return data

    def _run_row(self, run_id: str) -> sqlite3.Row:
        run_id = normalize_run_id(run_id)
        row = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise LibraryError(f"未找到 Run：{run_id}")
        return row

    def run_get(self, run_id: str) -> dict[str, Any]:
        return self.decode_run(self._run_row(run_id))

    def run_start(self, target_id: str, image_context: Any = None, executor: str = "unknown",
                  model: str | None = None, prompt_snapshot: str | None = None) -> dict[str, Any]:
        target_id = target_id.strip().upper()
        prompt_id: str | None = None
        prompt_version: int | None = None
        temporary_id: str | None = None
        if target_id.startswith("P"):
            prompt = self.get(target_id)
            if prompt.get("deleted_at"):
                raise LibraryError(f"Prompt {target_id} 在回收站中，不能执行")
            prompt_id = prompt["id"]
            prompt_version = int(prompt["version"])
            actual_prompt = prompt_snapshot or prompt["prompt_text"]
        elif target_id.startswith("T"):
            temporary = self.get_temporary(target_id)
            if temporary["status"] in {"saved", "discarded"}:
                raise LibraryError(f"临时 Prompt {target_id} 已是 {temporary['status']} 状态，不能执行")
            temporary_id = temporary["temp_id"]
            actual_prompt = prompt_snapshot or temporary["prompt_text"]
        else:
            raise LibraryError("Run 目标必须是 Pxxx 或 Txxx")
        timestamp = now()
        with self.conn:
            run_id = self._next_run_id()
            self.conn.execute(
                """INSERT INTO runs(run_id,prompt_id,prompt_version,temporary_prompt_id,image_context,
                   prompt_snapshot,executor,model,status,started_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (run_id, prompt_id, prompt_version, temporary_id, compact_json(image_context),
                 actual_prompt, executor or "unknown", model, "running", timestamp),
            )
            self._history(prompt_id, "run_started", run_id, {
                "temporary_prompt_id": temporary_id, "prompt_version": prompt_version,
                "executor": executor or "unknown", "model": model,
            })
        return {"status": "run_started", "run": self.run_get(run_id)}

    def run_complete(self, run_id: str, result_ref: str | None = None,
                     result_path: str | None = None) -> dict[str, Any]:
        before = self._run_row(run_id)
        if before["status"] != "running":
            raise LibraryError(f"Run {run_id} 当前状态为 {before['status']}，不能标记成功")
        timestamp = now()
        with self.conn:
            self.conn.execute(
                """UPDATE runs SET status='success',result_ref=?,result_path=?,completed_at=?
                   WHERE run_id=?""", (result_ref, result_path, timestamp, run_id)
            )
            if before["prompt_id"]:
                self.conn.execute(
                    """UPDATE prompts SET use_count=use_count+1,last_used_at=?,updated_at=?
                       WHERE id=?""", (timestamp, timestamp, before["prompt_id"])
                )
            else:
                self.conn.execute(
                    """UPDATE temporary_prompts SET use_count=use_count+1,status='used',
                       last_used_at=?,updated_at=? WHERE temp_id=?""",
                    (timestamp, timestamp, before["temporary_prompt_id"]),
                )
            event_id = self._history(before["prompt_id"], "run_success", run_id, {
                "temporary_prompt_id": before["temporary_prompt_id"],
                "prompt_version": before["prompt_version"], "result_ref": result_ref,
                "result_path": result_path,
            })
        backup = self.backup("run-success")
        return {"status": "run_success", "event_id": event_id,
                "run": self.run_get(run_id), "backup": backup["backup"]}

    def run_fail(self, run_id: str, error_summary: str, result_ref: str | None = None) -> dict[str, Any]:
        before = self._run_row(run_id)
        if before["status"] != "running":
            raise LibraryError(f"Run {run_id} 当前状态为 {before['status']}，不能标记失败")
        with self.conn:
            self.conn.execute(
                """UPDATE runs SET status='failed',error_summary=?,result_ref=?,completed_at=?
                   WHERE run_id=?""", (error_summary.strip(), result_ref, now(), run_id)
            )
            self._history(before["prompt_id"], "run_failed", run_id, {
                "temporary_prompt_id": before["temporary_prompt_id"], "error_summary": error_summary,
            })
        return {"status": "run_failed", "run": self.run_get(run_id)}

    @staticmethod
    def _feedback_effect(kind: str | None) -> tuple[int, int, float, int]:
        mapping = {
            None: (0, 0, 0.0, 0), "positive": (1, 0, 0.5, 0),
            "neutral": (0, 0, -0.25, 0), "negative": (0, 1, -1.0, 0),
            "never": (0, 1, -5.0, 1),
        }
        return mapping[kind]

    def run_feedback(self, run_id: str, kind: str, context: str | None = None) -> dict[str, Any]:
        if kind not in RUN_FEEDBACK:
            raise LibraryError("Run 反馈仅支持 positive、neutral、negative、never")
        before = self._run_row(run_id)
        if before["status"] != "success":
            raise LibraryError("只有成功 Run 才能记录效果反馈")
        old_pos, old_neg, old_delta, _ = self._feedback_effect(before["feedback"])
        new_pos, new_neg, new_delta, disabled = self._feedback_effect(kind)
        if before["prompt_id"]:
            aggregate_before = self.get(before["prompt_id"])
        else:
            aggregate_before = self.get_temporary(before["temporary_prompt_id"])
        with self.conn:
            self.conn.execute(
                "UPDATE runs SET feedback=?,feedback_at=? WHERE run_id=?", (kind, now(), run_id)
            )
            if before["prompt_id"]:
                self.conn.execute(
                    """UPDATE prompts SET positive_count=MAX(0,positive_count+?),
                       negative_count=MAX(0,negative_count+?),preference_weight=preference_weight+?,
                       disabled=MAX(disabled,?),updated_at=? WHERE id=?""",
                    (new_pos - old_pos, new_neg - old_neg, new_delta - old_delta,
                     disabled, now(), before["prompt_id"]),
                )
            else:
                if kind == "never":
                    kind = "negative"
                    new_pos, new_neg, _, _ = self._feedback_effect(kind)
                self.conn.execute(
                    """UPDATE temporary_prompts SET positive_count=MAX(0,positive_count+?),
                       negative_count=MAX(0,negative_count+?),updated_at=? WHERE temp_id=?""",
                    (new_pos - old_pos, new_neg - old_neg, now(), before["temporary_prompt_id"]),
                )
            self._history(before["prompt_id"], "run_feedback", {"run_id": run_id, "feedback": kind}, context)
        result = {"status": "run_feedback_recorded", "run": self.run_get(run_id),
                  "feedback_before": before["feedback"], "feedback_after": kind}
        if before["prompt_id"]:
            aggregate_after = self.get(before["prompt_id"])
            result["prompt"] = aggregate_after
            result["preference_weight_before"] = aggregate_before["preference_weight"]
            result["preference_weight_after"] = aggregate_after["preference_weight"]
        else:
            aggregate_after = self.get_temporary(before["temporary_prompt_id"])
            result["temporary_prompt"] = aggregate_after
        result.update({
            "positive_count_before": aggregate_before["positive_count"],
            "positive_count_after": aggregate_after["positive_count"],
            "negative_count_before": aggregate_before["negative_count"],
            "negative_count_after": aggregate_after["negative_count"],
        })
        return result

    def run_list(self, prompt_id: str | None = None, limit: int = 20,
                 status: str | None = None) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if prompt_id:
            prompt_id = normalize_id(prompt_id)
            clauses.append("prompt_id=?")
            params.append(prompt_id)
        if status:
            if status not in RUN_STATUSES:
                raise LibraryError(f"不支持的 Run 状态：{status}")
            clauses.append("status=?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.conn.execute(
            "SELECT * FROM runs" + where + " ORDER BY started_at DESC,run_id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return {"status": "ok", "count": len(rows), "runs": [self.decode_run(r) for r in rows]}

    @staticmethod
    def decode_temporary(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = dict(row)
        for field in JSON_FIELDS:
            data[field] = parse_json_list(data.get(field))
        return data

    def _temporary_row(self, temp_id: str) -> sqlite3.Row:
        temp_id = normalize_temp_id(temp_id)
        row = self.conn.execute(
            "SELECT * FROM temporary_prompts WHERE temp_id=?", (temp_id,)
        ).fetchone()
        if row is None:
            raise LibraryError(f"未找到临时 Prompt：{temp_id}")
        return row

    def get_temporary(self, temp_id: str) -> dict[str, Any]:
        return self.decode_temporary(self._temporary_row(temp_id))

    def create_temporary(self, data: dict[str, Any], image_context: str = "") -> dict[str, Any]:
        if not str(data.get("name", "")).strip():
            raise LibraryError("临时方案缺少名称：--name")
        if not str(data.get("prompt_text", "")).strip():
            raise LibraryError("临时方案缺少完整 Prompt：--prompt-text")
        timestamp = now()
        with self.conn:
            temp_id = self._next_temp_id()
            self.conn.execute(
                """INSERT INTO temporary_prompts(
                   temp_id,name,category,subcategory,tags,suitable_for,avoid_when,strengths,
                   prompt_text,notes,image_context,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (temp_id, str(data["name"]).strip(), str(data.get("category") or "其他").strip(),
                 str(data.get("subcategory") or "").strip(), json_text(data.get("tags")),
                 json_text(data.get("suitable_for")), json_text(data.get("avoid_when")),
                 json_text(data.get("strengths")), str(data["prompt_text"]).strip(),
                 str(data.get("notes") or "").strip(), image_context, timestamp, timestamp),
            )
            self._history(None, "temporary_created", {"temp_id": temp_id}, {"image_context": image_context})
        return {"status": "temporary_created", "temporary_prompt": self.get_temporary(temp_id)}

    def use_temporary(self, temp_id: str, context: str | None = None) -> dict[str, Any]:
        before = self.get_temporary(temp_id)
        started = self.run_start(temp_id, context, "legacy-temporary-use", None)
        completed = self.run_complete(started["run"]["run_id"])
        after = self.get_temporary(temp_id)
        return {"status": "temporary_used", "event_id": completed["event_id"],
                "run": completed["run"],
                "use_count_before": before["use_count"], "use_count_after": after["use_count"],
                "temporary_prompt": after}

    def feedback_temporary(self, temp_id: str, kind: str, context: str | None = None) -> dict[str, Any]:
        if kind not in {"positive", "neutral", "negative"}:
            raise LibraryError("临时 Prompt 反馈仅支持 positive、neutral、negative")
        before = self.get_temporary(temp_id)
        if before["status"] == "saved" and before["formal_prompt_id"]:
            return self.feedback(before["formal_prompt_id"], kind, context)
        if before["status"] == "discarded":
            raise LibraryError("已丢弃的临时 Prompt 不能记录反馈")
        if before["use_count"] <= 0:
            raise LibraryError("临时 Prompt 尚未实际使用，不能记录效果反馈")
        pos = 1 if kind == "positive" else 0
        neg = 1 if kind == "negative" else 0
        with self.conn:
            self.conn.execute(
                """UPDATE temporary_prompts SET positive_count=positive_count+?,
                   negative_count=negative_count+?,updated_at=? WHERE temp_id=?""",
                (pos, neg, now(), temp_id),
            )
            self._history(None, f"temporary_{kind}_feedback", None,
                          {"temp_id": temp_id, "context": context})
        after = self.get_temporary(temp_id)
        return {"status": "temporary_feedback_recorded", "feedback": kind,
                "positive_count_before": before["positive_count"],
                "positive_count_after": after["positive_count"],
                "negative_count_before": before["negative_count"],
                "negative_count_after": after["negative_count"],
                "temporary_prompt": after}

    def save_temporary(self, temp_id: str, duplicate_action: str = "check") -> dict[str, Any]:
        temporary = self.get_temporary(temp_id)
        if temporary["status"] == "saved":
            raise LibraryError(f"临时 Prompt 已收藏为 {temporary['formal_prompt_id']}")
        if temporary["status"] == "discarded":
            raise LibraryError("已丢弃的临时 Prompt 不能收藏")
        clean = {field: temporary[field] for field in EDITABLE_FIELDS}
        matches = self.duplicates(clean)
        threshold = float(self.settings.get("duplicate_threshold", 0.85))
        strong = [item for item in matches if item["similarity"] >= threshold]
        if strong and duplicate_action == "check":
            return {"status": "duplicate_found", "temporary_id": temp_id,
                    "candidates": strong, "proposed": clean}
        target_id = strong[0]["id"] if strong and duplicate_action in {"merge", "replace"} else None
        timestamp = now()
        preference_delta = 0.5 * temporary["positive_count"] - temporary["negative_count"]
        run_totals = self.conn.execute(
            """SELECT COUNT(*) AS uses,
               SUM(CASE WHEN feedback='positive' THEN 1 ELSE 0 END) AS positives,
               SUM(CASE WHEN feedback IN ('negative','never') THEN 1 ELSE 0 END) AS negatives
               FROM runs WHERE temporary_prompt_id=? AND status='success'""", (temp_id,)
        ).fetchone()
        legacy_uses = max(0, temporary["use_count"] - int(run_totals["uses"] or 0))
        legacy_positives = max(0, temporary["positive_count"] - int(run_totals["positives"] or 0))
        legacy_negatives = max(0, temporary["negative_count"] - int(run_totals["negatives"] or 0))
        with self.conn:
            if target_id:
                target = self.get(target_id)
                if duplicate_action == "replace":
                    list_values = {field: json_text(temporary[field]) for field in JSON_FIELDS}
                    self.conn.execute(
                        """UPDATE prompts SET name=?,category=?,subcategory=?,tags=?,suitable_for=?,
                           avoid_when=?,strengths=?,prompt_text=?,notes=?,use_count=use_count+?,
                           positive_count=positive_count+?,negative_count=negative_count+?,
                           legacy_use_count=legacy_use_count+?,
                           legacy_positive_count=legacy_positive_count+?,
                           legacy_negative_count=legacy_negative_count+?,
                           preference_weight=preference_weight+?,last_used_at=COALESCE(?,last_used_at),
                           updated_at=?,version=version+1 WHERE id=?""",
                        (temporary["name"], temporary["category"], temporary["subcategory"],
                         list_values["tags"], list_values["suitable_for"], list_values["avoid_when"],
                         list_values["strengths"], temporary["prompt_text"], temporary["notes"],
                         temporary["use_count"], temporary["positive_count"], temporary["negative_count"],
                         legacy_uses, legacy_positives, legacy_negatives, preference_delta,
                         temporary["last_used_at"], timestamp, target_id),
                    )
                    self._insert_version_snapshot(target_id, target["version"] + 1,
                                                  temporary["prompt_text"],
                                                  f"由临时 Prompt {temp_id} 替换")
                else:
                    merged = {field: json_text(target[field] + temporary[field]) for field in JSON_FIELDS}
                    note = target["notes"] + f"\n\n[Temporary {temp_id}]\n{temporary['prompt_text']}"
                    self.conn.execute(
                        """UPDATE prompts SET tags=?,suitable_for=?,avoid_when=?,strengths=?,notes=?,
                           use_count=use_count+?,positive_count=positive_count+?,negative_count=negative_count+?,
                           legacy_use_count=legacy_use_count+?,
                           legacy_positive_count=legacy_positive_count+?,
                           legacy_negative_count=legacy_negative_count+?,
                           preference_weight=preference_weight+?,last_used_at=COALESCE(?,last_used_at),
                           updated_at=? WHERE id=?""",
                        (merged["tags"], merged["suitable_for"], merged["avoid_when"], merged["strengths"],
                         note, temporary["use_count"], temporary["positive_count"],
                         temporary["negative_count"], legacy_uses, legacy_positives, legacy_negatives,
                         preference_delta, temporary["last_used_at"], timestamp, target_id),
                    )
                formal_id = target_id
            else:
                formal_id = self._next_id()
                self.conn.execute(
                    """INSERT INTO prompts(
                       id,name,category,subcategory,tags,suitable_for,avoid_when,strengths,prompt_text,
                       notes,use_count,positive_count,negative_count,preference_weight,created_at,
                       updated_at,last_used_at,source_type,origin_temporary_id,legacy_use_count,
                       legacy_positive_count,legacy_negative_count
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (formal_id, temporary["name"], temporary["category"], temporary["subcategory"],
                     json_text(temporary["tags"]), json_text(temporary["suitable_for"]),
                     json_text(temporary["avoid_when"]), json_text(temporary["strengths"]),
                     temporary["prompt_text"], temporary["notes"], temporary["use_count"],
                     temporary["positive_count"], temporary["negative_count"], preference_delta,
                     timestamp, timestamp, temporary["last_used_at"], "temporary_generated", temp_id,
                     legacy_uses, legacy_positives, legacy_negatives),
                )
                self._insert_version_snapshot(formal_id, 1, temporary["prompt_text"],
                                              f"由临时 Prompt {temp_id} 收藏")
            self.conn.execute(
                "UPDATE temporary_prompts SET status='saved',formal_prompt_id=?,updated_at=? WHERE temp_id=?",
                (formal_id, timestamp, temp_id),
            )
            formal_version = self.get(formal_id)["version"]
            self.conn.execute(
                """UPDATE runs SET prompt_id=?,prompt_version=?,temporary_prompt_id=NULL
                   WHERE temporary_prompt_id=?""", (formal_id, formal_version, temp_id)
            )
            self._history(formal_id, "temporary_promoted",
                          {"temp_id": temp_id, "use_count": temporary["use_count"],
                           "positive_count": temporary["positive_count"],
                           "negative_count": temporary["negative_count"]})
        backup = self.backup("temporary-promoted")
        return {"status": "temporary_saved", "temporary_id": temp_id,
                "prompt": self.get(formal_id), "backup": backup["backup"]}

    def discard_temporary(self, temp_id: str) -> dict[str, Any]:
        temporary = self.get_temporary(temp_id)
        if temporary["status"] == "saved":
            raise LibraryError("已收藏的临时 Prompt 不能丢弃；如需处理请管理正式 Prompt")
        with self.conn:
            self.conn.execute(
                "UPDATE temporary_prompts SET status='discarded',updated_at=? WHERE temp_id=?",
                (now(), temp_id),
            )
            self._history(None, "temporary_discarded", None, {"temp_id": temp_id})
        return {"status": "temporary_discarded", "temporary_prompt": self.get_temporary(temp_id)}

    def recent_use(self) -> dict[str, Any]:
        row = self.conn.execute(
            """SELECT * FROM runs WHERE status='success'
               ORDER BY COALESCE(completed_at,started_at) DESC,run_id DESC LIMIT 1"""
        ).fetchone()
        if row is None:
            raise LibraryError("还没有实际执行过任何 Prompt")
        if row["prompt_id"]:
            return {"status": "ok", "kind": "formal", "run": self.decode_run(row),
                    "prompt": self.get(row["prompt_id"])}
        return {"status": "ok", "kind": "temporary", "run": self.decode_run(row),
                "temporary_prompt": self.get_temporary(row["temporary_prompt_id"])}

    def feedback_last(self, kind: str, context: str | None = None) -> dict[str, Any]:
        recent = self.recent_use()
        return self.run_feedback(recent["run"]["run_id"], kind, context)

    def version_get(self, prompt_id: str, version: int) -> dict[str, Any]:
        prompt_id = normalize_id(prompt_id)
        row = self.conn.execute(
            "SELECT * FROM prompt_versions WHERE prompt_id=? AND version=?",
            (prompt_id, int(version)),
        ).fetchone()
        if row is None:
            raise LibraryError(f"未找到版本：{prompt_id} v{version}")
        data = dict(row)
        data["metadata_snapshot"] = json.loads(data["metadata_snapshot"] or "{}")
        stats = self.conn.execute(
            """SELECT COUNT(*) AS runs,
               SUM(CASE WHEN feedback='positive' THEN 1 ELSE 0 END) AS positives,
               SUM(CASE WHEN feedback IN ('negative','never') THEN 1 ELSE 0 END) AS negatives
               FROM runs WHERE prompt_id=? AND prompt_version=? AND status='success'""",
            (prompt_id, int(version)),
        ).fetchone()
        data["runs"] = int(stats["runs"] or 0)
        data["positive_runs"] = int(stats["positives"] or 0)
        data["negative_runs"] = int(stats["negatives"] or 0)
        return data

    def version_list(self, prompt_id: str) -> dict[str, Any]:
        prompt = self.get(prompt_id)
        rows = self.conn.execute(
            "SELECT version FROM prompt_versions WHERE prompt_id=? ORDER BY version", (prompt["id"],)
        ).fetchall()
        return {"status": "ok", "prompt_id": prompt["id"], "name": prompt["name"],
                "current_version": prompt["version"],
                "versions": [self.version_get(prompt["id"], row["version"]) for row in rows]}

    def version_diff(self, prompt_id: str, left: int, right: int) -> dict[str, Any]:
        first = self.version_get(prompt_id, left)
        second = self.version_get(prompt_id, right)
        diff = list(difflib.unified_diff(
            first["prompt_text"].splitlines(), second["prompt_text"].splitlines(),
            fromfile=f"{prompt_id} v{left}", tofile=f"{prompt_id} v{right}", lineterm="",
        ))
        metadata_changes = {
            key: {"before": first["metadata_snapshot"].get(key),
                  "after": second["metadata_snapshot"].get(key)}
            for key in VERSION_METADATA_FIELDS
            if first["metadata_snapshot"].get(key) != second["metadata_snapshot"].get(key)
        }
        return {"status": "ok", "prompt_id": normalize_id(prompt_id),
                "from_version": int(left), "to_version": int(right),
                "diff": diff, "metadata_changes": metadata_changes}

    def version_restore(self, prompt_id: str, version: int) -> dict[str, Any]:
        prompt = self.get(prompt_id)
        source = self.version_get(prompt_id, version)
        metadata = source["metadata_snapshot"]
        new_version = prompt["version"] + 1
        timestamp = now()
        with self.conn:
            self.conn.execute(
                """UPDATE prompts SET name=?,category=?,subcategory=?,tags=?,suitable_for=?,
                   avoid_when=?,strengths=?,prompt_text=?,version=?,updated_at=? WHERE id=?""",
                (metadata.get("name", prompt["name"]), metadata.get("category", prompt["category"]),
                 metadata.get("subcategory", prompt["subcategory"]), json_text(metadata.get("tags")),
                 json_text(metadata.get("suitable_for")), json_text(metadata.get("avoid_when")),
                 json_text(metadata.get("strengths")), source["prompt_text"], new_version,
                 timestamp, prompt["id"]),
            )
            self._insert_version_snapshot(prompt["id"], new_version, source["prompt_text"],
                                          f"由用户从 v{version} 恢复")
            self._history(prompt["id"], "version_restore", {
                "source_version": int(version), "new_version": new_version,
            })
        backup = self.backup("version-restore")
        return {"status": "version_restored", "source_version": int(version),
                "prompt": self.get(prompt["id"]), "backup": backup["backup"]}

    def provenance(self, prompt_id: str) -> dict[str, Any]:
        prompt = self.get(prompt_id)
        result = {key: prompt.get(key) for key in (
            "id", "name", "source_type", "source_ref", "source_note", "parent_prompt_id",
            "parent_prompt_version", "origin_temporary_id", "created_at", "version",
        )}
        if prompt.get("parent_prompt_id"):
            parent = self.get(prompt["parent_prompt_id"])
            result["parent"] = {"id": parent["id"], "name": parent["name"],
                                "version": prompt["parent_prompt_version"]}
        return {"status": "ok", "provenance": result}

    def trash(self, prompt_id: str) -> dict[str, Any]:
        prompt = self.get(prompt_id)
        if prompt.get("deleted_at"):
            raise LibraryError(f"Prompt {prompt_id} 已在回收站")
        timestamp = now()
        with self.conn:
            self.conn.execute("UPDATE prompts SET deleted_at=?,updated_at=? WHERE id=?",
                              (timestamp, timestamp, prompt["id"]))
            self._history(prompt["id"], "trash", None, {"deleted_at": timestamp})
        return {"status": "trashed", "prompt": self.get(prompt["id"])}

    def trash_list(self) -> dict[str, Any]:
        rows = self.conn.execute(
            "SELECT * FROM prompts WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC,id"
        ).fetchall()
        return {"status": "ok", "count": len(rows),
                "prompts": [self.decode_row(row, include_prompt=False) for row in rows]}

    def trash_restore(self, prompt_id: str) -> dict[str, Any]:
        prompt = self.get(prompt_id)
        if not prompt.get("deleted_at"):
            raise LibraryError(f"Prompt {prompt_id} 不在回收站")
        with self.conn:
            self.conn.execute("UPDATE prompts SET deleted_at=NULL,updated_at=? WHERE id=?",
                              (now(), prompt["id"]))
            self._history(prompt["id"], "trash_restore")
        return {"status": "trash_restored", "prompt": self.get(prompt["id"])}

    def trash_purge(self, prompt_id: str, confirmed: bool) -> dict[str, Any]:
        prompt = self.get(prompt_id)
        if not prompt.get("deleted_at"):
            raise LibraryError("只有回收站中的 Prompt 才能永久删除")
        if not confirmed:
            raise LibraryError("永久删除需要明确确认：重新运行并添加 --confirm")
        pre = self.backup("before-trash-purge")
        with self.conn:
            self._history(prompt["id"], "permanent_delete", {"id": prompt["id"], "name": prompt["name"]})
            self.conn.execute("DELETE FROM prompts WHERE id=?", (prompt["id"],))
        post = self.backup("trash-purge")
        return {"status": "purged", "id": prompt_id, "backup_before": pre["backup"],
                "backup_after": post["backup"]}

    def trash_clean(self, days: int, confirmed: bool) -> dict[str, Any]:
        if not confirmed:
            raise LibraryError("清理回收站需要明确确认：重新运行并添加 --confirm")
        cutoff = (dt.datetime.now(dt.timezone.utc).astimezone() - dt.timedelta(days=max(0, days))).isoformat()
        ids = [row[0] for row in self.conn.execute(
            "SELECT id FROM prompts WHERE deleted_at IS NOT NULL AND deleted_at<?", (cutoff,)
        )]
        if not ids:
            return {"status": "ok", "purged": []}
        pre = self.backup("before-trash-clean")
        with self.conn:
            for prompt_id in ids:
                self._history(prompt_id, "permanent_delete", {"reason": f"trash older than {days} days"})
                self.conn.execute("DELETE FROM prompts WHERE id=?", (prompt_id,))
        post = self.backup("trash-clean")
        return {"status": "trash_cleaned", "purged": ids, "backup_before": pre["backup"],
                "backup_after": post["backup"]}

    def stats_check(self, prompt_id: str | None = None) -> dict[str, Any]:
        rows = [self._row(prompt_id)] if prompt_id else self.conn.execute(
            "SELECT * FROM prompts ORDER BY id"
        ).fetchall()
        checks = []
        for row in rows:
            run_stats = self.conn.execute(
                """SELECT COUNT(*) AS uses,
                   SUM(CASE WHEN feedback='positive' THEN 1 ELSE 0 END) AS positives,
                   SUM(CASE WHEN feedback IN ('negative','never') THEN 1 ELSE 0 END) AS negatives
                   FROM runs WHERE prompt_id=? AND status='success'""", (row["id"],)
            ).fetchone()
            expected = {
                "use_count": row["legacy_use_count"] + int(run_stats["uses"] or 0),
                "positive_count": row["legacy_positive_count"] + int(run_stats["positives"] or 0),
                "negative_count": row["legacy_negative_count"] + int(run_stats["negatives"] or 0),
            }
            actual = {key: row[key] for key in expected}
            checks.append({"prompt_id": row["id"], "ok": actual == expected,
                           "actual": actual, "expected": expected,
                           "legacy_aggregate": {
                               "use_count": row["legacy_use_count"],
                               "positive_count": row["legacy_positive_count"],
                               "negative_count": row["legacy_negative_count"],
                           }})
        return {"status": "ok" if all(item["ok"] for item in checks) else "warn",
                "checks": checks, "legacy_note": "V3 以前的汇总统计没有逐次 Run，未伪造历史记录。"}

    def stats_rebuild(self, prompt_id: str) -> dict[str, Any]:
        prompt = self._row(prompt_id)
        check = self.stats_check(prompt["id"])["checks"][0]
        with self.conn:
            self.conn.execute(
                """UPDATE prompts SET use_count=?,positive_count=?,negative_count=?,updated_at=?
                   WHERE id=?""",
                (check["expected"]["use_count"], check["expected"]["positive_count"],
                 check["expected"]["negative_count"], now(), prompt["id"]),
            )
            self._history(prompt["id"], "stats_rebuild", check)
        backup = self.backup("stats-rebuild")
        return {"status": "stats_rebuilt", "prompt": self.get(prompt["id"]),
                "before": check["actual"], "after": check["expected"], "backup": backup["backup"]}

    def export_json(self, output: Path | None = None) -> dict[str, Any]:
        if output is None:
            output = self.exports_dir / f"image-prompts-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": FORMAT_NAME, "version": FORMAT_VERSION, "exported_at": now(),
            "prompts": [self.decode_row(r) for r in self.conn.execute("SELECT * FROM prompts ORDER BY id")],
            "history": [dict(r) for r in self.conn.execute("SELECT * FROM history ORDER BY event_id")],
            "prompt_versions": [dict(r) for r in self.conn.execute(
                "SELECT * FROM prompt_versions ORDER BY prompt_id,version"
            )],
            "runs": [self.decode_run(r) for r in self.conn.execute("SELECT * FROM runs ORDER BY run_id")],
        }
        temp = output.with_suffix(output.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, output)
        return {"status": "exported", "path": str(output), "prompt_count": len(payload["prompts"]),
                "history_count": len(payload["history"])}

    def import_json(self, input_path: Path, conflict: str = "skip") -> dict[str, Any]:
        path = input_path.expanduser().resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LibraryError(f"导入文件无法读取：{exc}") from exc
        if not isinstance(payload, dict) or payload.get("format") != FORMAT_NAME:
            raise LibraryError("导入文件格式无效：缺少正确的 format")
        prompts = payload.get("prompts")
        if not isinstance(prompts, list):
            raise LibraryError("导入文件格式无效：prompts 必须是数组")
        required = {"id", "name", "prompt_text"}
        for index, item in enumerate(prompts):
            if not isinstance(item, dict) or not required <= item.keys():
                raise LibraryError(f"导入文件第 {index + 1} 条 Prompt 结构无效")
            normalize_id(str(item["id"]))
        pre = self.backup("before-import")
        created, skipped, replaced, remapped = [], [], [], {}
        id_map: dict[str, str] = {}
        imported_versions = 0
        imported_runs = 0
        imported_history = 0
        run_remapped: dict[str, str] = {}
        with self.conn:
            for raw in prompts:
                incoming = dict(raw)
                source_id = normalize_id(str(incoming["id"]))
                exists = self.conn.execute("SELECT 1 FROM prompts WHERE id=?", (source_id,)).fetchone()
                candidate = {
                    "name": incoming["name"], "category": incoming.get("category", "其他"),
                    "tags": incoming.get("tags", []), "prompt_text": incoming["prompt_text"],
                }
                duplicate = self.duplicates(candidate, limit=1)
                if duplicate and duplicate[0]["similarity"] >= float(self.settings["duplicate_threshold"]):
                    if not exists or conflict == "skip":
                        skipped.append({"id": source_id, "reason": "duplicate", "match": duplicate[0]})
                        continue
                target_id = source_id
                if exists:
                    if conflict == "skip":
                        skipped.append({"id": source_id, "reason": "id_conflict"})
                        continue
                    if conflict == "remap":
                        target_id = self._next_id()
                        remapped[source_id] = target_id
                    elif conflict == "replace":
                        self.conn.execute("DELETE FROM prompts WHERE id=?", (source_id,))
                        replaced.append(source_id)
                timestamp = now()
                columns = {
                    "id": target_id, "name": str(incoming["name"]).strip(),
                    "category": str(incoming.get("category") or "其他"),
                    "subcategory": str(incoming.get("subcategory") or ""),
                    "tags": json_text(incoming.get("tags")),
                    "suitable_for": json_text(incoming.get("suitable_for")),
                    "avoid_when": json_text(incoming.get("avoid_when")),
                    "strengths": json_text(incoming.get("strengths")),
                    "prompt_text": str(incoming["prompt_text"]).strip(),
                    "notes": str(incoming.get("notes") or ""),
                    "use_count": max(0, int(incoming.get("use_count", 0))),
                    "positive_count": max(0, int(incoming.get("positive_count", 0))),
                    "negative_count": max(0, int(incoming.get("negative_count", 0))),
                    "user_rating": incoming.get("user_rating"),
                    "preference_weight": float(incoming.get("preference_weight", 0)),
                    "favorite": int(bool(incoming.get("favorite", False))),
                    "disabled": int(bool(incoming.get("disabled", False))),
                    "created_at": str(incoming.get("created_at") or timestamp),
                    "updated_at": timestamp, "last_used_at": incoming.get("last_used_at"),
                    "version": max(1, int(incoming.get("version", 1))),
                    "source_type": "imported",
                    "source_ref": incoming.get("source_ref"),
                    "source_note": incoming.get("source_note"),
                    "parent_prompt_id": None,
                    "parent_prompt_version": incoming.get("parent_prompt_version"),
                    "origin_temporary_id": incoming.get("origin_temporary_id"),
                    "deleted_at": incoming.get("deleted_at"),
                    "legacy_use_count": max(0, int(incoming.get("legacy_use_count", incoming.get("use_count", 0)))),
                    "legacy_positive_count": max(0, int(incoming.get("legacy_positive_count", incoming.get("positive_count", 0)))),
                    "legacy_negative_count": max(0, int(incoming.get("legacy_negative_count", incoming.get("negative_count", 0)))),
                }
                keys = list(columns)
                self.conn.execute(
                    f"INSERT INTO prompts({','.join(keys)}) VALUES({','.join('?' for _ in keys)})",
                    [columns[k] for k in keys],
                )
                self._insert_version_snapshot(target_id, columns["version"], columns["prompt_text"],
                                              "从 JSON 导入")
                self._history(target_id, "import", {"source_id": source_id})
                created.append(target_id)
                id_map[source_id] = target_id
            versions = payload.get("prompt_versions", [])
            if versions is not None and not isinstance(versions, list):
                raise LibraryError("导入文件格式无效：prompt_versions 必须是数组")
            grouped_versions: dict[str, list[dict[str, Any]]] = {}
            for raw_version in versions or []:
                if not isinstance(raw_version, dict) or not {"prompt_id", "version", "prompt_text"} <= raw_version.keys():
                    raise LibraryError("导入文件包含无效 Prompt 版本")
                grouped_versions.setdefault(normalize_id(str(raw_version["prompt_id"])), []).append(raw_version)
            for source_id, target_id in id_map.items():
                source_versions = grouped_versions.get(source_id, [])
                if not source_versions:
                    continue
                self.conn.execute("DELETE FROM prompt_versions WHERE prompt_id=?", (target_id,))
                for item in sorted(source_versions, key=lambda value: int(value["version"])):
                    metadata = item.get("metadata_snapshot", {})
                    if isinstance(metadata, str):
                        try:
                            metadata = json.loads(metadata)
                        except json.JSONDecodeError as exc:
                            raise LibraryError("Prompt 版本 metadata_snapshot 不是有效 JSON") from exc
                    self.conn.execute(
                        """INSERT INTO prompt_versions(prompt_id,version,prompt_text,metadata_snapshot,
                           change_note,created_at) VALUES(?,?,?,?,?,?)""",
                        (target_id, int(item["version"]), str(item["prompt_text"]),
                         json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                         str(item.get("change_note") or ""), str(item.get("created_at") or now())),
                    )
                    imported_versions += 1
            runs = payload.get("runs", [])
            if runs is not None and not isinstance(runs, list):
                raise LibraryError("导入文件格式无效：runs 必须是数组")
            for raw_run in runs or []:
                if not isinstance(raw_run, dict) or not {"run_id", "prompt_snapshot", "status"} <= raw_run.keys():
                    raise LibraryError("导入文件包含无效 Run")
                source_prompt_id = raw_run.get("prompt_id")
                if not source_prompt_id or source_prompt_id not in id_map:
                    continue
                status = str(raw_run["status"])
                if status not in RUN_STATUSES:
                    raise LibraryError(f"导入文件包含无效 Run 状态：{status}")
                source_run_id = normalize_run_id(str(raw_run["run_id"]))
                target_run_id = source_run_id
                if self.conn.execute("SELECT 1 FROM runs WHERE run_id=?", (target_run_id,)).fetchone():
                    target_run_id = self._next_run_id()
                    run_remapped[source_run_id] = target_run_id
                feedback = raw_run.get("feedback")
                if feedback is not None and feedback not in RUN_FEEDBACK:
                    raise LibraryError(f"导入文件包含无效 Run 反馈：{feedback}")
                self.conn.execute(
                    """INSERT INTO runs(run_id,prompt_id,prompt_version,temporary_prompt_id,image_context,
                       prompt_snapshot,executor,model,status,result_ref,result_path,error_summary,
                       started_at,completed_at,feedback,feedback_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (target_run_id, id_map[source_prompt_id], raw_run.get("prompt_version"), None,
                     compact_json(raw_run.get("image_context")), str(raw_run["prompt_snapshot"]),
                     str(raw_run.get("executor") or "unknown"), raw_run.get("model"), status,
                     raw_run.get("result_ref"), raw_run.get("result_path"), raw_run.get("error_summary"),
                     str(raw_run.get("started_at") or now()), raw_run.get("completed_at"), feedback,
                     raw_run.get("feedback_at")),
                )
                imported_runs += 1
            highest_run = self.conn.execute(
                "SELECT COALESCE(MAX(CAST(SUBSTR(run_id,2) AS INTEGER)),0) FROM runs"
            ).fetchone()[0]
            current_run = int(self.conn.execute(
                "SELECT value FROM meta WHERE key='next_run_number'"
            ).fetchone()[0])
            if current_run <= highest_run:
                self.conn.execute("UPDATE meta SET value=? WHERE key='next_run_number'",
                                  (str(highest_run + 1),))
            history = payload.get("history", [])
            if history is not None and not isinstance(history, list):
                raise LibraryError("导入文件格式无效：history 必须是数组")
            for item in history or []:
                if not isinstance(item, dict) or "event_type" not in item:
                    raise LibraryError("导入文件包含无效 history 事件")
                source_prompt_id = item.get("prompt_id")
                if source_prompt_id and source_prompt_id not in id_map:
                    continue
                self.conn.execute(
                    """INSERT INTO history(prompt_id,event_type,event_value,context,timestamp)
                       VALUES(?,?,?,?,?)""",
                    (id_map.get(source_prompt_id) if source_prompt_id else None,
                     str(item["event_type"]), item.get("event_value"), item.get("context"),
                     str(item.get("timestamp") or now())),
                )
                imported_history += 1
        post = self.backup("import")
        return {"status": "imported", "created": created, "replaced": replaced,
                "remapped": remapped, "skipped": skipped, "versions_imported": imported_versions,
                "runs_imported": imported_runs, "history_imported": imported_history,
                "run_remapped": run_remapped, "backup_before": pre["backup"],
                "backup_after": post["backup"]}


def add_common_prompt_fields(parser: argparse.ArgumentParser, required: bool = False) -> None:
    parser.add_argument("--name", required=required)
    parser.add_argument("--category")
    parser.add_argument("--subcategory")
    parser.add_argument("--tags", help="逗号分隔")
    parser.add_argument("--suitable-for", dest="suitable_for", help="逗号分隔")
    parser.add_argument("--avoid-when", dest="avoid_when", help="逗号分隔")
    parser.add_argument("--strengths", help="逗号分隔")
    parser.add_argument("--prompt-text", dest="prompt_text", required=required)
    parser.add_argument("--notes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="管理本地个人图片 Prompt 数据库")
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".image-prompt-manager",
                        help="数据目录，默认 ~/.image-prompt-manager")
    parser.add_argument("--json", action="store_true", help="输出 UTF-8 JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="初始化数据库")
    add = sub.add_parser("add", help="添加 Prompt（自动检查重复）")
    add_common_prompt_fields(add, required=True)
    add.add_argument("--duplicate-action", choices=["check", "add", "merge", "replace"], default="check")
    add.add_argument("--source-type", dest="source_type", choices=sorted(SOURCE_TYPES), default="manual")
    add.add_argument("--source-ref", dest="source_ref"); add.add_argument("--source-note", dest="source_note")
    add.add_argument("--parent-prompt-id", dest="parent_prompt_id")
    add.add_argument("--parent-prompt-version", dest="parent_prompt_version", type=int)
    get = sub.add_parser("get", help="获取完整 Prompt"); get.add_argument("id")
    listing = sub.add_parser("list", help="紧凑浏览")
    listing.add_argument("--category"); listing.add_argument("--all", action="store_true"); listing.add_argument("--limit", type=int, default=100)
    search = sub.add_parser("search", help="关键词搜索"); search.add_argument("query"); search.add_argument("--limit", type=int, default=20); search.add_argument("--all", action="store_true")
    candidates = sub.add_parser("candidates", help="取得图片推荐的小候选集")
    candidates.add_argument("--category"); candidates.add_argument("--subcategory"); candidates.add_argument("--tags"); candidates.add_argument("--query"); candidates.add_argument("--limit", type=int, default=12)
    recommend = sub.add_parser("recommend", help="按模型给出的图片匹配分数应用质量阈值")
    recommend.add_argument("--scores", required=True, help="JSON 对象或 P001=72,P002=38")
    recommend.add_argument("--context", default="", help="图片分析摘要，用于 avoid_when 过滤")
    recommend.add_argument("--show-all", action="store_true", help="包含低匹配/冲突候选")
    recommend.add_argument("--force-temporary", action="store_true", help="即使有高匹配也标记需要临时方案")
    sub.add_parser("stats", help="显示分类统计")
    sub.add_parser("status", help="检查数据库与累计统计")
    update = sub.add_parser("update", help="修改 Prompt"); update.add_argument("id"); add_common_prompt_fields(update); update.add_argument("--change-note", dest="change_note")
    use = sub.add_parser("use", help="实际选择并使用 Prompt"); use.add_argument("id"); use.add_argument("--context")
    undo = sub.add_parser("undo-use", help="撤回最近一次 use 计数"); undo.add_argument("id", nargs="?")
    feedback = sub.add_parser("feedback", help="记录自然语言反馈")
    feedback.add_argument("id"); feedback.add_argument("kind", choices=["positive", "neutral", "negative", "never"]); feedback.add_argument("--context")
    feedback_last = sub.add_parser("feedback-last", help="反馈绑定最近实际执行的 Prompt")
    feedback_last.add_argument("kind", choices=["positive", "neutral", "negative", "never"]); feedback_last.add_argument("--context")
    rate = sub.add_parser("rate", help="评分 1-5"); rate.add_argument("id"); rate.add_argument("rating", type=float); rate.add_argument("--context")
    pref = sub.add_parser("preference", help="增减推荐偏好权重"); pref.add_argument("id"); pref.add_argument("delta", type=float); pref.add_argument("--context")
    for name in ("disable", "enable", "favorite", "unfavorite"):
        flag = sub.add_parser(name); flag.add_argument("id")
    delete = sub.add_parser("delete", help="永久删除（需确认）"); delete.add_argument("id"); delete.add_argument("--confirm", action="store_true")
    merge = sub.add_parser("merge", help="把 source 合并进 target"); merge.add_argument("target"); merge.add_argument("source")
    backup = sub.add_parser("backup", help="手动备份"); backup.add_argument("--reason", default="manual")
    export = sub.add_parser("export", help="导出可读 JSON"); export.add_argument("--output", type=Path)
    imported = sub.add_parser("import", help="导入 JSON"); imported.add_argument("path", type=Path); imported.add_argument("--conflict", choices=["skip", "remap", "replace"], default="skip")
    temporary_create = sub.add_parser("temporary-create", help="创建未入正式库的临时方案")
    add_common_prompt_fields(temporary_create, required=True); temporary_create.add_argument("--context", default="")
    temporary_get = sub.add_parser("temporary-get", help="查看临时方案"); temporary_get.add_argument("temp_id")
    temporary_use = sub.add_parser("temporary-use", help="记录临时方案已成功执行")
    temporary_use.add_argument("temp_id"); temporary_use.add_argument("--context")
    temporary_feedback = sub.add_parser("temporary-feedback", help="记录临时方案效果反馈")
    temporary_feedback.add_argument("temp_id"); temporary_feedback.add_argument("kind", choices=["positive", "neutral", "negative"]); temporary_feedback.add_argument("--context")
    temporary_save = sub.add_parser("temporary-save", help="把临时方案及真实统计迁移到正式库")
    temporary_save.add_argument("temp_id"); temporary_save.add_argument("--duplicate-action", choices=["check", "add", "merge", "replace"], default="check")
    temporary_discard = sub.add_parser("temporary-discard", help="丢弃临时方案")
    temporary_discard.add_argument("temp_id")
    sub.add_parser("recent-use", help="读取最近一次实际执行的正式或临时 Prompt")
    version_list = sub.add_parser("version-list", help="列出 Prompt 历史版本"); version_list.add_argument("id")
    version_get = sub.add_parser("version-get", help="查看 Prompt 版本"); version_get.add_argument("id"); version_get.add_argument("version", type=int)
    version_diff = sub.add_parser("version-diff", help="比较两个 Prompt 版本"); version_diff.add_argument("id"); version_diff.add_argument("left", type=int); version_diff.add_argument("right", type=int)
    version_restore = sub.add_parser("version-restore", help="恢复旧版本并创建新版本"); version_restore.add_argument("id"); version_restore.add_argument("version", type=int)
    run_start = sub.add_parser("run-start", help="创建 running 状态的执行记录")
    run_start.add_argument("target"); run_start.add_argument("--context"); run_start.add_argument("--executor", default="unknown"); run_start.add_argument("--model"); run_start.add_argument("--prompt-snapshot", dest="prompt_snapshot")
    run_complete = sub.add_parser("run-complete", help="标记 Run 成功并增加使用统计")
    run_complete.add_argument("run_id"); run_complete.add_argument("--result-ref", dest="result_ref"); run_complete.add_argument("--result-path", dest="result_path")
    run_fail = sub.add_parser("run-fail", help="标记 Run 失败且不增加使用统计")
    run_fail.add_argument("run_id"); run_fail.add_argument("--error", required=True); run_fail.add_argument("--result-ref", dest="result_ref")
    run_get = sub.add_parser("run-get", help="查看 Run"); run_get.add_argument("run_id")
    run_list = sub.add_parser("run-list", help="浏览 Run 历史")
    run_list.add_argument("--prompt"); run_list.add_argument("--limit", type=int, default=20); run_list.add_argument("--status", choices=sorted(RUN_STATUSES))
    run_feedback = sub.add_parser("run-feedback", help="记录或修正 Run 反馈")
    run_feedback.add_argument("run_id"); run_feedback.add_argument("kind", choices=sorted(RUN_FEEDBACK)); run_feedback.add_argument("--context")
    provenance = sub.add_parser("provenance", help="查看 Prompt 来源与血缘"); provenance.add_argument("id")
    trash = sub.add_parser("trash", help="把 Prompt 移入回收站"); trash.add_argument("id")
    sub.add_parser("trash-list", help="打开回收站")
    trash_restore = sub.add_parser("trash-restore", help="恢复回收站 Prompt"); trash_restore.add_argument("id")
    trash_purge = sub.add_parser("trash-purge", help="永久删除回收站 Prompt")
    trash_purge.add_argument("id"); trash_purge.add_argument("--confirm", action="store_true")
    trash_clean = sub.add_parser("trash-clean", help="清理指定天数前的回收站")
    trash_clean.add_argument("--days", type=int, default=30); trash_clean.add_argument("--confirm", action="store_true")
    stats_check = sub.add_parser("stats-check", help="核对聚合统计与 Runs"); stats_check.add_argument("id", nargs="?")
    stats_rebuild = sub.add_parser("stats-rebuild", help="从旧基线和 Runs 重建聚合统计"); stats_rebuild.add_argument("id")
    return parser


def execute(library: PromptLibrary, args: argparse.Namespace) -> dict[str, Any]:
    command = args.command
    if command == "init": return library.init_info()
    if command == "add": return library.add(vars(args), args.duplicate_action)
    if command == "get": return {"status": "ok", "prompt": library.get(args.id)}
    if command == "list": return library.list_prompts(args.category, args.all, args.limit)
    if command == "search": return library.search(args.query, args.limit, args.all)
    if command == "candidates": return library.candidates(args.category, args.subcategory, args.tags, args.query, args.limit)
    if command == "recommend": return library.recommend(parse_match_scores(args.scores), args.context, args.show_all, args.force_temporary)
    if command in {"stats", "status"}: return library.stats()
    if command == "update": return library.update(args.id, vars(args))
    if command == "use": return library.use(args.id, args.context)
    if command == "undo-use": return library.undo_use(args.id)
    if command == "feedback": return library.feedback(args.id, args.kind, args.context)
    if command == "feedback-last": return library.feedback_last(args.kind, args.context)
    if command == "rate": return library.rate(args.id, args.rating, args.context)
    if command == "preference": return library.preference(args.id, args.delta, args.context)
    if command in {"disable", "enable"}: return library.set_flag(args.id, "disabled", command == "disable")
    if command in {"favorite", "unfavorite"}: return library.set_flag(args.id, "favorite", command == "favorite")
    if command == "delete": return library.delete(args.id, args.confirm)
    if command == "merge": return library.merge(args.target, args.source)
    if command == "backup": return library.backup(args.reason)
    if command == "export": return library.export_json(args.output)
    if command == "import": return library.import_json(args.path, args.conflict)
    if command == "temporary-create": return library.create_temporary(vars(args), args.context)
    if command == "temporary-get": return {"status": "ok", "temporary_prompt": library.get_temporary(args.temp_id)}
    if command == "temporary-use": return library.use_temporary(args.temp_id, args.context)
    if command == "temporary-feedback": return library.feedback_temporary(args.temp_id, args.kind, args.context)
    if command == "temporary-save": return library.save_temporary(args.temp_id, args.duplicate_action)
    if command == "temporary-discard": return library.discard_temporary(args.temp_id)
    if command == "recent-use": return library.recent_use()
    if command == "version-list": return library.version_list(args.id)
    if command == "version-get": return {"status": "ok", "version": library.version_get(args.id, args.version)}
    if command == "version-diff": return library.version_diff(args.id, args.left, args.right)
    if command == "version-restore": return library.version_restore(args.id, args.version)
    if command == "run-start": return library.run_start(args.target, args.context, args.executor, args.model, args.prompt_snapshot)
    if command == "run-complete": return library.run_complete(args.run_id, args.result_ref, args.result_path)
    if command == "run-fail": return library.run_fail(args.run_id, args.error, args.result_ref)
    if command == "run-get": return {"status": "ok", "run": library.run_get(args.run_id)}
    if command == "run-list": return library.run_list(args.prompt, args.limit, args.status)
    if command == "run-feedback": return library.run_feedback(args.run_id, args.kind, args.context)
    if command == "provenance": return library.provenance(args.id)
    if command == "trash": return library.trash(args.id)
    if command == "trash-list": return library.trash_list()
    if command == "trash-restore": return library.trash_restore(args.id)
    if command == "trash-purge": return library.trash_purge(args.id, args.confirm)
    if command == "trash-clean": return library.trash_clean(args.days, args.confirm)
    if command == "stats-check": return library.stats_check(args.id)
    if command == "stats-rebuild": return library.stats_rebuild(args.id)
    raise LibraryError(f"未知命令：{command}")


def human_text(result: dict[str, Any]) -> str:
    status = result.get("status", "ok")
    if status == "duplicate_found":
        lines = ["⚠️ 发现相似提示词"]
        for item in result["candidates"]:
            lines.append(f"{item['id']}｜{item['name']}｜相似度 {item['similarity']:.0%}")
        lines.append("请明确选择：仍然新增 / 合并 / 替换 / 取消")
        return "\n".join(lines)
    if "prompt" in result and isinstance(result["prompt"], dict):
        p = result["prompt"]
        if status == "used":
            return (f"已使用：{p['id']}｜{p['name']}\n"
                    f"使用次数：{result['use_count_before']} → {result['use_count_after']}")
        if status == "feedback_recorded":
            return (f"已记录 {result['feedback']} 反馈\n{p['id']}｜{p['name']}\n"
                    f"正面反馈：{result['positive_count_before']} → {result['positive_count_after']}\n"
                    f"负面反馈：{result['negative_count_before']} → {result['negative_count_after']}\n"
                    f"偏好权重：{result['preference_weight_before']} → {result['preference_weight_after']}")
        return f"{status}: {p['id']}｜{p['name']}\n{p['category']} → {p['subcategory']}\n使用次数：{p['use_count']}"
    if status == "ok" and result.get("empty"):
        return "你的图片提示词库目前还是空的。\n你可以在得到一个满意的图片处理 Prompt 后直接说：‘把这个提示词收进图片库’。"
    return json.dumps(result, ensure_ascii=False, indent=2)


def main(argv: Sequence[str] | None = None) -> int:
    # JSON mode must remain reliably UTF-8 even on Windows systems whose active
    # console code page is GBK. Existing streams without reconfigure still work.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    library: PromptLibrary | None = None
    try:
        library = PromptLibrary(args.data_dir)
        result = execute(library, args)
        output = json.dumps(result, ensure_ascii=False, indent=2) if args.json else human_text(result)
        print(output)
        return 2 if result.get("status") == "duplicate_found" else 0
    except (LibraryError, sqlite3.Error, OSError, ValueError) as exc:
        error = {"status": "error", "error": str(exc)}
        print(json.dumps(error, ensure_ascii=False) if getattr(args, "json", False) else f"错误：{exc}", file=sys.stderr)
        return 1
    finally:
        if library is not None:
            library.close()


if __name__ == "__main__":
    raise SystemExit(main())
