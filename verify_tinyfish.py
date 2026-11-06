#!/usr/bin/env python3
"""Verifikasi web beneran 81 prospek scored via Tinyfish Search. READ-ONLY: DB tidak disentuh.
Output: prospect_verify_tinyfish_2026-10-21.json (inkremental, resumable)."""
import json, re, sqlite3, subprocess, sys, time
from pathlib import Path

AGENCY = Path.home() / "workspace/ai-agency"
OUT = Path.home() / "workspace/goals/ai-digital-agency-for-umkm-websites/hidden_files/prospect_verify_tinyfish_2026-10-21.json"
TINYFISH = Path.home() / "workspace/custom-connectors/custom.tinyfish/bin/tinyfish.py"

AGGREGATOR = ("halodoc", "alodokter", "klikdokter", "sehatq", "gooddoctor", "practo",
              "openstreetmap", "google.", "wikipedia", "tripadvisor", "traveloka",
              "tiket.", "grab.", "gojek", "shopee", "tokopedia", "bukalapak", "contact.page")
SOCIAL = ("facebook.com", "instagram.com", "tiktok.com", "youtube.com", "twitter.com", "x.com", "linkedin.com")
WA_RE = re.compile(r"(?:\+62|62|0)8\d{2,4}[\s.\-]?\d{3,4}[\s.\-]?\d{3,5}")
PHONE_CLEAN = re.compile(r"[\s.\-]")

def norm_wa(raw):
    d = PHONE_CLEAN.sub("", raw)
    if d.startswith("0"):
        d = "62" + d[1:]
    if d.startswith("62") and 10 <= len(d) <= 15:
        return "+" + d
    return None

def name_tokens(nama):
    stop = {"klinik", "laboratorium", "upt", "layanan", "kesehatan", "dan", "the", "rs", "rumah", "sakit"}
    return [t for t in re.findall(r"[a-z0-9]+", nama.lower()) if len(t) > 2 and t not in stop]

def search(query):
    for attempt in range(3):
        p = subprocess.run([sys.executable, str(TINYFISH), "search", query],
                           capture_output=True, text=True, timeout=120)
        if p.returncode == 0:
            try:
                return json.loads(p.stdout)
            except json.JSONDecodeError:
                return {"results": [], "error": "json_parse"}
        if "429" in p.stdout + p.stderr:
            time.sleep(65)
            continue
        return {"results": [], "error": (p.stderr or p.stdout)[:200]}
    return {"results": [], "error": "retry_exhausted"}

def results_of(resp):
    if isinstance(resp, list):
        return resp
    for k in ("results", "data", "organic_results"):
        if isinstance(resp.get(k), list):
            return resp[k]
    return []

def verify(biz):
    nama, lokasi = biz["nama"], biz.get("lokasi", "")
    toks = name_tokens(nama)
    resp = search(f"{nama} {lokasi}")
    res = results_of(resp)
    website, socials, wa_found = None, [], set()
    evidence = []
    for r in res:
        url = (r.get("url") or "").lower()
        title = r.get("title") or ""
        snip = r.get("snippet") or ""
        evidence.append({"title": title, "url": r.get("url"), "snippet": snip[:200]})
        for m in WA_RE.findall(title + " " + snip + " " + url):
            w = norm_wa(m)
            if w:
                wa_found.add(w)
        m = re.search(r"wa\.me/(\d+)", url)
        if m:
            w = norm_wa(m.group(1))
            if w:
                wa_found.add(w)
        if any(s in url for s in SOCIAL):
            socials.append(r.get("url"))
            continue
        if any(a in url for a in AGGREGATOR):
            continue
        if website is None and toks:
            hay = url + " " + title.lower()
            if any(t in hay for t in toks):
                website = r.get("url")
    if website:
        verdict = "PUNYA_WEBSITE"
    elif wa_found or socials:
        verdict = "TIDAK_KETEMU_WEB_TAPI_ADA_KONTAK"
    else:
        verdict = "TIDAK_KETEMU_WEB"
    return {"id": biz["id"], "nama": nama, "lokasi": lokasi,
            "db_has_website": biz.get("has_website"), "db_website": biz.get("existing_website_url"),
            "db_wa": biz.get("nomor_wa"), "verdict": verdict, "website_found": website,
            "wa_found": sorted(wa_found), "socials": socials[:3], "evidence_top": evidence[:4],
            "search_error": resp.get("error") if isinstance(resp, dict) else None}

def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 81
    db = sqlite3.connect(f"file:{AGENCY}/storage/agency.db?mode=ro", uri=True)
    leads = {bid: json.loads(d).get("status") for bid, d in db.execute("SELECT business_id, data FROM leads")}
    bizs = [json.loads(d) for _, d in db.execute("SELECT id, data FROM businesses")]
    scored = [b for b in bizs if leads.get(b["id"]) == "scored"]
    done = {}
    if OUT.exists():
        done = {r["id"]: r for r in json.loads(OUT.read_text())}
    todo = [b for b in scored if b["id"] not in done][:limit]
    print(f"total scored={len(scored)} sudah={len(done)} jalan sekarang={len(todo)}", flush=True)
    for i, b in enumerate(todo, 1):
        t0 = time.time()
        try:
            r = verify(b)
        except Exception as e:
            r = {"id": b["id"], "nama": b["nama"], "verdict": "ERROR", "error": str(e)[:200]}
        done[b["id"]] = r
        OUT.write_text(json.dumps(list(done.values()), ensure_ascii=False, indent=1))
        print(f"[{i}/{len(todo)}] {b['nama'][:45]} -> {r['verdict']} web={r.get('website_found')} wa={r.get('wa_found')}", flush=True)
        wait = 13 - (time.time() - t0)
        if wait > 0:
            time.sleep(wait)
    print("SELESAI", flush=True)

if __name__ == "__main__":
    main()
