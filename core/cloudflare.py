"""Helper Cloudflare Pages — deploy site statis agensi.

Auth pakai surrogate dari vault (custom.cloudflare), bukan raw token.
Account ID default milik Di; bisa dioverride via env CF_ACCOUNT_ID.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "b4e0a0e8c7d918157959a113dece01a9")
CF_API = "https://api.cloudflare.com/client/v4"
WRANGLER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "node_modules", ".bin", "wrangler")

_CF_SURROGATE = None


def _cf_surrogate() -> str:
    global _CF_SURROGATE
    if _CF_SURROGATE:
        return _CF_SURROGATE
    sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
    from dynamic_credentials import dynamic_credential_entry

    _CF_SURROGATE = str(dynamic_credential_entry("custom.cloudflare")["surrogate"]).strip()
    return _CF_SURROGATE


def cf_api(method: str, path: str, payload: dict | None = None) -> dict:
    """Panggil Cloudflare API, return result (raise kalau gagal)."""
    req = urllib.request.Request(
        f"{CF_API}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_cf_surrogate()}",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if not data.get("success"):
        raise RuntimeError(f"Cloudflare API gagal: {data.get('errors')}")
    return data["result"]


def ensure_pages_project(project_name: str) -> dict:
    """Bikin Pages project kalau belum ada; return info project."""
    try:
        return cf_api("GET", f"/accounts/{CF_ACCOUNT_ID}/pages/projects/{project_name}")
    except Exception:
        pass
    return cf_api(
        "POST",
        f"/accounts/{CF_ACCOUNT_ID}/pages/projects",
        {"name": project_name, "production_branch": "main"},
    )


def deploy_site(site_dir: str, project_name: str) -> str:
    """Deploy folder statis ke Cloudflare Pages via wrangler. Return live URL."""
    ensure_pages_project(project_name)
    env = {
        **os.environ,
        "CLOUDFLARE_API_TOKEN": _cf_surrogate(),
        "CLOUDFLARE_ACCOUNT_ID": CF_ACCOUNT_ID,
    }
    proc = subprocess.run(
        [WRANGLER, "pages", "deploy", site_dir, "--project-name", project_name, "--commit-dirty=true"],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"wrangler deploy gagal: {proc.stderr[-500:]}")
    # wrangler cetak URL di stdout, mis. https://xxx.pages.dev
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("https://") and "pages.dev" in line:
            return line.rstrip("/")
    return f"https://{project_name}.pages.dev"


def attach_custom_domain(project_name: str, domain: str) -> dict:
    """Pasang custom domain ke Pages project. Return instruksi DNS."""
    cf_api(
        "POST",
        f"/accounts/{CF_ACCOUNT_ID}/pages/projects/{project_name}/domains",
        {"name": domain},
    )
    return {
        "domain": domain,
        "dns_instruction": (
            f"Set DNS domain '{domain}' di registrar kamu: "
            f"CNAME '{domain}' -> '{project_name}.pages.dev' "
            "(atau pakai Cloudflare DNS untuk setup otomatis)."
        ),
    }
