"""Uji chatbot builder: parse FAQ -> widget. Anti-halusinasi = harga di widget
hanya boleh berasal dari tabel FAQ."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.chatbot_agent import build_widget, parse_faq  # noqa: E402

CONTOH = Path(__file__).resolve().parent.parent / "templates" / "faq_contoh_nkhealth.md"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "faq_template.md"


def test_parse_contoh():
    d = parse_faq(CONTOH)
    assert d["nama"] == "NK Health", d["nama"]
    assert d["wa"] == "6287841193393", d["wa"]
    assert len(d["branches"]) == 2, d["branches"]
    assert len(d["layanan"]) == 7, len(d["layanan"])
    assert "Rp400.000" in d["layanan"][0]["harga"]
    assert len(d["faq"]) >= 5
    assert "admin" in d["eskalasi"].lower()
    print("OK parse contoh")


def test_parse_template_kosong_ditolak():
    try:
        parse_faq(TEMPLATE)
    except ValueError as e:
        assert "belum lengkap" in str(e)
        print("OK template kosong ditolak")
        return
    raise AssertionError("template kosong harusnya ditolak")


def test_widget_isi_dari_data():
    d = parse_faq(CONTOH)
    w = build_widget(d)
    assert "Asisten NK Health" in w
    assert "Rp400.000" in w  # harga dari tabel
    assert "wa.me/" in w and "6287841193393" in w
    assert "Kebon Jeruk" in w and "Kelapa Gading" in w
    assert d["eskalasi"] in w  # kalimat eskalasi verbatim
    print("OK widget isi dari data")


def test_widget_tidak_mengarang_harga():
    """Semua 'Rp...' di widget harus berasal dari tabel layanan."""
    d = parse_faq(CONTOH)
    w = build_widget(d)
    allowed = set()
    for l in d["layanan"]:
        allowed.update(re.findall(r"Rp[\d.]+", l["harga"]))
    found = set(re.findall(r"Rp[\d.]+", w))
    invented = found - allowed
    assert not invented, f"harga karangan terdeteksi: {invented}"
    print("OK tidak ada harga karangan")


def test_widget_tidak_mengaku_manusia():
    d = parse_faq(CONTOH)
    w = build_widget(d).lower()
    assert "asisten digital" in w
    assert "saya dokter" not in w and "saya admin" not in w
    print("OK tidak mengaku manusia")


if __name__ == "__main__":
    test_parse_contoh()
    test_parse_template_kosong_ditolak()
    test_widget_isi_dari_data()
    test_widget_tidak_mengarang_harga()
    test_widget_tidak_mengaku_manusia()
    print("\nSEMUA UJI CHATBOT LOLOS")
