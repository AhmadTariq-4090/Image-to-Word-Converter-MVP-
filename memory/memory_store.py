import hashlib
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path


class MemoryStore:
    """
    Persistent SQLite-backed memory for the agentic system.

    Tables:
      sessions           – one row per conversion session
      corrections        – user-submitted text corrections
      engine_preferences – learned per-content-type engine preferences
      processing_logs    – INFO / WARNING / ERROR log lines
    """

    DB_PATH = Path("agent_memory.db")

    def __init__(self):
        self.conn = sqlite3.connect(str(self.DB_PATH), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._bootstrap()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _bootstrap(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id              TEXT PRIMARY KEY,
                timestamp       TEXT NOT NULL,
                image_count     INTEGER,
                engine_used     TEXT,
                quality_score   REAL,
                content_type    TEXT,
                processing_time REAL,
                confidence      REAL
            );

            CREATE TABLE IF NOT EXISTS corrections (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      TEXT,
                image_hash      TEXT,
                original_text   TEXT,
                corrected_text  TEXT,
                timestamp       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS engine_preferences (
                content_type    TEXT PRIMARY KEY,
                preferred_engine TEXT,
                satisfaction_avg REAL DEFAULT 0.5,
                usage_count     INTEGER DEFAULT 0,
                last_updated    TEXT
            );

            CREATE TABLE IF NOT EXISTS processing_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT,
                timestamp   TEXT NOT NULL,
                level       TEXT,
                message     TEXT
            );
        """)
        self.conn.commit()

    # ── Session ───────────────────────────────────────────────────────────────

    def new_session_id(self) -> str:
        return str(uuid.uuid4())[:8]

    def save_session(self, session_id: str, image_count: int, engine_used: str,
                     quality_score: float, content_type: str,
                     processing_time: float, confidence: float):
        self.conn.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?)",
            (session_id, datetime.now().isoformat(), image_count, engine_used,
             quality_score, content_type, processing_time, confidence)
        )
        self.conn.commit()

    def get_recent_sessions(self, limit: int = 10) -> list:
        rows = self.conn.execute(
            "SELECT id, timestamp, engine_used, quality_score, content_type, confidence "
            "FROM sessions ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Corrections ───────────────────────────────────────────────────────────

    def save_correction(self, session_id: str, image_hash: str,
                        original_text: str, corrected_text: str):
        self.conn.execute(
            "INSERT INTO corrections "
            "(session_id, image_hash, original_text, corrected_text, timestamp) "
            "VALUES (?,?,?,?,?)",
            (session_id, image_hash, original_text, corrected_text,
             datetime.now().isoformat())
        )
        self.conn.commit()

    # ── Engine preferences ────────────────────────────────────────────────────

    def update_engine_preference(self, content_type: str, engine: str,
                                  satisfaction: float):
        existing = self.conn.execute(
            "SELECT satisfaction_avg, usage_count FROM engine_preferences "
            "WHERE content_type=?", (content_type,)
        ).fetchone()

        if existing:
            old_avg, count = existing["satisfaction_avg"], existing["usage_count"]
            new_avg   = (old_avg * count + satisfaction) / (count + 1)
            new_count = count + 1
            # Flip preferred engine if this interaction was bad
            preferred = engine if satisfaction >= 0.5 else (
                "gemini" if engine == "tesseract" else "tesseract"
            )
            self.conn.execute(
                "UPDATE engine_preferences "
                "SET preferred_engine=?, satisfaction_avg=?, usage_count=?, last_updated=? "
                "WHERE content_type=?",
                (preferred, round(new_avg, 3), new_count,
                 datetime.now().isoformat(), content_type)
            )
        else:
            self.conn.execute(
                "INSERT INTO engine_preferences VALUES (?,?,?,?,?)",
                (content_type, engine, round(satisfaction, 3), 1,
                 datetime.now().isoformat())
            )
        self.conn.commit()

    def get_engine_preferences(self) -> dict:
        rows = self.conn.execute(
            "SELECT content_type, preferred_engine, satisfaction_avg, usage_count "
            "FROM engine_preferences"
        ).fetchall()
        return {
            row["content_type"]: {
                "preferred_engine": row["preferred_engine"],
                "confidence":       row["satisfaction_avg"],
                "usage_count":      row["usage_count"],
            }
            for row in rows
        }

    # ── Logging ───────────────────────────────────────────────────────────────

    def log(self, session_id: str, level: str, message: str):
        self.conn.execute(
            "INSERT INTO processing_logs (session_id, timestamp, level, message) "
            "VALUES (?,?,?,?)",
            (session_id, datetime.now().isoformat(), level, message)
        )
        self.conn.commit()

    def get_logs(self, session_id: str = None, limit: int = 100) -> list:
        if session_id:
            rows = self.conn.execute(
                "SELECT timestamp, level, message FROM processing_logs "
                "WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT timestamp, level, message FROM processing_logs "
                "ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Stats ─────────────────────────────────────────────────────────────────

    def hash_image(self, image_bytes: bytes) -> str:
        return hashlib.md5(image_bytes).hexdigest()[:12]

    def get_stats(self) -> dict:
        total   = self.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        corrx   = self.conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
        avg_row = self.conn.execute("SELECT AVG(confidence) FROM sessions").fetchone()[0]
        return {
            "total_sessions":   total,
            "total_corrections": corrx,
            "avg_confidence":   round(avg_row or 0.0, 2),
        }
