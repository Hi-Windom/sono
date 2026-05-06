import sqlite3
import json
import os
from config import DB_PATH

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN file_hash TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass
    conn.commit()
    conn.close()

def create_task(task_id: str, filename: str, filepath: str, params: dict, file_hash: str = "", file_size: int = 0):
    conn = get_db()
    conn.execute(
        "INSERT INTO tasks (id, original_filename, original_path, params, file_hash, file_size) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, filename, filepath, json.dumps(params), file_hash, file_size)
    )
    conn.commit()
    conn.close()

def update_task(task_id: str, **kwargs):
    conn = get_db()
    sets = []
    values = []
    for k, v in kwargs.items():
        sets.append(f"{k} = ?")
        values.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
    sets.append("updated_at = CURRENT_TIMESTAMP")
    values.append(task_id)
    conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", values)
    conn.commit()
    conn.close()

def get_task(task_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    if result.get("params"):
        result["params"] = json.loads(result["params"])
    if result.get("detection_result"):
        result["detection_result"] = json.loads(result["detection_result"])
    if result.get("repaired_detection_result"):
        result["repaired_detection_result"] = json.loads(result["repaired_detection_result"])
    if result.get("repair_result"):
        result["repair_result"] = json.loads(result["repair_result"])
    return result

def find_task_by_hash(file_hash: str) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM tasks WHERE file_hash = ? ORDER BY created_at DESC LIMIT 1",
        (file_hash,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    if result.get("original_path") and not os.path.exists(result["original_path"]):
        return None
    if result.get("params"):
        result["params"] = json.loads(result["params"])
    return result

def get_all_tasks_ordered() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT id, original_path, output_path, file_size, created_at FROM tasks ORDER BY created_at ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_task(task_id: str):
    conn = get_db()
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


def get_queue_status() -> dict:
    """获取任务队列状态"""
    conn = get_db()
    
    # 统计各状态任务数
    status_counts = conn.execute(
        "SELECT status, COUNT(*) as count FROM tasks GROUP BY status"
    ).fetchall()
    
    # 获取正在运行的任务
    running_tasks = conn.execute(
        """SELECT id, status, step, progress, 
                  (julianday('now') - julianday(updated_at)) * 24 * 60 * 60 as elapsed_seconds
           FROM tasks 
           WHERE status IN ('detecting', 'repairing') 
           ORDER BY updated_at DESC"""
    ).fetchall()
    
    # 获取等待中的任务
    pending_tasks = conn.execute(
        "SELECT id, status, original_filename FROM tasks WHERE status = 'pending' ORDER BY created_at"
    ).fetchall()
    
    conn.close()
    
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


def mark_stuck_tasks(timeout_seconds: int = 300):
    """标记卡住的任务（超过timeout_seconds没有更新）"""
    conn = get_db()
    conn.execute(
        """UPDATE tasks 
           SET status = 'timeout', 
               step = '任务执行超时，请重试',
               error = 'Task execution timeout'
           WHERE status IN ('detecting', 'repairing') 
           AND (julianday('now') - julianday(updated_at)) * 24 * 60 * 60 > ?""",
        (timeout_seconds,)
    )
    conn.commit()
    conn.close()

# 训练素材相关数据库操作
TRAINING_DB_PATH = os.path.join(os.path.dirname(DB_PATH), "training.db")

def get_training_db():
    conn = sqlite3.connect(TRAINING_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_training_db():
    conn = get_training_db()
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
    conn.close()

def create_training_record(file_id: str, filename: str, filepath: str, file_hash: str, file_size: int = 0):
    conn = get_training_db()
    conn.execute(
        "INSERT OR REPLACE INTO training_files (id, filename, filepath, file_hash, file_size) VALUES (?, ?, ?, ?, ?)",
        (file_id, filename, filepath, file_hash, file_size)
    )
    conn.commit()
    conn.close()

def find_training_by_hash(file_hash: str) -> dict | None:
    conn = get_training_db()
    row = conn.execute(
        "SELECT * FROM training_files WHERE file_hash = ? LIMIT 1",
        (file_hash,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    # 检查文件是否还存在
    if result.get("filepath") and not os.path.exists(result["filepath"]):
        return None
    return result
