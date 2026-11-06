"""
Chatbot builder — fase paket chatbot (B1/B2/B3, C1/C2/C3).

Membangun widget chatbot rule-based dari file FAQ klien
(templates/faq_<klien>.md). Guardrail struktural, bukan janji:
- Harga & jawaban HANYA dari data FAQ (tidak ada LLM bebas).
- Tidak ada di FAQ -> kalimat eskalasi + link WhatsApp admin.
- Harga & booking = alur scripted (cabang -> layanan -> harga -> WA).
- Bot tidak pernah mengaku manusia ("Asisten <nama>").
"""

from __future__ import annotations

import json
import re
from pathlib import Path

STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "untuk", "dengan", "adalah", "ini",
    "itu", "saya", "kamu", "anda", "apa", "bagaimana", "berapa", "kapan",
    "apakah", "bisa", "ada", "tidak", "juga", "atau", "pada", "sebagai",
    "dalam", "oleh", "akan", "sudah", "belum", "jika", "kalau", "agar",
    "supaya", "saja", "nya", "kah", "pun", "tersebut",
}


def _norm_wa(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    return digits


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[a-z]{4,}", text.lower())
    seen = []
    for w in words:
        if w not in STOPWORDS and w not in seen:
            seen.append(w)
    return seen


def _section(text: str, num: str) -> str:
    """Ambil isi section '## <num>.' sampai header '## ' berikutnya."""
    m = re.search(rf"^## {re.escape(num)}\.(.*)(?=^## |\Z)", text,
                  re.M | re.S)
    return m.group(1).strip() if m else ""


def _kv_lines(section: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in section.splitlines():
        m = re.match(r"^\s*-\s*([^:]+):\s*(.*)$", line)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def parse_faq(path: str | Path) -> dict:
    """Parse templates/faq_<klien>.md -> dict terstruktur. ValueError bila tak lengkap."""
    text = Path(path).read_text(encoding="utf-8")
    ident = _section(text, "1")
    kv = _kv_lines(ident)

    # cabang: sub-list di bawah "- Cabang:"
    branches: list[dict[str, str]] = []
    in_cabang = False
    for line in ident.splitlines():
        if re.match(r"^\s*-\s*Cabang\s*:", line):
            in_cabang = True
            continue
        if in_cabang:
            m = re.match(r"^\s+-\s*(.+)$", line)
            if m:
                item = m.group(1).strip()
                name, _, addr = item.partition(":")
                branches.append({"name": name.strip(), "address": addr.strip()})
            elif re.match(r"^\s*-\s*\S", line):
                in_cabang = False

    # tabel layanan
    layanan: list[dict[str, str]] = []
    for line in _section(text, "2").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or re.match(r"^:?-{3,}", cells[0]):
            continue
        if cells[0].lower() == "layanan":
            continue
        layanan.append({
            "nama": cells[0],
            "harga": cells[1],
            "keterangan": cells[2] if len(cells) > 2 else "",
        })

    kebijakan = _kv_lines(_section(text, "3"))

    # FAQ Q/A (A boleh multi-baris)
    faq: list[dict] = []
    cur_q: str | None = None
    cur_a: list[str] = []
    for line in _section(text, "4").splitlines():
        if line.startswith("Q:"):
            if cur_q is not None:
                faq.append({"q": cur_q, "a": " ".join(cur_a).strip(),
                            "kw": _keywords(cur_q)})
            cur_q, cur_a = line[2:].strip(), []
        elif line.startswith("A:") and cur_q is not None:
            cur_a.append(line[2:].strip())
        elif cur_q is not None and line.strip():
            cur_a.append(line.strip())
    if cur_q is not None:
        faq.append({"q": cur_q, "a": " ".join(cur_a).strip(),
                    "kw": _keywords(cur_q)})

    m_esk = re.search(r"Kalimat eskalasi:\s*\"([^\"]+)\"", text)
    eskalasi = m_esk.group(1) if m_esk else ""

    missing = []
    nama = kv.get("Nama bisnis", "")
    wa = _norm_wa(kv.get("Telepon / WhatsApp", ""))
    if not nama:
        missing.append("Nama bisnis")
    if not wa:
        missing.append("Telepon / WhatsApp")
    if not layanan:
        missing.append("tabel Layanan & Harga")
    if not eskalasi:
        missing.append("Kalimat eskalasi")
    if missing:
        raise ValueError(
            "FAQ belum lengkap (" + ", ".join(missing) + ") — "
            "chatbot tidak dibangun sampai file dikonfirmasi."
        )

    return {
        "nama": nama,
        "bidang": kv.get("Bidang usaha", ""),
        "branches": branches,
        "wa": wa,
        "jam": kv.get("Jam operasional", ""),
        "layanan": layanan,
        "kebijakan": kebijakan,
        "faq": faq,
        "eskalasi": eskalasi,
    }


# ---------------------------------------------------------------------------
# Widget generator
# ---------------------------------------------------------------------------

WIDGET_CSS = """
<style>
.cb-btn{position:fixed;right:18px;bottom:18px;z-index:60;width:60px;height:60px;border-radius:50%;
 background:var(--cb,#0e7c6b);color:#fff;display:flex;align-items:center;justify-content:center;
 font-size:1.6rem;cursor:pointer;box-shadow:0 12px 28px rgba(14,124,107,.45);transition:transform .2s;border:0}
.cb-btn:hover{transform:scale(1.08)}
.cb-btn .cb-badge{position:absolute;top:-2px;right:-2px;background:#ff5c38;color:#fff;font-size:.65rem;
 font-weight:800;width:20px;height:20px;border-radius:50%;display:flex;align-items:center;justify-content:center}
.cb-panel{position:fixed;right:18px;bottom:88px;z-index:60;width:min(360px,calc(100vw - 36px));
 max-height:min(520px,calc(100dvh - 120px));background:#fff;border-radius:22px;
 box-shadow:0 24px 60px rgba(8,76,65,.28);display:none;flex-direction:column;overflow:hidden;
 border:1px solid #dde1e8;font-family:system-ui,sans-serif}
.cb-panel.open{display:flex}
.cb-head{background:#0b5f53;color:#fff;padding:14px 16px;display:flex;gap:12px;align-items:center}
.cb-head .cb-ava{width:38px;height:38px;border-radius:50%;background:#fff;display:flex;
 align-items:center;justify-content:center;font-size:1.2rem;flex-shrink:0}
.cb-head b{display:block;font-size:.95rem}
.cb-head span{font-size:.75rem;opacity:.8}
.cb-head .cb-x{margin-left:auto;background:none;border:0;color:#fff;font-size:1.3rem;cursor:pointer;opacity:.8}
.cb-body{padding:14px;overflow-y:auto;display:flex;flex-direction:column;gap:10px;flex:1;min-height:220px;background:#f7faf8}
.cb-msg{max-width:85%;padding:10px 13px;border-radius:16px;font-size:.88rem;line-height:1.55}
.cb-msg.cb-bot{background:#fff;border:1px solid #dde1e8;border-bottom-left-radius:4px;align-self:flex-start;color:#0e1526}
.cb-msg.cb-user{background:var(--cb,#0e7c6b);color:#fff;border-bottom-right-radius:4px;align-self:flex-end}
.cb-chips{display:flex;flex-wrap:wrap;gap:7px}
.cb-chip{background:#fff;border:1.5px solid var(--cb,#0e7c6b);color:#0b5f53;border-radius:999px;
 padding:7px 13px;font-size:.8rem;font-weight:700;cursor:pointer}
.cb-chip:hover{background:var(--cb,#0e7c6b);color:#fff}
.cb-input{display:flex;gap:8px;padding:12px;border-top:1px solid #dde1e8;background:#fff}
.cb-input input{flex:1;border:1.5px solid #dde1e8;border-radius:999px;padding:11px 16px;font-size:.88rem;outline:none}
.cb-input button{background:var(--cb,#0e7c6b);color:#fff;border:0;width:42px;height:42px;border-radius:50%;cursor:pointer;font-size:1.1rem;flex-shrink:0}
</style>
"""

WIDGET_HTML = """
<button class="cb-btn" id="cbBtn" aria-label="Buka chatbot">&#128172;<span class="cb-badge" id="cbBadge">1</span></button>
<div class="cb-panel" id="cbPanel">
  <div class="cb-head">
    <div class="cb-ava">&#129302;</div>
    <div><b>__NAMA__</b><span>Online &middot; balas instan</span></div>
    <button class="cb-x" id="cbX" aria-label="Tutup">&times;</button>
  </div>
  <div class="cb-body" id="cbBody"></div>
  <div class="cb-input">
    <input id="cbInput" placeholder="Ketik pesan..." autocomplete="off">
    <button id="cbSend" aria-label="Kirim">&#10148;</button>
  </div>
</div>
"""

WIDGET_JS = """
<script>
(function(){
const D = __DATA_JSON__;
const body=document.getElementById('cbBody'), panel=document.getElementById('cbPanel'),
      btn=document.getElementById('cbBtn'), badge=document.getElementById('cbBadge'),
      input=document.getElementById('cbInput');
let state={branch:(D.branches.length===1?D.branches[0].name:null),service:null}, opened=false;
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function msg(t,who){const d=document.createElement('div');d.className='cb-msg cb-'+who;d.innerHTML=t;
 body.appendChild(d);body.scrollTop=body.scrollHeight;}
function chips(list){const w=document.createElement('div');w.className='cb-chips';
 list.forEach(function(l){const b=document.createElement('button');b.className='cb-chip';b.textContent=l.label;
  b.onclick=function(){msg(esc(l.label),'user');setTimeout(l.act,250);};w.appendChild(b);});
 body.appendChild(w);body.scrollTop=body.scrollHeight;}
function wa(t){return 'https://wa.me/'+D.wa+'?text='+encodeURIComponent(t);}
function goWa(t){window.open(wa(t),'_blank');}
function priceText(l){
 if(/DITENTUKAN SETELAH PEMERIKSAAN/i.test(l.harga))
  return 'Biayanya ditentukan setelah pemeriksaan'+(l.keterangan?' — '+esc(l.keterangan):'')+'. Tenang, diinformasikan <b>sebelum</b> tindakan dimulai.';
 return 'Harganya <b>'+esc(l.harga)+'</b>'+(l.keterangan?'<br>'+esc(l.keterangan):'')+'.';
}
function askBranch(){
 msg('Silakan pilih cabang <b>'+esc(D.nama)+'</b> yang ingin Anda kunjungi:','bot');
 chips(D.branches.map(function(b){return {label:b.name,act:function(){state.branch=b.name;askService();}};}));
}
function askService(){
 const pre=state.branch?('Cabang <b>'+esc(state.branch)+'</b> — '):'';
 msg(pre+'mau tanya layanan apa, Pak/Bu?','bot');
 const list=D.layanan.map(function(l){return {label:l.nama,act:function(){showService(l);}};});
 list.push({label:'Lihat semua harga',act:showPrices});
 list.push({label:'Chat admin',act:function(){goWa('Halo '+D.nama+', saya mau bertanya.');}});
 chips(list);
}
function showService(l){
 state.service=l.nama;
 msg('<b>'+esc(l.nama)+'</b><br>'+priceText(l),'bot');
 chips([
  {label:'Booking '+l.nama,act:booking},
  {label:'Layanan lain',act:askService},
  {label:'Chat admin',act:function(){goWa('Halo '+D.nama+', saya mau tanya tentang '+l.nama+(state.branch?(' di cabang '+state.branch):'')+'.');}}
 ]);
}
function showPrices(){
 const rows=D.layanan.map(function(l){
  return '&bull; <b>'+esc(l.nama)+' — '+esc(l.harga)+'</b>';}).join('<br>');
 msg('Daftar harga kami:<br>'+rows,'bot');
 chips([{label:'Pilih layanan',act:askService},
        {label:'Chat admin',act:function(){goWa('Halo '+D.nama+', saya mau tanya harga.');}}]);
}
function booking(){
 msg('Siap! Booking <b>'+esc(state.service)+'</b>'+(state.branch?(' di cabang <b>'+esc(state.branch)+'</b>'):'')
  +'. Lanjutkan ke WhatsApp — admin akan konfirmasi jadwalnya.','bot');
 chips([{label:'Lanjut ke WhatsApp',act:function(){
   goWa('Halo '+D.nama+', saya mau booking '+state.service+(state.branch?(' di cabang '+state.branch):'')+'.');}},
  {label:'Mulai dari awal',act:function(){state={branch:(D.branches.length===1?D.branches[0].name:null),service:null};askBranch();}}]);
}
function matchService(s){
 let best=null,bs=0,tie=false;
 D.layanan.forEach(function(l){
  const words=l.nama.toLowerCase().split(/[^a-z]+/).filter(function(w){return w.length>3;});
  let sc=0;words.forEach(function(w){if(s.indexOf(w)>=0)sc++;});
  if(sc>bs){bs=sc;best=l;tie=false;}else if(sc===bs&&sc>0){tie=true;}
 });
 if(bs===0)return null;
 if(tie){ // ambigu — tawarkan pilihan + selalu sediakan jalan ke admin
  msg('Maksudnya layanan yang mana, Pak/Bu?','bot');
  const opts=D.layanan.filter(function(l){
   const words=l.nama.toLowerCase().split(/[^a-z]+/).filter(function(w){return w.length>3;});
   return words.some(function(w){return s.indexOf(w)>=0;});
  }).map(function(l){return {label:l.nama,act:function(){showService(l);}};});
  opts.push({label:'Chat admin',act:function(){goWa('Halo '+D.nama+', saya mau bertanya: '+t);}});
  chips(opts);
  return 'tie';
 }
 return best;
}
function reply(t){
 const s=t.toLowerCase();
 const m=matchService(s);
 if(m==='tie')return;
 if(m){state.service=m.nama;return showService(m);}
 if(/jam|buka|tutup|operasional/.test(s)&&D.jam)
  return msg('Jam operasional kami: <b>'+esc(D.jam)+'</b>.','bot');
 if(/cabang|lokasi|alamat/.test(s))return askBranch();
 if(/harga|biaya|tarif|paket/.test(s))return showPrices();
 if(/booking|daftar|jadwal|janji|reservasi/.test(s))
  return (state.branch||D.branches.length<=1)?askService():askBranch();
 let best=null,bs=0;
 D.faq.forEach(function(f){let sc=0;f.kw.forEach(function(k){if(s.indexOf(k)>=0)sc++;});
  if(sc>bs){bs=sc;best=f;}});
 if(best&&bs>=2)return msg(esc(best.a),'bot');
 msg(esc(D.eskalasi),'bot'); // tidak ada di data -> eskalasi, bukan mengarang
 chips([{label:'Chat admin via WhatsApp',act:function(){goWa('Halo '+D.nama+', saya mau bertanya: '+t);}}]);
}
function send(){
 const v=input.value.trim();if(!v)return;input.value='';msg(esc(v),'user');
 setTimeout(function(){reply(v);},350);
}
document.getElementById('cbSend').onclick=send;
input.onkeydown=function(e){if(e.key==='Enter')send();};
btn.onclick=function(){const open=panel.classList.toggle('open');
 badge.style.display=open?'none':'flex';
 if(open&&!opened){opened=true;
  msg('Halo! Selamat datang di <b>'+esc(D.nama)+'</b> 🙂<br>Saya asisten digital di sini — saya jawab dari info resmi kami.','bot');
  if(D.branches.length>1)askBranch();else askService();
 }};
document.getElementById('cbX').onclick=function(){panel.classList.remove('open');};
})();
</script>
"""


def build_widget(data: dict) -> str:
    """Bangun snippet widget (CSS+HTML+JS) dari data hasil parse_faq()."""
    payload = {
        "nama": data["nama"],
        "wa": data["wa"],
        "jam": data.get("jam", ""),
        "branches": data.get("branches", []),
        "layanan": data.get("layanan", []),
        "faq": data.get("faq", []),
        "eskalasi": data["eskalasi"],
    }
    js = WIDGET_JS.replace("__DATA_JSON__", json.dumps(payload, ensure_ascii=False))
    html = WIDGET_HTML.replace("__NAMA__", "Asisten " + data["nama"])
    return WIDGET_CSS + html + js


def build_widget_from_faq(faq_path: str | Path) -> str:
    return build_widget(parse_faq(faq_path))
