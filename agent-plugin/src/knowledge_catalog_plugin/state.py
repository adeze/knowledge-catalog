"""Persistent curated memory and workflow state backed by DuckDB."""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

MEMORY_KINDS = frozenset({"decision", "constraint", "correction", "evidence", "note"})
WORK_STATUSES = frozenset({"todo", "doing", "blocked", "done", "cancelled"})
TERMINAL_WORK_STATUSES = frozenset({"done", "cancelled"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_tags(tags: list[str] | None) -> list[str]:
    normalized = []
    for tag in tags or []:
        value = tag.strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    return normalized[:50]


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _row(cursor: duckdb.DuckDBPyConnection, values: tuple[Any, ...] | None) -> dict[str, Any] | None:
    if values is None:
        return None
    result = {
        column[0]: _json_value(value)
        for column, value in zip(cursor.description, values, strict=True)
    }
    for field in ("metadata", "payload"):
        if isinstance(result.get(field), str):
            result[field] = json.loads(result[field])
    return result


def _rows(cursor: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    return [_row(cursor, values) for values in cursor.fetchall()]  # type: ignore[misc]


class DuckDBState:
    """Small, auditable local state store. It does not execute work items."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.extension_directory = self.path.parent / "extensions"
        self.extension_directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        connection = duckdb.connect(
            str(self.path),
            config={
                "extension_directory": str(self.extension_directory),
                "allow_unsigned_extensions": "false",
                "autoinstall_known_extensions": "false",
                "autoload_known_extensions": "false",
            },
        )
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[duckdb.DuckDBPyConnection]:
        with self._lock, self._connect() as connection:
            connection.begin()
            try:
                yield connection
            except BaseException:  # Roll back cancellations as well as ordinary errors.
                connection.rollback()
                raise
            else:
                connection.commit()

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id VARCHAR PRIMARY KEY,
                    content VARCHAR NOT NULL,
                    kind VARCHAR NOT NULL,
                    scope VARCHAR NOT NULL,
                    tags VARCHAR[] NOT NULL,
                    source VARCHAR,
                    metadata JSON NOT NULL,
                    supersedes VARCHAR,
                    active BOOLEAN NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );
                CREATE TABLE IF NOT EXISTS work_items (
                    work_id VARCHAR PRIMARY KEY,
                    title VARCHAR NOT NULL,
                    details VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    priority INTEGER NOT NULL,
                    parent_id VARCHAR,
                    depends_on VARCHAR[] NOT NULL,
                    tags VARCHAR[] NOT NULL,
                    due_at TIMESTAMPTZ,
                    metadata JSON NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_events (
                    event_id VARCHAR PRIMARY KEY,
                    work_id VARCHAR,
                    event_type VARCHAR NOT NULL,
                    summary VARCHAR NOT NULL,
                    payload JSON NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                );
                CREATE TABLE IF NOT EXISTS extension_policy (
                    name VARCHAR PRIMARY KEY,
                    repository VARCHAR NOT NULL,
                    enabled BOOLEAN NOT NULL,
                    acknowledged_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ NOT NULL
                );
                """
            )

    def remember(
        self,
        content: str,
        kind: str = "note",
        scope: str = "global",
        tags: list[str] | None = None,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
        supersedes: str | None = None,
    ) -> dict[str, Any]:
        text = content.strip()
        if not text:
            raise ValueError("content must not be empty")
        if len(text) > 100_000:
            raise ValueError("content must be at most 100000 characters")
        if kind not in MEMORY_KINDS:
            raise ValueError(f"kind must be one of {sorted(MEMORY_KINDS)}")
        normalized_scope = scope.strip()
        if not normalized_scope or len(normalized_scope) > 256:
            raise ValueError("scope must contain 1 to 256 characters")
        serialized_metadata = json.dumps(metadata or {}, separators=(",", ":"))
        memory_id = str(uuid.uuid4())
        timestamp = _now()

        with self._transaction() as connection:
            if supersedes:
                prior = connection.execute(
                    "SELECT active FROM memories WHERE memory_id = ?", [supersedes]
                ).fetchone()
                if prior is None:
                    raise ValueError(f"superseded memory {supersedes!r} does not exist")
                if not prior[0]:
                    raise ValueError(
                        f"superseded memory {supersedes!r} is no longer active"
                    )
                connection.execute(
                    "UPDATE memories SET active = false, updated_at = ? WHERE memory_id = ?",
                    [timestamp, supersedes],
                )
            connection.execute(
                """
                INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, true, ?, ?)
                """,
                [
                    memory_id,
                    text,
                    kind,
                    normalized_scope,
                    _normalize_tags(tags),
                    source.strip() if source else None,
                    serialized_metadata,
                    supersedes,
                    timestamp,
                    timestamp,
                ],
            )
            cursor = connection.execute(
                "SELECT * FROM memories WHERE memory_id = ?", [memory_id]
            )
            record = _row(cursor, cursor.fetchone())
        assert record is not None
        return record

    def recall(
        self,
        query: str,
        scope: str | None = None,
        kinds: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        requested_kinds = kinds or []
        invalid_kinds = set(requested_kinds) - MEMORY_KINDS
        if invalid_kinds:
            raise ValueError(f"invalid memory kinds: {sorted(invalid_kinds)}")

        normalized_query = query.strip()
        if normalized_query and self.is_extension_enabled("fts"):
            try:
                return {
                    "search_mode": "fts-bm25",
                    "items": self._recall_fts(
                        normalized_query, scope, requested_kinds, limit
                    ),
                }
            except duckdb.Error as error:  # FTS is optional; lexical search remains available.
                result = self._recall_lexical(
                    normalized_query, scope, requested_kinds, limit
                )
                return {
                    "search_mode": "lexical-fallback",
                    "warning": f"fts unavailable: {error}",
                    "items": result,
                }
        return {
            "search_mode": "recent" if not normalized_query else "lexical",
            "items": self._recall_lexical(
                normalized_query, scope, requested_kinds, limit
            ),
        }

    def _memory_filters(
        self, scope: str | None, kinds: list[str]
    ) -> tuple[list[str], list[Any]]:
        clauses = ["active = true"]
        parameters: list[Any] = []
        if scope:
            clauses.append("scope = ?")
            parameters.append(scope)
        if kinds:
            placeholders = ", ".join("?" for _ in kinds)
            clauses.append(f"kind IN ({placeholders})")
            parameters.extend(kinds)
        return clauses, parameters

    def _recall_lexical(
        self, query: str, scope: str | None, kinds: list[str], limit: int
    ) -> list[dict[str, Any]]:
        clauses, parameters = self._memory_filters(scope, kinds)
        if not query:
            sql = f"""
                SELECT *, NULL::INTEGER AS score
                FROM memories
                WHERE {' AND '.join(clauses)}
                ORDER BY updated_at DESC
                LIMIT ?
            """
            parameters.append(limit)
        else:
            terms = list(
                dict.fromkeys(re.findall(r"[a-z0-9][a-z0-9._/-]*", query.lower()))
            )[:12]
            if not terms:
                terms = [query.lower()]
            score_parts = ["CASE WHEN contains(lower(content), ?) THEN 3 ELSE 0 END"]
            score_parameters: list[Any] = [query.lower()]
            for term in terms:
                score_parts.append(
                    "CASE WHEN contains(lower(content), ?) OR "
                    "contains(lower(CAST(tags AS VARCHAR)), ?) THEN 1 ELSE 0 END"
                )
                score_parameters.extend([term, term])
            score = " + ".join(score_parts)
            sql = f"""
                SELECT *
                FROM (
                    SELECT *, {score} AS score
                    FROM memories
                    WHERE {' AND '.join(clauses)}
                ) ranked
                WHERE score > 0
                ORDER BY score DESC, updated_at DESC
                LIMIT ?
            """
            parameters = score_parameters + parameters + [limit]
        with self._connect() as connection:
            return _rows(connection.execute(sql, parameters))

    def _recall_fts(
        self, query: str, scope: str | None, kinds: list[str], limit: int
    ) -> list[dict[str, Any]]:
        clauses, parameters = self._memory_filters(scope, kinds)
        with self._transaction() as connection:
            connection.execute("LOAD fts")
            connection.execute(
                "PRAGMA create_fts_index('memories', 'memory_id', 'content', "
                "'kind', 'scope', overwrite = 1)"
            )
            sql = f"""
                SELECT *
                FROM (
                    SELECT *, fts_main_memories.match_bm25(memory_id, ?) AS score
                    FROM memories
                    WHERE {' AND '.join(clauses)}
                ) ranked
                WHERE score IS NOT NULL
                ORDER BY score DESC, updated_at DESC
                LIMIT ?
            """
            return _rows(connection.execute(sql, [query, *parameters, limit]))

    def create_work_item(
        self,
        title: str,
        details: str = "",
        priority: int = 0,
        status: str = "todo",
        parent_id: str | None = None,
        depends_on: list[str] | None = None,
        tags: list[str] | None = None,
        due_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("title must not be empty")
        if status not in WORK_STATUSES:
            raise ValueError(f"status must be one of {sorted(WORK_STATUSES)}")
        dependencies = list(dict.fromkeys(depends_on or []))
        work_id = str(uuid.uuid4())
        timestamp = _now()

        with self._transaction() as connection:
            self._require_work_items(connection, dependencies)
            if parent_id:
                self._require_work_items(connection, [parent_id])
            if status in {"doing", "done"}:
                self._require_dependencies_complete(connection, dependencies)
            connection.execute(
                """
                INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    work_id,
                    normalized_title,
                    details.strip(),
                    status,
                    priority,
                    parent_id,
                    dependencies,
                    _normalize_tags(tags),
                    due_at,
                    json.dumps(metadata or {}, separators=(",", ":")),
                    timestamp,
                    timestamp,
                ],
            )
            self._record_event(
                connection, work_id, "created", f"Created work item in {status}", {}
            )
            cursor = connection.execute(
                "SELECT * FROM work_items WHERE work_id = ?", [work_id]
            )
            record = _row(cursor, cursor.fetchone())
        assert record is not None
        return record

    def update_work_item(
        self,
        work_id: str,
        status: str | None = None,
        title: str | None = None,
        details: str | None = None,
        priority: int | None = None,
        tags: list[str] | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        if status is not None and status not in WORK_STATUSES:
            raise ValueError(f"status must be one of {sorted(WORK_STATUSES)}")
        normalized_note = note.strip() if note is not None else None
        if note is not None and not normalized_note:
            raise ValueError("note must not be empty")
        updates: list[str] = []
        parameters: list[Any] = []
        for field, value in (("title", title), ("details", details), ("priority", priority)):
            if value is not None:
                normalized = value.strip() if isinstance(value, str) else value
                if field == "title" and not normalized:
                    raise ValueError("title must not be empty")
                updates.append(f"{field} = ?")
                parameters.append(normalized)
        if tags is not None:
            updates.append("tags = ?")
            parameters.append(_normalize_tags(tags))
        if status is not None:
            updates.append("status = ?")
            parameters.append(status)
        if not updates and normalized_note is None:
            raise ValueError("provide a field update or note")

        with self._transaction() as connection:
            cursor = connection.execute(
                "SELECT * FROM work_items WHERE work_id = ?", [work_id]
            )
            current = _row(cursor, cursor.fetchone())
            if current is None:
                raise ValueError(f"work item {work_id!r} does not exist")
            if status in {"doing", "done"}:
                self._require_dependencies_complete(connection, current["depends_on"])
            if (
                status is not None
                and current["status"] in TERMINAL_WORK_STATUSES
                and status not in TERMINAL_WORK_STATUSES
            ):
                active_dependents = self._active_dependents(connection, work_id)
                if active_dependents:
                    raise ValueError(
                        "cannot reopen work item; doing or done dependents: "
                        f"{active_dependents}"
                    )
            if updates:
                updates.append("updated_at = ?")
                parameters.extend([_now(), work_id])
                connection.execute(
                    f"UPDATE work_items SET {', '.join(updates)} WHERE work_id = ?",
                    parameters,
                )
            summary = normalized_note or f"Updated work item to {status or current['status']}"
            self._record_event(connection, work_id, "updated", summary, {})
            cursor = connection.execute(
                "SELECT * FROM work_items WHERE work_id = ?", [work_id]
            )
            record = _row(cursor, cursor.fetchone())
        assert record is not None
        return record

    def list_work_items(
        self,
        status: str | None = None,
        runnable_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if status is not None and status not in WORK_STATUSES:
            raise ValueError(f"status must be one of {sorted(WORK_STATUSES)}")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        clauses = []
        parameters: list[Any] = []
        if status:
            clauses.append("item.status = ?")
            parameters.append(status)
        if runnable_only:
            clauses.extend(
                [
                    "item.status IN ('todo', 'doing')",
                    """
                    NOT EXISTS (
                        SELECT 1
                        FROM UNNEST(item.depends_on) AS required(dependency_id)
                        LEFT JOIN work_items AS dependency
                            ON dependency.work_id = required.dependency_id
                        WHERE dependency.work_id IS NULL
                           OR dependency.status NOT IN ('done', 'cancelled')
                    )
                    """,
                ]
            )
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            items = _rows(
                connection.execute(
                    f"""
                    SELECT item.* FROM work_items AS item
                    {where}
                    ORDER BY item.priority DESC, item.updated_at DESC
                    LIMIT ?
                    """,
                    [*parameters, limit],
                )
            )
            dependency_ids = list(
                dict.fromkeys(
                    dependency
                    for item in items
                    for dependency in item["depends_on"]
                )
            )
            dependency_states = self._work_item_statuses(connection, dependency_ids)
        for item in items:
            item["runnable"] = item["status"] in {"todo", "doing"} and all(
                dependency_states.get(dependency) in TERMINAL_WORK_STATUSES
                for dependency in item["depends_on"]
            )
        return [item for item in items if item["runnable"]] if runnable_only else items

    def record_event(
        self,
        event_type: str,
        summary: str,
        work_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not event_type.strip() or not summary.strip():
            raise ValueError("event_type and summary must not be empty")
        with self._lock, self._connect() as connection:
            if work_id:
                self._require_work_items(connection, [work_id])
            event_id = self._record_event(
                connection,
                work_id,
                event_type.strip(),
                summary.strip(),
                payload or {},
            )
            cursor = connection.execute(
                "SELECT * FROM workflow_events WHERE event_id = ?", [event_id]
            )
            record = _row(cursor, cursor.fetchone())
        assert record is not None
        return record

    def workflow_summary(self, recent_event_limit: int = 10) -> dict[str, Any]:
        if not 1 <= recent_event_limit <= 50:
            raise ValueError("recent_event_limit must be between 1 and 50")
        with self._connect() as connection:
            counts = {
                status: count
                for status, count in connection.execute(
                    "SELECT status, count() FROM work_items GROUP BY status"
                ).fetchall()
            }
            recent = _rows(
                connection.execute(
                    """
                    SELECT * FROM workflow_events
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    [recent_event_limit],
                )
            )
        return {
            "counts": {status: counts.get(status, 0) for status in sorted(WORK_STATUSES)},
            "recent_events": recent,
        }

    def _record_event(
        self,
        connection: duckdb.DuckDBPyConnection,
        work_id: str | None,
        event_type: str,
        summary: str,
        payload: dict[str, Any],
    ) -> str:
        event_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO workflow_events VALUES (?, ?, ?, ?, ?, ?)",
            [
                event_id,
                work_id,
                event_type,
                summary,
                json.dumps(payload, separators=(",", ":")),
                _now(),
            ],
        )
        return event_id

    def _require_work_items(
        self, connection: duckdb.DuckDBPyConnection, work_ids: list[str]
    ) -> None:
        if not work_ids:
            return
        states = self._work_item_statuses(connection, work_ids)
        missing = [work_id for work_id in work_ids if work_id not in states]
        if missing:
            raise ValueError(f"unknown work item dependencies: {missing}")

    def _work_item_statuses(
        self, connection: duckdb.DuckDBPyConnection, work_ids: list[str]
    ) -> dict[str, str]:
        if not work_ids:
            return {}
        placeholders = ", ".join("?" for _ in work_ids)
        return {
            work_id: status
            for work_id, status in connection.execute(
                f"SELECT work_id, status FROM work_items WHERE work_id IN ({placeholders})",
                work_ids,
            ).fetchall()
        }

    def _active_dependents(
        self, connection: duckdb.DuckDBPyConnection, work_id: str
    ) -> list[str]:
        return [
            dependent_id
            for (dependent_id,) in connection.execute(
                """
                SELECT work_id
                FROM work_items
                WHERE list_contains(depends_on, ?)
                  AND status IN ('doing', 'done')
                ORDER BY work_id
                """,
                [work_id],
            ).fetchall()
        ]

    def _require_dependencies_complete(
        self, connection: duckdb.DuckDBPyConnection, dependencies: list[str]
    ) -> None:
        states = self._work_item_statuses(connection, dependencies)
        unresolved = [
            dependency
            for dependency in dependencies
            if states.get(dependency) not in TERMINAL_WORK_STATUSES
        ]
        if unresolved:
            raise ValueError(f"cannot complete work item; unresolved dependencies: {unresolved}")

    def extension_policy(self) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            rows = _rows(connection.execute("SELECT * FROM extension_policy"))
        return {row["name"]: row for row in rows}

    def is_extension_enabled(self, name: str) -> bool:
        return bool(self.extension_policy().get(name, {}).get("enabled"))

    def set_extension_policy(
        self,
        name: str,
        repository: str,
        enabled: bool,
        acknowledged: bool,
    ) -> None:
        with self._lock, self._connect() as connection:
            self._set_extension_policy(
                connection, name, repository, enabled, acknowledged
            )

    def _set_extension_policy(
        self,
        connection: duckdb.DuckDBPyConnection,
        name: str,
        repository: str,
        enabled: bool,
        acknowledged: bool,
    ) -> None:
        timestamp = _now()
        connection.execute(
            """
            INSERT INTO extension_policy VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (name) DO UPDATE SET
                repository = excluded.repository,
                enabled = excluded.enabled,
                acknowledged_at = excluded.acknowledged_at,
                updated_at = excluded.updated_at
            """,
            [
                name,
                repository,
                enabled,
                timestamp if acknowledged else None,
                timestamp,
            ],
        )

    def install_and_enable_extension(
        self, name: str, repository: str, acknowledged: bool
    ) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError("invalid extension name")
        if repository not in {"core", "community"}:
            raise ValueError("extension repository must be core or community")
        with self._lock, self._connect() as connection:
            connection.install_extension(name, repository=repository)
            connection.load_extension(name)
            self._set_extension_policy(
                connection, name, repository, True, acknowledged
            )

    def extension_runtime_status(
        self, names: list[str]
    ) -> dict[str, dict[str, Any]]:
        if not names:
            return {}
        placeholders = ", ".join("?" for _ in names)
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                SELECT extension_name, installed, loaded, extension_version
                FROM duckdb_extensions()
                WHERE extension_name IN ({placeholders})
                """,
                names,
            )
            return {
                name: {
                    "installed": installed,
                    "loaded": loaded,
                    "extension_version": version,
                }
                for name, installed, loaded, version in cursor.fetchall()
            }

    def search_agent_history(
        self,
        query: str,
        limit: int = 20,
        project_path: str | None = None,
        codex_data_path: str | Path | None = None,
    ) -> list[dict[str, Any]]:
        if not self.is_extension_enabled("agent_data"):
            raise ValueError(
                "agent_data is disabled; enable it only after explicit approval with "
                "duckdb_extension_configure"
            )
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        data_path = Path(codex_data_path or Path.home() / ".codex").expanduser().resolve()
        with self._connect() as connection:
            connection.execute("LOAD agent_data")
            clauses = [
                "message_content IS NOT NULL",
                "message_role IN ('user', 'assistant')",
                "contains(lower(message_content), lower(?))",
            ]
            parameters: list[Any] = [str(data_path), normalized_query]
            if project_path:
                clauses.append("project_path = ?")
                parameters.append(str(Path(project_path).expanduser().resolve()))
            parameters.append(limit)
            return _rows(
                connection.execute(
                    f"""
                    SELECT
                        source,
                        session_id,
                        project_path,
                        timestamp,
                        message_role,
                        left(message_content, 1200) AS content
                    FROM read_conversations(path = ?, source = 'codex')
                    WHERE {' AND '.join(clauses)}
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    parameters,
                )
            )
