"""
Fase 3 (bagian 1): Website Builder — versi multi-halaman berbasis paket.

Paket (config/packages.yaml) menentukan berapa halaman dan block apa saja
yang di-generate — w1 cuma 1 halaman, w2/w3/c1/c2/c3 beberapa halaman
terpisah dengan nav bar (lihat core/packages.py & templates/site/page_template.html).

Alur:
1. Kalau state belum punya project_id, bikin Project baru. paket diambil
   dari brief['paket'] (idealnya diisi marketing_agent waktu klien deal),
   default ke DEFAULT_PACKAGE kalau belum ditentukan. max_revisions Project
   ikut mengikuti spec paket.
2. generate_site_content() -> LLM bikin SEMUA jenis konten sekaligus
   (headline, about, services, faq, gallery caption, blog draft) dalam
   satu panggilan JSON — lebih hemat dibanding panggil LLM per halaman.
   Halaman yang tidak butuh field tertentu (misal w1 tidak butuh
   blog_posts) otomatis diabaikan saat render.
3. render_site() -> loop tiap halaman di package_spec['pages'], render
   cuma block yang relevan ke page_template.html.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config.settings import BASE_DIR, STAGING_DIR
from core.database import get_business, get_lead, get_project, save_project
from core.llm import generate
from core.package_rules import assign_package
from core.packages import DEFAULT_PACKAGE, get_package, nav_items
from agents.chatbot_agent import build_widget_from_faq
from core.state import PipelineState
from models.schemas import Project, ProjectStatus

logger = logging.getLogger("website_agent")

TEMPLATE_DIR = BASE_DIR / "templates" / "site"
_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

_CONTENT_SYSTEM_PROMPT = """\
Kamu menulis copywriting website untuk UMKM/bisnis Indonesia. Jawab HANYA
dengan JSON valid (tanpa markdown code fence, tanpa penjelasan), struktur
persis:
{
  "headline": "...",
  "subheadline": "...",
  "about": "... (2-4 kalimat)",
  "meta_description": "... (maks 155 karakter)",
  "services": [{"name": "...", "desc": "..."}, ...],
  "faq": [{"q": "...", "a": "..."}, ...],
  "blog_posts": [{"title": "...", "excerpt": "..."}, ...],
  "cta_text": "..."
}
Buat 3-5 layanan, 3-4 FAQ, dan 2-3 draft judul+ringkasan artikel blog yang
relevan dengan bisnisnya (blog_posts boleh berupa ide artikel generik untuk
industrinya walau belum ada draft lengkap). Bahasa Indonesia, nada ramah
dan profesional, jangan bombastis/lebay."""


def generate_site_content(brief: dict, revision_notes: list[str] | None = None) -> dict:
    prompt = f"Data bisnis:\n{json.dumps(brief, ensure_ascii=False, indent=2)}\n\n"
    if revision_notes:
        prompt += (
            "Ini REVISI dari draft sebelumnya. Catatan revisi dari klien:\n"
            + "\n".join(f"- {n}" for n in revision_notes)
            + "\n\nSesuaikan konten dengan catatan di atas."
        )
    else:
        prompt += "Buat konten website pertama untuk bisnis ini."

    raw = generate(prompt, system=_CONTENT_SYSTEM_PROMPT, max_tokens=2000)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("LLM tidak balas JSON valid, isi mentah: %s", raw[:300])
        raise


def render_site(project_id: str, brief: dict, content: dict, package_spec: dict) -> Path:
    site_dir = STAGING_DIR / project_id / "site"
    site_dir.mkdir(parents=True, exist_ok=True)

    base_context = {
        "nama_usaha": brief.get("nama", "Usaha Anda"),
        "nomor_wa": (brief.get("nomor_wa") or "").lstrip("0").lstrip("+"),
        "alamat": brief.get("alamat", ""),
        "warna": brief.get("warna", "#2563eb"),
        "photos": brief.get("foto", []),
        **content,
    }

    # Tier C (chatbot: true): injeksi widget chatbot dari FAQ klien.
    # Tanpa faq_path -> widget dilewati, website tetap jadi (tidak error).
    chatbot_widget = ""
    if package_spec.get("chatbot") and brief.get("faq_path"):
        try:
            chatbot_widget = build_widget_from_faq(brief["faq_path"])
        except ValueError as e:
            logger.warning("chatbot dilewati: %s", e)

    template = _env.get_template("page_template.html")
    pages = package_spec["pages"]

    for page in pages:
        block_types = package_spec["blocks"][page]
        blocks = [{"type": t} for t in block_types]
        page_nav = nav_items(package_spec, page)

        context = {
            **base_context,
            "page_title": None if page == "index" else page_nav[pages.index(page)]["label"],
            "blocks": blocks,
            "nav_items": page_nav,
            "chatbot_widget": chatbot_widget,
        }

        html = template.render(**context)
        filename = "index.html" if page == "index" else f"{page}.html"
        (site_dir / filename).write_text(html, encoding="utf-8")

    css_template = _env.get_template("style.css")
    css = css_template.render(warna=base_context["warna"])
    (site_dir / "style.css").write_text(css, encoding="utf-8")

    return site_dir


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(state: PipelineState) -> PipelineState:
    project_id = state.get("project_id")

    if not project_id:
        business = get_business(state["business_id"])
        if business is None:
            state["error"] = "website: business tidak ditemukan"
            return state

        brief = state.get("brief") or {
            "nama": business.nama,
            "alamat": business.alamat,
            "nomor_wa": business.nomor_wa,
        }

        if "paket" not in brief:
            lead = get_lead(state.get("lead_id", "")) if state.get("lead_id") else None
            brief["paket"] = assign_package(business.kategori, lead.score if lead else 0)

        paket_id = brief.get("paket", DEFAULT_PACKAGE)

        try:
            package_spec = get_package(paket_id)
        except ValueError as exc:
            state["error"] = f"website: {exc}"
            return state

        project = Project(
            business_id=business.id,
            lead_id=state.get("lead_id", ""),
            status=ProjectStatus.IN_PRODUCTION,
            brief=brief,
            max_revisions=package_spec["max_revisions"],
        )
        save_project(project)
        state["project_id"] = project.id
        state["brief"] = brief
    else:
        project = get_project(project_id)
        if project is None:
            state["error"] = f"website: project {project_id} tidak ditemukan"
            return state
        try:
            package_spec = get_package(project.brief.get("paket", DEFAULT_PACKAGE))
        except ValueError as exc:
            state["error"] = f"website: {exc}"
            return state

    revision_notes = state.get("revision_notes") or []
    try:
        content = generate_site_content(state["brief"], revision_notes=revision_notes or None)
        render_site(project.id, state["brief"], content, package_spec)
    except Exception as exc:  # noqa: BLE001
        state["error"] = f"website: gagal generate/render - {exc}"
        return state

    project.status = ProjectStatus.IN_PRODUCTION
    save_project(project)

    state["status"] = "in_production"
    return state
