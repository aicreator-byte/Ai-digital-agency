/**
 * Jembatan WhatsApp (tidak resmi, pakai Baileys) untuk nomor khusus jualan.
 *
 * - Python kirim pesan lewat HTTP lokal: POST /send, POST /send-image
 * - Pesan masuk diteruskan ke Python: POST WA_WEBHOOK_URL {number, text}
 * - Login sekali via QR di terminal, sesi disimpan di folder ./auth
 *
 * Hanya listen di 127.0.0.1 (tidak terbuka ke internet).
 */
const http = require("http");
const fs = require("fs");
const qrcode = require("qrcode-terminal");
const pino = require("pino");
const { HttpsProxyAgent } = require("https-proxy-agent");
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require("@whiskeysockets/baileys");

const PORT = parseInt(process.env.WA_BRIDGE_PORT || "3000", 10);
const WEBHOOK = process.env.WA_WEBHOOK_URL || "http://127.0.0.1:8081/wa/incoming";
const TOKEN = process.env.WA_BRIDGE_TOKEN || "";
const PAIR_NUMBER = (process.env.WA_PAIR_NUMBER || "").replace(/\D/g, "");

let sock = null;
let ready = false;

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState("auth");
  const { version } = await fetchLatestBaileysVersion();
  // sandbox ini wajib lewat egress proxy untuk koneksi luar
  const proxyUrl = process.env.HTTPS_PROXY || process.env.https_proxy || "";
  const agent = proxyUrl ? new HttpsProxyAgent(proxyUrl) : undefined;
  sock = makeWASocket({ version, auth: state, logger: pino({ level: "silent" }), agent });

  sock.ev.on("creds.update", saveCreds);

  // Pairing code (alternatif QR): set WA_PAIR_NUMBER=628xx, kode dicetak + disimpan ke pair_code.txt
  if (PAIR_NUMBER && !state.creds.registered) {
    setTimeout(async () => {
      try {
        const code = await sock.requestPairingCode(PAIR_NUMBER);
        console.log("KODE PAIRING untuk " + PAIR_NUMBER + ": " + code);
        try { fs.writeFileSync(require("path").join(__dirname, "pair_code.txt"), code); } catch (e) {}
      } catch (e) { console.log("Gagal minta kode pairing:", e.message); }
    }, 3000);
  }

  sock.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      console.log("Scan QR ini dengan WhatsApp nomor jualan (Perangkat Tertaut):");
      qrcode.generate(qr, { small: true });
      try { fs.writeFileSync(require("path").join(__dirname, "qr.txt"), qr); } catch (e) {}
    }
    if (connection === "open") {
      ready = true;
      console.log("WhatsApp tersambung.");
    }
    if (connection === "close") {
      ready = false;
      const code = lastDisconnect?.error?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) {
        console.log("Sesi logout. Hapus folder ./auth lalu jalankan ulang untuk scan QR lagi.");
      } else {
        console.log("Koneksi putus, mencoba sambung ulang...");
        setTimeout(start, 3000);
      }
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const m of messages) {
      if (m.key.fromMe || !m.message) continue;
      const jid = m.key.remoteJid || "";
      if (jid.endsWith("@g.us") || jid.includes("broadcast")) continue; // abaikan grup/status
      // WA baru kadang pakai ID @lid; nomor aslinya ada di remoteJidAlt kalau tersedia
      const number = (m.key.remoteJidAlt || jid).split("@")[0];
      const text = m.message.conversation || m.message.extendedTextMessage?.text || "";
      if (!text) continue;
      try {
        await fetch(WEBHOOK, {
          method: "POST",
          headers: { "Content-Type": "application/json", "x-token": TOKEN },
          body: JSON.stringify({ number, text }),
        });
      } catch (e) {
        console.log("Gagal teruskan pesan masuk ke Python:", e.message);
      }
    }
  });
}

function toJid(number) {
  return `${String(number).replace(/\D/g, "")}@s.whatsapp.net`;
}

async function handleSend(body) {
  if (!ready) return [503, { ok: false, error: "WA belum tersambung" }];
  const jid = toJid(body.to);
  const check = await sock.onWhatsApp(jid);
  if (!check || !check[0] || !check[0].exists) {
    return [404, { ok: false, error: "Nomor tidak terdaftar di WhatsApp" }];
  }
  const target = check[0].jid || jid;
  if (body.image_path) {
    await sock.sendMessage(target, {
      image: fs.readFileSync(body.image_path),
      caption: body.caption || "",
    });
  } else {
    await sock.sendMessage(target, { text: body.text || "" });
  }
  return [200, { ok: true }];
}

const server = http.createServer((req, res) => {
  const reply = (code, obj) => {
    res.writeHead(code, { "Content-Type": "application/json" });
    res.end(JSON.stringify(obj));
  };
  if (TOKEN && req.headers["x-token"] !== TOKEN) return reply(401, { ok: false, error: "token salah" });

  if (req.method === "GET" && req.url === "/status") return reply(200, { ready });

  if (req.method === "POST" && req.url === "/presence") {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", async () => {
      try {
        const body = JSON.parse(raw);
        const jid = toJid(body.to);
        await sock.sendPresenceUpdate(body.state || "composing", jid);
        reply(200, { ok: true });
      } catch (e) {
        reply(500, { ok: false, error: e.message });
      }
    });
    return;
  }

  if (req.method === "POST" && (req.url === "/send" || req.url === "/send-image")) {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", async () => {
      try {
        const [code, obj] = await handleSend(JSON.parse(raw));
        reply(code, obj);
      } catch (e) {
        reply(500, { ok: false, error: e.message });
      }
    });
    return;
  }
  reply(404, { ok: false, error: "not found" });
});

server.listen(PORT, "127.0.0.1", () => console.log(`Bridge WA jalan di 127.0.0.1:${PORT}`));
start();
