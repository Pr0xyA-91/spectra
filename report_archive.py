#!/usr/bin/env python3
"""
SPECTRA — Local Diagnostic Report Archive (SQLite WAL + FTS5 + Content-Addressed Blobs)
========================================================================================
Zero-dependency stdlib sqlite3 archive designed to scale cleanly to 15,000+ stored
diagnostic reports, service certificates, and capture bundles with sub-20ms indexed
lookups and sub-30ms FTS5 full-text search.
"""

import atexit
import hashlib
import math
import os
import queue
import re
import sqlite3
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


_ARCHIVE_DIR_OVERRIDE: Optional[str] = None
_WRITE_LOCK = threading.Lock()
_CONN_LOCK = threading.RLock()
_PERSISTENT_CONN: Optional[sqlite3.Connection] = None
_PERSISTENT_DB_PATH: str = ""
_INITIALIZED_DBS: set = set()
_MAX_ARCHIVE_ROWS_DEFAULT = 50000
_ARCHIVE_QUEUE_MAXSIZE = 256
_ARCHIVE_QUEUE: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=_ARCHIVE_QUEUE_MAXSIZE)
_ASYNC_WORKER_LOCK = threading.Lock()
_ASYNC_WORKER_THREAD: Optional[threading.Thread] = None


def _chmod_private_dir(path: str) -> None:
    if os.name != "nt" and path:
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass


def _chmod_private_file(path: str) -> None:
    if os.name != "nt" and path and os.path.exists(path):
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def get_archive_dir() -> str:
    """Return OS-appropriate local appdata directory for SPECTRA report archive."""
    if _ARCHIVE_DIR_OVERRIDE:
        os.makedirs(_ARCHIVE_DIR_OVERRIDE, exist_ok=True)
        _chmod_private_dir(_ARCHIVE_DIR_OVERRIDE)
        return _ARCHIVE_DIR_OVERRIDE

    if sys.platform.startswith("win") or os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "SPECTRA")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        path = os.path.join(base, "spectra")
    os.makedirs(path, exist_ok=True)
    _chmod_private_dir(path)
    return path


def get_archive_db_path(db_path: Optional[str] = None) -> str:
    if db_path:
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
            _chmod_private_dir(parent)
        return os.path.abspath(db_path)
    return os.path.join(get_archive_dir(), "reports_index.sqlite3")


def get_blobs_dir(db_path: Optional[str] = None) -> str:
    resolved_db = get_archive_db_path(db_path)
    blobs_dir = os.path.join(os.path.dirname(resolved_db), "reports_blobs")
    os.makedirs(blobs_dir, exist_ok=True)
    _chmod_private_dir(blobs_dir)
    return blobs_dir


def close_persistent_connection() -> None:
    """Close the cached persistent SQLite connection cleanly."""
    global _PERSISTENT_CONN, _PERSISTENT_DB_PATH
    with _CONN_LOCK:
        if _PERSISTENT_CONN is not None:
            try:
                _PERSISTENT_CONN.close()
            except Exception:
                pass
            _PERSISTENT_CONN = None
            _PERSISTENT_DB_PATH = ""


atexit.register(close_persistent_connection)


def _open_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    global _PERSISTENT_CONN, _PERSISTENT_DB_PATH
    resolved = get_archive_db_path(db_path)
    with _CONN_LOCK:
        if _PERSISTENT_CONN is not None and _PERSISTENT_DB_PATH == resolved:
            if resolved not in _INITIALIZED_DBS:
                _ensure_schema(_PERSISTENT_CONN)
                _INITIALIZED_DBS.add(resolved)
            return _PERSISTENT_CONN

        if _PERSISTENT_CONN is not None:
            try:
                _PERSISTENT_CONN.close()
            except Exception:
                pass
            _PERSISTENT_CONN = None
            _PERSISTENT_DB_PATH = ""

        if os.name != "nt" and not os.path.exists(resolved):
            try:
                fd = os.open(resolved, os.O_WRONLY | os.O_CREAT, 0o600)
                os.close(fd)
            except OSError:
                pass
        conn = sqlite3.connect(
            resolved,
            timeout=10.0,
            isolation_level="DEFERRED",
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA cache_size = -32000;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        if resolved not in _INITIALIZED_DBS:
            _ensure_schema(conn)
            _INITIALIZED_DBS.add(resolved)
        for sidecar in (resolved, f"{resolved}-wal", f"{resolved}-shm"):
            _chmod_private_file(sidecar)
        _PERSISTENT_CONN = conn
        _PERSISTENT_DB_PATH = resolved
        return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            report_type TEXT NOT NULL,
            ticket_prefix TEXT NOT NULL DEFAULT '',
            manufacturer TEXT NOT NULL DEFAULT '',
            model_name TEXT NOT NULL DEFAULT '',
            ef_code TEXT NOT NULL DEFAULT '',
            article_number TEXT NOT NULL DEFAULT '',
            serial_number TEXT NOT NULL DEFAULT '',
            total_cups INTEGER NOT NULL DEFAULT 0,
            health_score INTEGER,
            filename TEXT NOT NULL DEFAULT '',
            blob_sha256 TEXT NOT NULL DEFAULT '',
            blob_path TEXT NOT NULL DEFAULT '',
            summary_text TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_reports_serial_created
            ON reports (serial_number, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_reports_article_created
            ON reports (article_number, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_reports_ticket_created
            ON reports (ticket_prefix, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_reports_created_id
            ON reports (created_at DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_reports_blob_sha256
            ON reports (blob_sha256);

        CREATE VIRTUAL TABLE IF NOT EXISTS reports_fts USING fts5(
            ticket_prefix,
            manufacturer,
            model_name,
            ef_code,
            article_number,
            serial_number,
            filename,
            summary_text,
            content='reports',
            content_rowid='id',
            tokenize='unicode61'
        );

        CREATE TRIGGER IF NOT EXISTS reports_ai AFTER INSERT ON reports BEGIN
            INSERT INTO reports_fts(
                rowid, ticket_prefix, manufacturer, model_name, ef_code,
                article_number, serial_number, filename, summary_text
            ) VALUES (
                new.id, new.ticket_prefix, new.manufacturer, new.model_name, new.ef_code,
                new.article_number, new.serial_number, new.filename, new.summary_text
            );
        END;

        CREATE TRIGGER IF NOT EXISTS reports_ad AFTER DELETE ON reports BEGIN
            INSERT INTO reports_fts(
                reports_fts, rowid, ticket_prefix, manufacturer, model_name, ef_code,
                article_number, serial_number, filename, summary_text
            ) VALUES (
                'delete', old.id, old.ticket_prefix, old.manufacturer, old.model_name, old.ef_code,
                old.article_number, old.serial_number, old.filename, old.summary_text
            );
        END;

        CREATE TRIGGER IF NOT EXISTS reports_au AFTER UPDATE ON reports BEGIN
            INSERT INTO reports_fts(
                reports_fts, rowid, ticket_prefix, manufacturer, model_name, ef_code,
                article_number, serial_number, filename, summary_text
            ) VALUES (
                'delete', old.id, old.ticket_prefix, old.manufacturer, old.model_name, old.ef_code,
                old.article_number, old.serial_number, old.filename, old.summary_text
            );
            INSERT INTO reports_fts(
                rowid, ticket_prefix, manufacturer, model_name, ef_code,
                article_number, serial_number, filename, summary_text
            ) VALUES (
                new.id, new.ticket_prefix, new.manufacturer, new.model_name, new.ef_code,
                new.article_number, new.serial_number, new.filename, new.summary_text
            );
        END;
        """
    )
    conn.commit()


def init_archive(db_path: Optional[str] = None) -> str:
    """Ensure schema and WAL mode are initialized for the archive database."""
    resolved = get_archive_db_path(db_path)
    _INITIALIZED_DBS.discard(resolved)
    with _WRITE_LOCK, _CONN_LOCK:
        conn = _open_connection(resolved)
        _ensure_schema(conn)
        _INITIALIZED_DBS.add(resolved)
    return resolved


def store_blob(content: Any, ext: str = "json", db_path: Optional[str] = None) -> Tuple[str, str]:
    """
    Persist immutable content-addressed blob under reports_blobs/<sha[:2]>/<sha>.<ext>
    with owner-only permissions (0o700 dirs / 0o600 files on POSIX).
    Returns (sha256_hex, absolute_blob_path).
    """
    if isinstance(content, bytes):
        raw = content
    else:
        raw = str(content or "").encode("utf-8")

    sha = hashlib.sha256(raw).hexdigest()
    clean_ext = re.sub(r"[^a-zA-Z0-9]", "", str(ext or "bin").lstrip("."))[:10] or "bin"
    blobs_root = get_blobs_dir(db_path)
    shard_dir = os.path.join(blobs_root, sha[:2])
    os.makedirs(shard_dir, exist_ok=True)
    _chmod_private_dir(shard_dir)
    blob_path = os.path.join(shard_dir, f"{sha}.{clean_ext}")
    if not os.path.isfile(blob_path):
        tmp_path = f"{blob_path}.tmp.{os.getpid()}.{threading.get_ident()}"
        if os.name != "nt":
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
            _chmod_private_file(tmp_path)
        else:
            with open(tmp_path, "wb") as f:
                f.write(raw)
        try:
            os.replace(tmp_path, blob_path)
            _chmod_private_file(blob_path)
        except OSError:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
    else:
        _chmod_private_file(blob_path)
    return sha, blob_path


def _normalize_record(record: Dict[str, Any], db_path: Optional[str] = None) -> Tuple[Any, ...]:
    raw_ts = record.get("created_at")
    try:
        created_at = float(raw_ts) if raw_ts is not None else time.time()
        if not math.isfinite(created_at):
            created_at = time.time()
    except (TypeError, ValueError):
        created_at = time.time()
    report_type = str(record.get("report_type") or "export")
    ticket_prefix = str(record.get("ticket_prefix") or "")
    manufacturer = str(record.get("manufacturer") or "")
    model_name = str(record.get("model_name") or "")
    ef_code = str(record.get("ef_code") or "")
    article_number = str(record.get("article_number") or "")
    serial_number = str(record.get("serial_number") or "")
    try:
        total_cups = int(record.get("total_cups") or 0)
    except (TypeError, ValueError):
        total_cups = 0
    raw_hs = record.get("health_score")
    try:
        health_score = int(raw_hs) if raw_hs is not None else None
    except (TypeError, ValueError):
        health_score = None
    filename = str(record.get("filename") or "")
    blob_sha = str(record.get("blob_sha256") or "")
    blob_path = str(record.get("blob_path") or "")
    if "content" in record and record["content"] is not None and not blob_sha:
        ext = str(record.get("ext") or os.path.splitext(filename)[1].lstrip(".") or "json")
        blob_sha, blob_path = store_blob(record["content"], ext=ext, db_path=db_path)
    summary_text = str(record.get("summary_text") or "")
    return (
        created_at,
        report_type,
        ticket_prefix,
        manufacturer,
        model_name,
        ef_code,
        article_number,
        serial_number,
        total_cups,
        health_score,
        filename,
        blob_sha,
        blob_path,
        summary_text,
    )


def _get_max_archive_rows() -> int:
    try:
        val = int(os.environ.get("SPECTRA_ARCHIVE_MAX_ROWS", str(_MAX_ARCHIVE_ROWS_DEFAULT)))
        return max(100, val)
    except (TypeError, ValueError):
        return _MAX_ARCHIVE_ROWS_DEFAULT


def _prune_excess_rows(conn: sqlite3.Connection, max_rows: int) -> int:
    """Delete oldest archived rows beyond max_rows and unlink unreferenced blob files."""
    total = int(conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0])
    excess = total - max_rows
    if excess <= 0:
        return 0
    old_rows = conn.execute(
        "SELECT id, blob_sha256, blob_path FROM reports ORDER BY created_at ASC, id ASC LIMIT ?",
        (excess,),
    ).fetchall()
    if not old_rows:
        return 0
    ids = [(int(r["id"]),) for r in old_rows]
    conn.executemany("DELETE FROM reports WHERE id = ?", ids)
    conn.commit()
    for r in old_rows:
        sha = str(r["blob_sha256"] or "")
        bpath = str(r["blob_path"] or "")
        if sha and bpath and os.path.isfile(bpath):
            still_used = conn.execute(
                "SELECT 1 FROM reports WHERE blob_sha256 = ? LIMIT 1",
                (sha,),
            ).fetchone()
            if not still_used:
                try:
                    os.remove(bpath)
                except OSError:
                    pass
    return len(old_rows)


def archive_report(
    report_type: str,
    *,
    content: Optional[Any] = None,
    ext: str = "json",
    ticket_prefix: str = "",
    manufacturer: str = "",
    model_name: str = "",
    ef_code: str = "",
    article_number: str = "",
    serial_number: str = "",
    total_cups: int = 0,
    health_score: Optional[int] = None,
    filename: str = "",
    summary_text: str = "",
    created_at: Optional[float] = None,
    db_path: Optional[str] = None,
) -> int:
    """Archive a single diagnostic report or certificate and return its row ID."""
    row = _normalize_record(
        {
            "created_at": created_at,
            "report_type": report_type,
            "ticket_prefix": ticket_prefix,
            "manufacturer": manufacturer,
            "model_name": model_name,
            "ef_code": ef_code,
            "article_number": article_number,
            "serial_number": serial_number,
            "total_cups": total_cups,
            "health_score": health_score,
            "filename": filename,
            "content": content,
            "ext": ext,
            "summary_text": summary_text,
        },
        db_path=db_path,
    )
    with _WRITE_LOCK, _CONN_LOCK:
        conn = _open_connection(db_path)
        cur = conn.execute(
            """
            INSERT INTO reports (
                created_at, report_type, ticket_prefix, manufacturer,
                model_name, ef_code, article_number, serial_number,
                total_cups, health_score, filename, blob_sha256,
                blob_path, summary_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()
        row_id = int(cur.lastrowid or 0)
        max_rows = _get_max_archive_rows()
        if row_id % 100 == 0 or max_rows <= 1000:
            _prune_excess_rows(conn, max_rows)
        return row_id


def archive_reports_batch(
    records: List[Dict[str, Any]],
    db_path: Optional[str] = None,
) -> int:
    """Batch-insert diagnostic reports inside a single SQLite transaction."""
    if not records:
        return 0
    rows = [_normalize_record(rec, db_path=db_path) for rec in records]
    with _WRITE_LOCK, _CONN_LOCK:
        conn = _open_connection(db_path)
        with conn:
            conn.executemany(
                """
                INSERT INTO reports (
                    created_at, report_type, ticket_prefix, manufacturer,
                    model_name, ef_code, article_number, serial_number,
                    total_cups, health_score, filename, blob_sha256,
                    blob_path, summary_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)


def _build_fts_query(raw_query: str) -> str:
    """Build a safe Unicode-aware FTS5 prefix MATCH expression (preserves Czech/German diacritics)."""
    tokens = re.findall(r"[\w.\-]+", str(raw_query or "").strip(), flags=re.UNICODE)
    cleaned = [tok.replace('"', "") for tok in tokens if tok.replace('"', "")]
    if not cleaned:
        return ""
    return " AND ".join(f'"{tok}"*' for tok in cleaned[:8])


def _parse_cursor(cursor: Optional[str]) -> Optional[Tuple[float, int]]:
    if not cursor:
        return None
    raw = str(cursor).strip()
    if ":" not in raw:
        return None
    ts_part, id_part = raw.split(":", 1)
    try:
        ts = float(ts_part)
        rid = int(id_part)
    except ValueError:
        return None
    if not math.isfinite(ts) or rid < 0:
        return None
    return ts, rid


def search_reports(
    query: Optional[str] = None,
    serial_number: Optional[str] = None,
    article_number: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
    db_path: Optional[str] = None,
    include_blob_path: bool = False,
) -> Dict[str, Any]:
    """
    Search archived reports using composite indexes and FTS5 with keyset cursor pagination.
    Returns {"items": [...], "next_cursor": Optional[str], "count": int}.
    Omits raw local `blob_path` by default to prevent local filesystem path disclosure.
    """
    lim = max(1, min(200, int(limit or 50)))
    where_clauses: List[str] = []
    params: List[Any] = []
    from_sql = "FROM reports r"

    fts_expr = _build_fts_query(query or "")
    if fts_expr:
        from_sql = "FROM reports r JOIN reports_fts fts ON fts.rowid = r.id"
        where_clauses.append("reports_fts MATCH ?")
        params.append(fts_expr)

    if serial_number:
        where_clauses.append("r.serial_number = ?")
        params.append(str(serial_number).strip())

    if article_number:
        where_clauses.append("r.article_number = ?")
        params.append(str(article_number).strip())

    parsed_cursor = _parse_cursor(cursor)
    if parsed_cursor is not None:
        c_ts, c_id = parsed_cursor
        where_clauses.append("(r.created_at < ? OR (r.created_at = ? AND r.id < ?))")
        params.extend([c_ts, c_ts, c_id])

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    sql = (
        f"SELECT r.id, r.created_at, r.report_type, r.ticket_prefix, r.manufacturer, "
        f"r.model_name, r.ef_code, r.article_number, r.serial_number, r.total_cups, "
        f"r.health_score, r.filename, r.blob_sha256, r.blob_path, r.summary_text "
        f"{from_sql} {where_sql} "
        f"ORDER BY r.created_at DESC, r.id DESC LIMIT ?"
    )
    params.append(lim + 1)

    with _CONN_LOCK:
        conn = _open_connection(db_path)
        rows = conn.execute(sql, params).fetchall()

    has_more = len(rows) > lim
    page_rows = rows[:lim]
    items: List[Dict[str, Any]] = []
    for row in page_rows:
        item = dict(row)
        item["has_blob"] = bool(item.get("blob_sha256"))
        if not include_blob_path:
            item.pop("blob_path", None)
        items.append(item)
    next_cursor = (
        f"{items[-1]['created_at']}:{items[-1]['id']}"
        if has_more and items
        else None
    )
    return {
        "items": items,
        "next_cursor": next_cursor,
        "count": len(items),
    }


def _async_archive_loop() -> None:
    while True:
        item = _ARCHIVE_QUEUE.get()
        try:
            archive_report(**item)
        except Exception:
            pass
        finally:
            _ARCHIVE_QUEUE.task_done()


def _ensure_async_worker() -> None:
    global _ASYNC_WORKER_THREAD
    with _ASYNC_WORKER_LOCK:
        if _ASYNC_WORKER_THREAD is not None and _ASYNC_WORKER_THREAD.is_alive():
            return
        t = threading.Thread(target=_async_archive_loop, daemon=True, name="SpectraReportArchiveWorker")
        t.start()
        _ASYNC_WORKER_THREAD = t


def archive_report_async(**kwargs: Any) -> bool:
    """Bounded non-blocking report archival helper using a single persistent worker queue."""
    _ensure_async_worker()
    try:
        _ARCHIVE_QUEUE.put_nowait(dict(kwargs))
        return True
    except queue.Full:
        return False
