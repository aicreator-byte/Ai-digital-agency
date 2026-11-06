"""
Wrapper LLM tipis — dipakai agent mana pun yang butuh generate/klasifikasi teks.
Provider: anthropic (default), nvidia (NIM, OpenAI-compatible).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

from config.settings import ANTHROPIC_API_KEY, LLM_PROVIDER

NIM_HOST = "integrate.api.nvidia.com"
NIM_MODEL = os.getenv("NIM_MODEL", "meta/llama-3.2-90b-vision-instruct")

_NIM_SURROGATE = None


def _nim_surrogate() -> str:
    """Ambil surrogate credential NVIDIA dari vault (bukan raw key)."""
    global _NIM_SURROGATE
    if _NIM_SURROGATE:
        return _NIM_SURROGATE
    sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
    from dynamic_credentials import dynamic_credential_entry

    _NIM_SURROGATE = str(
        dynamic_credential_entry("custom.nvidia-nim")["surrogate"]
    ).strip()
    return _NIM_SURROGATE


def generate(prompt: str, system: str = "", max_tokens: int = 500) -> str:
    if LLM_PROVIDER == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system or None,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    if LLM_PROVIDER == "nvidia":
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        req = urllib.request.Request(
            f"https://{NIM_HOST}/v1/chat/completions",
            data=json.dumps(
                {
                    "model": NIM_MODEL,
                    "messages": msgs,
                    "temperature": 0.7,
                    "max_tokens": max_tokens,
                }
            ).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_nim_surrogate()}",
            },
        )
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.load(r)
        return data["choices"][0]["message"]["content"]

    raise NotImplementedError(
        f"LLM_PROVIDER='{LLM_PROVIDER}' belum diimplementasi. Pilihan: anthropic, nvidia."
    )
