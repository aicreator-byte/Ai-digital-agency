"""
Database layer pakai SQLite — ringan, jalan tanpa server terpisah,
cocok untuk VPS kecil maupun Termux. Migrasi ke Postgres nanti tinggal
ganti connection string karena semua akses lewat fungsi-fungsi di sini.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from config.settings import DB_PATH
from models.schemas import Business, Invoice, Lead, Message, Project

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    status TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    data TEXT NOT NULL
);
"""


def _default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Tipe tidak bisa di-serialize: {type(obj)}")


@contextmanager
def get_conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# ---------------------------------------------------------------------------
# Generic helpers: simpan/ambil model Pydantic sebagai JSON blob + kolom index
# ---------------------------------------------------------------------------

def save_business(b: Business) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO businesses (id, data) VALUES (?, ?)",
            (b.id, b.model_dump_json()),
        )


def get_business(business_id: str) -> Business | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT data FROM businesses WHERE id = ?", (business_id,)
        ).fetchone()
    return Business.model_validate_json(row["data"]) if row else None


def save_lead(lead: Lead) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO leads (id, business_id, data) VALUES (?, ?, ?)",
            (lead.id, lead.business_id, lead.model_dump_json()),
        )


def get_leads_by_status(status: str) -> list[Lead]:
    with get_conn() as conn:
        rows = conn.execute("SELECT data FROM leads").fetchall()
    leads = [Lead.model_validate_json(r["data"]) for r in rows]
    return [l for l in leads if l.status == status]


def get_lead(lead_id: str) -> Lead | None:
    with get_conn() as conn:
        row = conn.execute("SELECT data FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return Lead.model_validate_json(row["data"]) if row else None


def save_project(p: Project) -> None:
    p.updated_at = datetime.utcnow()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO projects (id, business_id, status, data) VALUES (?, ?, ?, ?)",
            (p.id, p.business_id, p.status, p.model_dump_json()),
        )


def get_project(project_id: str) -> Project | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT data FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    return Project.model_validate_json(row["data"]) if row else None


def get_projects_by_status(status: str) -> list[Project]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT data FROM projects WHERE status = ?", (status,)
        ).fetchall()
    return [Project.model_validate_json(r["data"]) for r in rows]


def save_invoice(inv: Invoice) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO invoices (id, project_id, data) VALUES (?, ?, ?)",
            (inv.id, inv.project_id, inv.model_dump_json()),
        )


def save_message(msg: Message) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO messages (id, business_id, data) VALUES (?, ?, ?)",
            (msg.id, msg.business_id, msg.model_dump_json()),
        )
