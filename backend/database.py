from __future__ import annotations

import json
import os
import sqlite3
import stat
from contextlib import closing
from typing import Any, Iterator

import config
from services.param_maps import DUAL_REPAIR_PARAM_KEYS, SINGLE_REPAIR_PARAM_KEYS

TaskDict = dict[str, Any]

SCHEMA_VERSION = 1

_ALLOWED_TASK_COLUMNS = {
    "status", "progress", "step", "original_filename", "original_path",
    "file_hash", "file_size", "output_path", "params", "detection_result",
    "repaired_detection_result", "repair_result", "error",
    "render_filename", "render_result"
}

_TASK_TABLE_COLUMNS = {
    "id", "status", "progress", "step", "original_filename", "original_path",
    "file_hash", "file_size", "output_path", "params", "detection_result",
    "repaired_detection_result", "repair_result", "error",
    "render_filename", "render_result", "created_at", "updated_at"
}

assert _ALLOWED_TASK_COLUMNS.issubset(_TASK_TABLE_COLUMNS), \
    "_ALLOWED_TASK_COLUMNS 包含不存在的列"


def _set_db_file_permissions(db_path: str) -> None:
    if os.path.exists(db_path):
        try:
            os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    return conn


def checkpoint_db(mode: str = "PASSIVE") -> None:
    with closing(get_db()) as conn:
        conn.execute(f"PRAGMA wal_checkpoint({mode})")
        conn.commit()


def _get_schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
        return row["version"] if row else 0
    except sqlite3.OperationalError:
        return 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO schema_version (id, version) VALUES (1, ?)",
        (version,)
    )


def _migrate_v1(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            progress REAL NOT NULL DEFAULT 0,
            step TEXT NOT NULL DEFAULT '',
            original_filename TEXT NOT NULL DEFAULT '',
            original_path TEXT NOT NULL DEFAULT '',
            file_hash TEXT NOT NULL DEFAULT '',
            file_size INTEGER NOT NULL DEFAULT 0,
            output_path TEXT NOT NULL DEFAULT '',
            params TEXT NOT NULL DEFAULT '{}',
            detection_result TEXT,
            repaired_detection_result TEXT,
            repair_result TEXT,
            error TEXT,
            render_filename TEXT,
            render_result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analysis_cache (
            quick_hash TEXT PRIMARY KEY,
            file_name TEXT NOT NULL DEFAULT '',
            file_size INTEGER NOT NULL DEFAULT 0,
            wav_info TEXT NOT NULL DEFAULT '',
            analysis TEXT NOT NULL DEFAULT '',
            waveform_peaks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_file_hash ON tasks(file_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status_created_at ON tasks(status, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_analysis_cache_file_size ON analysis_cache(file_size)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_analysis_cache_created_at ON analysis_cache(created_at)")


_MIGRATIONS = [
    _migrate_v1,
]


def init_db() -> None:
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    with closing(get_db()) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=1000")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY,
                version INTEGER NOT NULL DEFAULT 0
            )
        """)
        current_version = _get_schema_version(conn)
        for i in range(current_version, len(_MIGRATIONS)):
            _MIGRATIONS[i](conn)
        _set_schema_version(conn, len(_MIGRATIONS))
        conn.commit()
    _set_db_file_permissions(config.DB_PATH)

def cleanup_stale_tasks() -> int:
    import logging
    logger = logging.getLogger(__name__)
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        stale_statuses = ('pending', 'processing', 'detecting', 'analyzing', 'repairing', 'rendering')
        cursor = conn.execute(
            "UPDATE tasks SET status = 'error', error = '服务器重启，任务中断', progress = 0, "
            "step = '任务已中断', updated_at = CURRENT_TIMESTAMP WHERE status IN ({})".format(
                ','.join('?' * len(stale_statuses))
            ),
            stale_statuses,
        )
        count = cursor.rowcount
        if count > 0:
            logger.info(f"[cleanup_stale_tasks] 标记 {count} 个停滞任务为失败")
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_task(task_id: str, filename: str, filepath: str, params: dict[str, Any], file_hash: str = "", file_size: int = 0) -> None:
    with closing(get_db()) as conn:
        conn.execute(
            "INSERT INTO tasks (id, original_filename, original_path, params, file_hash, file_size) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, filename, filepath, json.dumps(params), file_hash, file_size)
        )
        conn.commit()

def _convert_to_json_serializable(obj: Any) -> Any:
    """将 numpy 类型和其他不可序列化类型转换为 JSON 可序列化类型"""
    import numpy as np
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _convert_to_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_to_json_serializable(v) for v in obj]
    return obj


def update_task(task_id: str, **kwargs: Any) -> None:
    with closing(get_db()) as conn:
        sets: list[str] = []
        values: list[Any] = []
        for k, v in kwargs.items():
            if k not in _ALLOWED_TASK_COLUMNS:
                raise ValueError(f"不允许更新的字段: {k}")
            sets.append(f"{k} = ?")
            if isinstance(v, (dict, list)):
                serializable_v = _convert_to_json_serializable(v)
                values.append(json.dumps(serializable_v))
            else:
                values.append(v)
        sets.append("updated_at = CURRENT_TIMESTAMP")
        values.append(task_id)
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", values)
        conn.commit()

def get_task(task_id: str) -> TaskDict | None:
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    result: TaskDict = dict(row)
    for ts_field in ("created_at", "updated_at", "completed_at"):
        if ts_field in result:
            result[ts_field] = _format_timestamp(result[ts_field])
    _parse_json_fields(result)
    _enrich_output_size(result)
    return result

def find_task_by_hash(file_hash: str) -> TaskDict | None:
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE file_hash = ? ORDER BY created_at DESC LIMIT 1",
            (file_hash,)
        ).fetchone()
    if row is None:
        return None
    result: TaskDict = dict(row)
    if result.get("original_path") and not os.path.exists(result["original_path"]):
        return None
    output_path = result.get("output_path")
    if output_path and not os.path.exists(output_path):
        result["output_path"] = ""
    _parse_json_fields(result)
    _enrich_output_size(result)
    return result

def find_dual_task_by_hashes(vocal_file_hash: str, accompaniment_file_hash: str) -> TaskDict | None:
    with closing(get_db()) as conn:
        row = conn.execute(
            """
            SELECT * FROM tasks 
            WHERE original_filename LIKE 'dual_%'
              AND json_extract(params, '$.vocal_file_hash') = ?
              AND json_extract(params, '$.accompaniment_file_hash') = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (vocal_file_hash, accompaniment_file_hash)
        ).fetchone()
    if row is None:
        return None
    result: TaskDict = dict(row)
    if result.get("original_path") and not os.path.exists(result["original_path"]):
        return None
    output_path = result.get("output_path")
    if output_path and not os.path.exists(output_path):
        result["output_path"] = ""
    _parse_json_fields(result)
    _enrich_output_size(result)
    return result

def find_repair_cache(file_hash: str, params: dict) -> TaskDict | None:
    import logging
    logger = logging.getLogger(__name__)

    where_clauses = [
        "file_hash = ?",
        "status = 'completed'",
        "output_path != ''",
        "json_extract(params, '$.processing_mode') != 'dual' OR json_extract(params, '$.processing_mode') IS NULL"
    ]
    query_values: list[Any] = [file_hash]

    for key in sorted(SINGLE_REPAIR_PARAM_KEYS):
        if key in params:
            where_clauses.append(f"json_extract(params, '$.{key}') = json(?)")
            query_values.append(json.dumps(params[key], ensure_ascii=False))

    sql = (
        "SELECT * FROM tasks WHERE "
        + " AND ".join(where_clauses)
        + " ORDER BY updated_at DESC LIMIT 1"
    )

    with closing(get_db()) as conn:
        row = conn.execute(sql, query_values).fetchone()

    if row is None:
        logger.info(f"[cache-lookup] ❌ NO MATCH for hash={file_hash}")
        return None

    result: TaskDict = dict(row)
    output_path = result.get("output_path")

    if not output_path or not os.path.exists(output_path):
        logger.info(f"[cache-lookup] hash={file_hash} SKIP: output_path not found")
        return None

    try:
        size = os.path.getsize(output_path)
    except OSError as e:
        logger.info(f"[cache-lookup] hash={file_hash} SKIP: getsize error {e}")
        return None

    if size < 10240:
        logger.info(f"[cache-lookup] hash={file_hash} SKIP: too small {size}B")
        return None

    logger.info(f"[cache-lookup] ✅ MATCH id={result.get('id')} size={size}")
    result["output_size"] = size
    _parse_json_fields(result)
    return result

def find_dual_repair_cache(vocal_file_hash: str, accompaniment_file_hash: str, params: dict) -> TaskDict | None:
    import logging
    logger = logging.getLogger(__name__)

    where_clauses = [
        "json_extract(params, '$.processing_mode') = 'dual'",
        "status = 'completed'",
        "output_path != ''",
        "json_extract(params, '$.vocal_file_hash') = ?",
        "json_extract(params, '$.accompaniment_file_hash') = ?"
    ]
    query_values: list[Any] = [vocal_file_hash, accompaniment_file_hash]

    for key in sorted(DUAL_REPAIR_PARAM_KEYS):
        if key in params:
            where_clauses.append(f"json_extract(params, '$.{key}') = json(?)")
            query_values.append(json.dumps(params[key], ensure_ascii=False))

    sql = (
        "SELECT * FROM tasks WHERE "
        + " AND ".join(where_clauses)
        + " ORDER BY updated_at DESC LIMIT 1"
    )

    with closing(get_db()) as conn:
        row = conn.execute(sql, query_values).fetchone()

    if row is None:
        logger.info(f"[cache-lookup-dual] NO MATCH for vocal_hash={vocal_file_hash} acc_hash={accompaniment_file_hash}")
        return None

    result: TaskDict = dict(row)
    output_path = result.get("output_path")

    if not output_path or not os.path.exists(output_path):
        logger.info(f"[cache-lookup-dual] vocal_hash={vocal_file_hash} SKIP: output_path not found")
        return None

    try:
        size = os.path.getsize(output_path)
    except OSError as e:
        logger.info(f"[cache-lookup-dual] vocal_hash={vocal_file_hash} SKIP: getsize error {e}")
        return None

    if size < 10240:
        logger.info(f"[cache-lookup-dual] vocal_hash={vocal_file_hash} SKIP: too small {size}B")
        return None

    logger.info(f"[cache-lookup-dual] ✅ MATCH id={result.get('id')} size={size}")
    result["output_size"] = size
    _parse_json_fields(result)
    return result

def get_all_tasks_ordered() -> list[TaskDict]:
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT id, original_path, output_path, file_size, created_at FROM tasks ORDER BY created_at ASC").fetchall()
    return [dict(r) for r in rows]


def get_tasks_paginated(limit: int = 100, offset: int = 0) -> list[TaskDict]:
    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT id, original_path, output_path, file_size, created_at FROM tasks ORDER BY created_at ASC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
    return [dict(r) for r in rows]


def iter_tasks_batch(batch_size: int = 100) -> Iterator[list[TaskDict]]:
    offset = 0
    while True:
        batch = get_tasks_paginated(limit=batch_size, offset=offset)
        if not batch:
            break
        yield batch
        offset += len(batch)
        if len(batch) < batch_size:
            break

def delete_task(task_id: str) -> None:
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()


def get_queue_status() -> dict[str, Any]:
    """获取任务队列状态"""
    with closing(get_db()) as conn:
        status_counts = conn.execute(
            "SELECT status, COUNT(*) as count FROM tasks GROUP BY status"
        ).fetchall()
        
        running_tasks = conn.execute(
            """SELECT id, status, step, progress, 
                      (julianday('now') - julianday(updated_at)) * 24 * 60 * 60 as elapsed_seconds
               FROM tasks 
               WHERE status IN ('detecting', 'repairing', 'rendering') 
               ORDER BY updated_at DESC"""
        ).fetchall()
        
        pending_tasks = conn.execute(
            "SELECT id, status, original_filename FROM tasks WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
    
    return {
        'status_counts': {row['status']: row['count'] for row in status_counts},
        'running': [
            {
                'id': row['id'],
                'status': row['status'],
                'step': row['step'],
                'progress': row['progress'],
                'elapsed_seconds': int(row['elapsed_seconds']) if row['elapsed_seconds'] else 0
            }
            for row in running_tasks
        ],
        'pending': [
            {'id': row['id'], 'filename': row['original_filename']}
            for row in pending_tasks
        ],
        'queue_length': len(pending_tasks)
    }


def mark_stuck_tasks(timeout_seconds: int = 300) -> None:
    """标记卡住的任务（超过timeout_seconds没有更新）"""
    with closing(get_db()) as conn:
        conn.execute(
            """UPDATE tasks 
               SET status = 'timeout', 
                   step = '任务执行超时，请重试',
                   error = 'Task execution timeout'
               WHERE status IN ('detecting', 'repairing', 'rendering') 
               AND (julianday('now') - julianday(updated_at)) * 24 * 60 * 60 > ?""",
            (timeout_seconds,)
        )
        conn.commit()


def get_analysis_cache(quick_hash: str) -> dict[str, Any] | None:
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM analysis_cache WHERE quick_hash = ?", (quick_hash,)).fetchone()
    if row is None:
        return None
    return dict(row)

def save_analysis_cache(quick_hash: str, file_name: str, file_size: int, wav_info: str, analysis: str, waveform_peaks: str = "") -> None:
    with closing(get_db()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO analysis_cache (quick_hash, file_name, file_size, wav_info, analysis, waveform_peaks) VALUES (?, ?, ?, ?, ?, ?)",
            (quick_hash, file_name, file_size, wav_info, analysis, waveform_peaks),
        )
        conn.commit()

def get_all_analysis_cache() -> list[dict[str, Any]]:
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT * FROM analysis_cache ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_analysis_cache_paginated(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT * FROM analysis_cache ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
    return [dict(r) for r in rows]


def iter_analysis_cache_batch(batch_size: int = 100) -> Iterator[list[dict[str, Any]]]:
    offset = 0
    while True:
        batch = get_analysis_cache_paginated(limit=batch_size, offset=offset)
        if not batch:
            break
        yield batch
        offset += len(batch)
        if len(batch) < batch_size:
            break


def cleanup_expired_analysis_cache(max_age_days: int = 30) -> int:
    with closing(get_db()) as conn:
        cursor = conn.execute(
            "DELETE FROM analysis_cache WHERE julianday('now') - julianday(created_at) > ?",
            (max_age_days,)
        )
        conn.commit()
        return cursor.rowcount


def delete_analysis_cache(quick_hash: str) -> None:
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM analysis_cache WHERE quick_hash = ?", (quick_hash,))
        conn.commit()

def clear_all_analysis_cache() -> int:
    with closing(get_db()) as conn:
        count = conn.execute("SELECT COUNT(*) FROM analysis_cache").fetchone()[0]
        conn.execute("DELETE FROM analysis_cache")
        conn.commit()
    return count


def _format_timestamp(ts: str | None) -> str | None:
    if ts is None:
        return None
    ts_str = str(ts).replace(" ", "T")
    if not ts_str.endswith("Z") and "+" not in ts_str and "Z" not in ts_str:
        ts_str += "Z"
    return ts_str


def _parse_json_fields(result: TaskDict) -> None:
    for field in ("params", "detection_result", "repaired_detection_result", "repair_result"):
        raw = result.get(field)
        if raw and isinstance(raw, str):
            try:
                result[field] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass


def _enrich_output_size(result: TaskDict) -> None:
    output_path = result.get("output_path")
    if output_path and os.path.exists(output_path):
        try:
            result["output_size"] = os.path.getsize(output_path)
        except OSError:
            result["output_size"] = 0
    else:
        result["output_size"] = 0


# 训练素材相关数据库操作
TRAINING_DB_PATH = os.path.join(os.path.dirname(config.DB_PATH), "training.db")


def get_training_db() -> sqlite3.Connection:
    conn = sqlite3.connect(TRAINING_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    return conn


def checkpoint_training_db(mode: str = "PASSIVE") -> None:
    with closing(get_training_db()) as conn:
        conn.execute(f"PRAGMA wal_checkpoint({mode})")
        conn.commit()


def init_training_db() -> None:
    os.makedirs(os.path.dirname(TRAINING_DB_PATH), exist_ok=True)
    with closing(get_training_db()) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=1000")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS training_files (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                file_hash TEXT NOT NULL UNIQUE,
                file_size INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    _set_db_file_permissions(TRAINING_DB_PATH)

def create_training_record(file_id: str, filename: str, filepath: str, file_hash: str, file_size: int = 0) -> None:
    with closing(get_training_db()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO training_files (id, filename, filepath, file_hash, file_size) VALUES (?, ?, ?, ?, ?)",
            (file_id, filename, filepath, file_hash, file_size)
        )
        conn.commit()

def find_training_by_hash(file_hash: str) -> TaskDict | None:
    with closing(get_training_db()) as conn:
        row = conn.execute(
            "SELECT * FROM training_files WHERE file_hash = ? LIMIT 1",
            (file_hash,)
        ).fetchone()
    if row is None:
        return None
    result: TaskDict = dict(row)
    if result.get("filepath") and not os.path.exists(result["filepath"]):
        return None
    return result
