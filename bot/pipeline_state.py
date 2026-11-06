"""
Logic transisi status project yang dipicu oleh tombol inline Telegram
(Approve / Revisi / Reject). Dipisah dari telegram_bot.py supaya gampang
dites tanpa perlu jalanin bot beneran.
"""

from __future__ import annotations

from core.database import get_project, save_project
from core.orchestrator import resume_after_revision, run_payment
from core.state import PipelineState
from models.schemas import Project, ProjectStatus


def _project_to_state(p: Project) -> PipelineState:
    return PipelineState(
        business_id=p.business_id,
        project_id=p.id,
        status=p.status,
        brief=p.brief,
        staging_url=p.staging_url or "",
        screenshot_path=p.screenshot_path or "",
        revision_notes=list(p.revision_notes),
        revision_count=p.revision_count,
        max_revisions=p.max_revisions,
        error=None,
        next_action=None,
    )


def _state_to_project(state: PipelineState, p: Project) -> Project:
    p.status = ProjectStatus(state.get("status", p.status))
    p.staging_url = state.get("staging_url") or p.staging_url
    p.screenshot_path = state.get("screenshot_path") or p.screenshot_path
    p.revision_notes = state.get("revision_notes", p.revision_notes)
    p.revision_count = state.get("revision_count", p.revision_count)
    return p


def handle_approve(project_id: str) -> Project:
    p = get_project(project_id)
    if p is None:
        raise ValueError(f"Project {project_id} tidak ditemukan")

    p.status = ProjectStatus.APPROVED
    state = run_payment(_project_to_state(p))
    p = _state_to_project(state, p)
    save_project(p)
    return p


def handle_revision(project_id: str, catatan: str) -> Project:
    p = get_project(project_id)
    if p is None:
        raise ValueError(f"Project {project_id} tidak ditemukan")

    p.revision_count += 1
    p.revision_notes.append(catatan)

    if p.revision_count > p.max_revisions:
        p.status = ProjectStatus.STUCK
        save_project(p)
        return p

    p.status = ProjectStatus.REVISION
    save_project(p)

    state = resume_after_revision(_project_to_state(p))
    p = _state_to_project(state, p)
    save_project(p)
    return p


def handle_reject(project_id: str) -> Project:
    p = get_project(project_id)
    if p is None:
        raise ValueError(f"Project {project_id} tidak ditemukan")
    p.status = ProjectStatus.STUCK  # perlu keputusan manual, bukan auto-drop
    save_project(p)
    return p
