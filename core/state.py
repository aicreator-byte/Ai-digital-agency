"""
State yang di-pass antar-node di orchestrator (LangGraph).
Ini bukan pengganti database — ini "working memory" satu run pipeline
untuk satu project, supaya tiap agent tahu context tanpa query ulang terus.
"""

from __future__ import annotations

from typing import TypedDict


class PipelineState(TypedDict, total=False):
    business_id: str
    lead_id: str
    project_id: str
    status: str            # nilai ProjectStatus saat ini
    brief: dict             # data usaha untuk website_agent
    staging_url: str
    screenshot_path: str
    revision_notes: list[str]
    revision_count: int
    max_revisions: int
    error: str | None       # kalau ada agent gagal, catat di sini biar orchestrator bisa handle
    next_action: str | None  # dipakai orchestrator buat routing eksplisit kalau perlu


def initial_state(business_id: str, lead_id: str, project_id: str, brief: dict) -> PipelineState:
    return PipelineState(
        business_id=business_id,
        lead_id=lead_id,
        project_id=project_id,
        status="new",
        brief=brief,
        revision_notes=[],
        revision_count=0,
        max_revisions=5,
        error=None,
        next_action=None,
    )
