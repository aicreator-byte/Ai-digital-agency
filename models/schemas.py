"""
Schema data untuk seluruh pipeline AI Digital Agency.
Pakai Pydantic supaya gampang divalidasi & nanti gampang migrasi ke Postgres.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums status
# ---------------------------------------------------------------------------

class LeadStatus(str, Enum):
    NEW = "new"
    SCORED = "scored"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    DEAL = "deal"


class ProjectStatus(str, Enum):
    NEW = "new"
    IN_PRODUCTION = "in_production"
    STAGED = "staged"          # website jadi, screenshot + staging link siap
    REVIEW = "review"          # menunggu approve klien via Telegram
    REVISION = "revision"      # ada feedback, balik ke website_agent
    APPROVED = "approved"
    INVOICED = "invoiced"
    PAID = "paid"
    PUBLISHED = "published"
    STUCK = "stuck"            # revision_count lewat batas, perlu review manual


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return uuid4().hex[:12]


class Business(BaseModel):
    id: str = Field(default_factory=_new_id)
    nama: str
    kategori: str
    lokasi: str
    alamat: str | None = None
    nomor_wa: str | None = None
    google_maps_url: str | None = None
    has_website: bool = False
    existing_website_url: str | None = None
    website_score: int | None = None  # 0-100, None kalau belum dinilai / tidak ada website
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Lead(BaseModel):
    id: str = Field(default_factory=_new_id)
    business_id: str
    score: int  # skor prospek keseluruhan, bukan cuma skor website
    status: LeadStatus = LeadStatus.NEW
    contact_channel: str | None = None  # "whatsapp" / "email"
    last_contacted_at: datetime | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Project(BaseModel):
    id: str = Field(default_factory=_new_id)
    business_id: str
    lead_id: str
    status: ProjectStatus = ProjectStatus.NEW
    brief: dict = Field(default_factory=dict)  # nama usaha, logo, warna, layanan, foto, dst
    staging_url: str | None = None
    screenshot_path: str | None = None
    revision_count: int = 0
    revision_notes: list[str] = Field(default_factory=list)
    max_revisions: int = 5
    cf_pages_project: str | None = None
    live_url: str | None = None       # URL *.pages.dev setelah deploy
    custom_domain: str | None = None  # diisi setelah domain dibeli & di-attach manual
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Invoice(BaseModel):
    id: str = Field(default_factory=_new_id)
    project_id: str
    nominal: int
    jatuh_tempo: datetime
    status: InvoiceStatus = InvoiceStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Message(BaseModel):
    id: str = Field(default_factory=_new_id)
    business_id: str
    isi: str
    agent: str  # agent mana yang kirim/terima pesan ini
    arah: str = "out"  # "out" (agent -> klien) atau "in" (klien -> agent)
    created_at: datetime = Field(default_factory=datetime.utcnow)
