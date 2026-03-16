import aiosqlite
from datetime import datetime, timedelta
from config import DB_PATH, PROJECT_TTL_DAYS


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                is_admin BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                slug TEXT NOT NULL,
                original_name TEXT,
                description TEXT DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                notified BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                UNIQUE(user_id, slug)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS allowed_users (
                telegram_id INTEGER PRIMARY KEY,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migration: add description column to existing databases
        try:
            await db.execute("ALTER TABLE projects ADD COLUMN description TEXT DEFAULT NULL")
        except Exception:
            pass  # Column already exists
        await db.commit()


def _conn():
    return aiosqlite.connect(DB_PATH)


# ── Users ──

async def get_user(telegram_id: int) -> dict | None:
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_by_username(username: str) -> dict | None:
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_user(telegram_id: int, username: str, is_admin: bool = False):
    async with _conn() as db:
        await db.execute(
            "INSERT INTO users (telegram_id, username, is_admin) VALUES (?, ?, ?)",
            (telegram_id, username, is_admin),
        )
        await db.commit()


# ── Allowed Users ──

async def get_all_allowed_users() -> set[int]:
    async with _conn() as db:
        cursor = await db.execute("SELECT telegram_id FROM allowed_users")
        rows = await cursor.fetchall()
        return {row[0] for row in rows}


async def add_allowed_user(telegram_id: int):
    async with _conn() as db:
        await db.execute(
            "INSERT OR IGNORE INTO allowed_users (telegram_id) VALUES (?)",
            (telegram_id,),
        )
        await db.commit()


async def remove_allowed_user(telegram_id: int):
    async with _conn() as db:
        await db.execute(
            "DELETE FROM allowed_users WHERE telegram_id = ?",
            (telegram_id,),
        )
        await db.commit()


# ── Projects ──

async def get_project(user_id: int, slug: str) -> dict | None:
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM projects WHERE user_id = ? AND slug = ?",
            (user_id, slug),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_projects(user_id: int) -> list[dict]:
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_all_projects() -> list[dict]:
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT p.*, u.username
            FROM projects p
            JOIN users u ON p.user_id = u.telegram_id
            ORDER BY p.created_at DESC
        """)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def create_project(user_id: int, slug: str, original_name: str, description: str = None) -> dict:
    expires_at = datetime.utcnow() + timedelta(days=PROJECT_TTL_DAYS)
    async with _conn() as db:
        cursor = await db.execute(
            "INSERT INTO projects (user_id, slug, original_name, description, expires_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, slug, original_name, description, expires_at.isoformat()),
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,))
        row = await cur.fetchone()
        return dict(row)


async def update_project(user_id: int, slug: str, original_name: str, description: str = None) -> dict:
    """Update existing project (overwrite): reset dates."""
    expires_at = datetime.utcnow() + timedelta(days=PROJECT_TTL_DAYS)
    now = datetime.utcnow().isoformat()
    async with _conn() as db:
        await db.execute(
            """UPDATE projects
               SET original_name = ?, description = ?, created_at = ?, expires_at = ?, notified = 0
               WHERE user_id = ? AND slug = ?""",
            (original_name, description, now, expires_at.isoformat(), user_id, slug),
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM projects WHERE user_id = ? AND slug = ?", (user_id, slug)
        )
        row = await cur.fetchone()
        return dict(row)


async def delete_project(user_id: int, slug: str):
    async with _conn() as db:
        await db.execute(
            "DELETE FROM projects WHERE user_id = ? AND slug = ?",
            (user_id, slug),
        )
        await db.commit()


async def extend_project(user_id: int, slug: str):
    """Extend project by PROJECT_TTL_DAYS from now."""
    expires_at = datetime.utcnow() + timedelta(days=PROJECT_TTL_DAYS)
    async with _conn() as db:
        await db.execute(
            "UPDATE projects SET expires_at = ?, notified = 0 WHERE user_id = ? AND slug = ?",
            (expires_at.isoformat(), user_id, slug),
        )
        await db.commit()


async def get_expiring_projects(days_before: int) -> list[dict]:
    """Get projects expiring within `days_before` days that haven't been notified."""
    threshold = (datetime.utcnow() + timedelta(days=days_before)).isoformat()
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT p.*, u.username
               FROM projects p
               JOIN users u ON p.user_id = u.telegram_id
               WHERE p.expires_at <= ? AND p.notified = 0""",
            (threshold,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def mark_notified(project_id: int):
    async with _conn() as db:
        await db.execute(
            "UPDATE projects SET notified = 1 WHERE id = ?", (project_id,)
        )
        await db.commit()


async def get_expired_projects() -> list[dict]:
    """Get projects past their expiry date."""
    now = datetime.utcnow().isoformat()
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT p.*, u.username
               FROM projects p
               JOIN users u ON p.user_id = u.telegram_id
               WHERE p.expires_at <= ?""",
            (now,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
