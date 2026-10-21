"""
Fase 1: Lead Generation.

PENTING soal arsitektur: scraping/lead-gen ini sifatnya BATCH job
(satu kali jalan bisa hasilkan puluhan-ratusan lead sekaligus), beda
dengan node lain di orchestrator (marketing, website, dst) yang jalan
PER PROJECT satu-satu. Jadi ada 2 entry point di file ini:

1. `find_leads()`  -> dipanggil manual / via command terpisah (nanti bisa
   dari bot Telegram, misal /riset laundry "Bandung Timur"). Ini yang
   benar-benar dipakai untuk Fase 1 sehari-hari.

2. `run(state)`     -> wrapper supaya tetap kompatibel sebagai node
   pertama di LangGraph (core/orchestrator.py). Dipakai kalau kamu mau
   proses satu kategori+lokasi lalu langsung lanjut ke satu lead
   terbaik dalam satu graph run (misal untuk testing/demo end-to-end).

Pakai Google Places API (New) resmi (Text Search + Place Details), BUKAN
scraping HTML Google Maps langsung — sesuai catatan sebelumnya soal
risiko ToS. Butuh GOOGLE_MAPS_API_KEY di .env dengan "Places API (New)"
diaktifkan di Google Cloud Console.
"""

from __future__ import annotations

import logging
import os
import time

import requests
from bs4 import BeautifulSoup

from config.settings import GOOGLE_MAPS_API_KEY, SCRAPER_BACKEND
from core.database import save_business, save_lead
from core.state import PipelineState
from models.schemas import Business, Lead, LeadStatus

logger = logging.getLogger("scraper_agent")

# ---------------------------------------------------------------------------
# Google Places API (New)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Google Places API (New)
# ---------------------------------------------------------------------------

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

REQUEST_TIMEOUT = 10  # detik, buat panggil Places API maupun cek website target

SEARCH_FIELDMASK = "places.id,places.displayName,places.formattedAddress"
DETAILS_FIELDMASK = (
    "id,displayName,formattedAddress,nationalPhoneNumber,"
    "websiteUri,rating,userRatingCount,googleMapsUri"
)


def _places_headers(field_mask: str) -> dict:
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": field_mask,
    }


def _require_key():
    if not GOOGLE_MAPS_API_KEY:
        raise RuntimeError("GOOGLE_MAPS_API_KEY belum diisi di .env")


def search_places_google(kategori: str, lokasi: str) -> list[dict]:
    """Text Search (Google): 'kategori di lokasi', return daftar place dasar."""
    _require_key()
    resp = requests.post(
        PLACES_SEARCH_URL,
        headers=_places_headers(SEARCH_FIELDMASK),
        json={"textQuery": f"{kategori} di {lokasi}", "languageCode": "id", "maxResultCount": 20},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    places = []
    for p in data.get("places", []):
        # id datang sebagai resource name "places/XXX" -> ambil XXX
        raw_id = p.get("id", "")
        place_id = raw_id.split("/", 1)[-1] if "/" in raw_id else raw_id
        places.append(
            {
                "place_id": place_id,
                "name": (p.get("displayName") or {}).get("text", ""),
                "formatted_address": p.get("formattedAddress", ""),
            }
        )
    return places


def get_place_details_google(place_id: str) -> dict:
    """Return dict: name, formatted_address, formatted_phone_number,
    website, rating, user_ratings_total, url."""
    _require_key()
    resp = requests.get(
        PLACES_DETAILS_URL.format(place_id=place_id),
        headers=_places_headers(DETAILS_FIELDMASK),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    d = resp.json()
    return {
        "name": (d.get("displayName") or {}).get("text", ""),
        "formatted_address": d.get("formattedAddress", ""),
        "formatted_phone_number": d.get("nationalPhoneNumber", ""),
        "website": d.get("websiteUri", ""),
        "rating": d.get("rating"),
        "user_ratings_total": d.get("userRatingCount"),
        "url": d.get("googleMapsUri", ""),
    }


def get_place_details(place_id: str) -> dict:
    """Dispatcher: pilih backend Google atau OSM."""
    if SCRAPER_BACKEND == "osm":
        return get_place_details_osm(place_id)
    return get_place_details_google(place_id)


def search_places(kategori: str, lokasi: str) -> list[dict]:
    """Dispatcher: pilih backend Google atau OSM."""
    if SCRAPER_BACKEND == "osm":
        return search_places_osm(kategori, lokasi)
    return search_places_google(kategori, lokasi)


# ---------------------------------------------------------------------------
# OpenStreetMap (Overpass API) — gratis, tanpa key, tanpa kartu kredit
# ---------------------------------------------------------------------------

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = [
    os.getenv("OVERPASS_URL", ""),
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]
OVERPASS_URLS = [u for u in OVERPASS_URLS if u]
_OSM_UA = {"User-Agent": "ai-agency/1.0 (lead scraper)"}

# kategori (id) -> daftar (tag_key, tag_value) OSM
_OSM_TAGS = {
    "klinik": [("amenity", "clinic"), ("amenity", "doctors")],
    "dokter": [("amenity", "doctors")],
    "apotek": [("amenity", "pharmacy")],
    "laundry": [("shop", "laundry")],
    "resto": [("amenity", "restaurant")],
    "restoran": [("amenity", "restaurant")],
    "kafe": [("amenity", "cafe")],
    "cafe": [("amenity", "cafe")],
    "salon": [("shop", "hairdresser"), ("shop", "beauty")],
    "bengkel": [("shop", "car_repair")],
    "hotel": [("tourism", "hotel")],
    "spa": [("shop", "massage")],
    "gym": [("leisure", "fitness_centre")],
    "toko": [("shop", "convenience"), ("shop", "supermarket")],
}

_OSM_CACHE: dict[str, dict] = {}


def _geocode(lokasi: str) -> tuple[float, float]:
    resp = requests.get(
        NOMINATIM_URL,
        params={"q": lokasi, "format": "json", "limit": 1},
        headers=_OSM_UA,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise RuntimeError(f"OSM: lokasi '{lokasi}' tidak ketemu")
    return float(data[0]["lat"]), float(data[0]["lon"])


def _overpass(query: str) -> list[dict]:
    last_err = None
    for url in OVERPASS_URLS:
        try:
            resp = requests.post(
                url, data={"data": query}, headers=_OSM_UA, timeout=60
            )
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except requests.RequestException as e:
            logger.warning("Overpass %s gagal: %s", url, str(e)[:80])
            last_err = e
    raise RuntimeError(f"Semua server Overpass gagal: {last_err}")


def _osm_address(tags: dict) -> str:
    parts = [
        tags.get("addr:street"),
        tags.get("addr:housenumber"),
        tags.get("addr:suburb") or tags.get("addr:village"),
        tags.get("addr:city"),
    ]
    return ", ".join(p for p in parts if p)


def _osm_to_detail(el: dict) -> dict:
    tags = el.get("tags", {})
    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")
    return {
        "name": tags.get("name", "Tanpa nama"),
        "formatted_address": _osm_address(tags),
        "formatted_phone_number": tags.get("phone") or tags.get("contact:phone", ""),
        "website": tags.get("website") or tags.get("contact:website", ""),
        "rating": None,
        "user_ratings_total": None,
        "url": f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
        "_lat": lat,
        "_lon": lon,
    }


def search_places_osm(kategori: str, lokasi: str) -> list[dict]:
    """Cari bisnis via Overpass. Return [{place_id, name}] seperti Google."""
    kat = kategori.strip().lower()
    tag_pairs = _OSM_TAGS.get(kat, [("amenity", kat), ("shop", kat)])
    lat, lon = _geocode(lokasi)
    radius = 8000

    clauses = "".join(
        f'node["{k}"="{v}"](around:{radius},{lat},{lon});'
        f'way["{k}"="{v}"](around:{radius},{lat},{lon});'
        for k, v in tag_pairs
    )
    elements = _overpass(f"[out:json][timeout:40];({clauses});out center tags;")

    places = []
    for el in elements:
        tags = el.get("tags", {})
        if not tags.get("name"):
            continue
        pid = f"{el.get('type')}/{el.get('id')}"
        _OSM_CACHE[pid] = _osm_to_detail(el)
        places.append({"place_id": pid, "name": tags["name"]})
    return places


def get_place_details_osm(place_id: str) -> dict:
    """Return dict kompatibel Google (name, formatted_address, ...)."""
    if place_id in _OSM_CACHE:
        return _OSM_CACHE[place_id]
    typ, _, oid = place_id.partition("/")
    elements = _overpass(f"[out:json][timeout:25];{typ}({oid});out tags;")
    if not elements:
        raise RuntimeError(f"OSM: {place_id} tidak ketemu")
    return _osm_to_detail(elements[0])


# ---------------------------------------------------------------------------
# Penilaian kualitas website
# ---------------------------------------------------------------------------

def score_website(url: str) -> int:
    """
    Skor kasar 0-100 berdasarkan sinyal dasar: HTTPS, mobile-friendly,
    kecepatan respons, SEO dasar, ada WhatsApp, ada Analytics, ada CTA.
    Ini heuristik ringan (bukan Lighthouse beneran) supaya cepat & tanpa
    dependency berat — cukup untuk nyortir prospek, bukan audit teknis.
    """
    score = 0
    try:
        start = time.monotonic()
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        elapsed = time.monotonic() - start
    except requests.RequestException:
        return 0  # website mati/tidak bisa diakses = skor terendah

    if url.startswith("https://"):
        score += 15
    if elapsed < 2.0:
        score += 15

    soup = BeautifulSoup(resp.text, "html.parser")

    if soup.find("meta", attrs={"name": "viewport"}):
        score += 20
    if soup.title and soup.title.text.strip():
        score += 10
    if soup.find("meta", attrs={"name": "description"}):
        score += 10

    page_text = resp.text.lower()
    if "wa.me/" in page_text or "api.whatsapp.com" in page_text:
        score += 10
    if "gtag(" in page_text or "google-analytics.com" in page_text or "googletagmanager.com" in page_text:
        score += 10
    if any(cta in page_text for cta in ("hubungi kami", "pesan sekarang", "order sekarang", "beli sekarang")):
        score += 10

    return min(score, 100)


def compute_lead_score(has_website: bool, website_score: int | None, rating: float | None) -> int:
    """Skor prospek keseluruhan — makin tinggi makin layak diprioritaskan outreach."""
    if not has_website:
        base = 90
    else:
        base = max(0, 100 - (website_score or 0))

    if rating and rating >= 4.0:
        base = min(100, base + 10)

    return base


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def find_leads(kategori: str, lokasi: str, min_score: int = 0) -> list[Lead]:
    """Batch job Fase 1: cari bisnis, nilai, simpan Business+Lead ke DB."""
    places = search_places(kategori, lokasi)
    leads: list[Lead] = []

    for place in places:
        try:
            details = get_place_details(place["place_id"])
        except RuntimeError:
            logger.warning("Gagal ambil detail untuk %s, skip.", place.get("name"))
            continue

        website = details.get("website")
        has_website = bool(website)
        website_score = score_website(website) if has_website else None

        business = Business(
            nama=details.get("name", place.get("name", "Tanpa nama")),
            kategori=kategori,
            lokasi=lokasi,
            alamat=details.get("formatted_address"),
            nomor_wa=details.get("formatted_phone_number"),
            google_maps_url=details.get("url"),
            has_website=has_website,
            existing_website_url=website,
            website_score=website_score,
        )
        save_business(business)

        score = compute_lead_score(has_website, website_score, details.get("rating"))
        if score < min_score:
            continue

        lead = Lead(business_id=business.id, score=score, status=LeadStatus.SCORED)
        save_lead(lead)
        leads.append(lead)

    leads.sort(key=lambda l: l.score, reverse=True)
    return leads


def run(state: PipelineState) -> PipelineState:
    """Node wrapper untuk orchestrator LangGraph — proses 1 kategori+lokasi,
    ambil lead skor tertinggi, lanjutkan pipeline dengan lead itu."""
    kategori = state.get("kategori")
    lokasi = state.get("lokasi")
    if not kategori or not lokasi:
        state["error"] = "scrape: 'kategori' dan 'lokasi' wajib ada di state"
        return state

    leads = find_leads(kategori, lokasi)
    if not leads:
        state["error"] = f"scrape: tidak ada lead ditemukan untuk '{kategori}' di '{lokasi}'"
        return state

    top_lead = leads[0]
    state["business_id"] = top_lead.business_id
    state["lead_id"] = top_lead.id
    state["status"] = "scored"
    return state
