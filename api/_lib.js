// Sdílené pomůcky pro API (soubory s _ na začátku Vercel nevystavuje jako endpointy).
const fs = require("fs"), path = require("path"), crypto = require("crypto");
const read = n => JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", n), "utf8"));
const fmt = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Prague" });
const pragueDate = (back = 0) => fmt.format(new Date(Date.now() - back * 864e5));   // RRRR-MM-DD podle serveru
const SC = 1e10;   // skóre = (1000 - spojů) * SC + (dřívější čas = víc): méně spojů = vyšší skóre, při shodě vyhrává dřívější
const PREFIX = "idosle:";   // Upstash sdílí i antIDOS: každý klíč IDOSle (účty, jména, žebříčky, rozehrané hry) má tuto předponu

// Upstash Redis přes REST (Vercel Marketplace). Podporuje obě pojmenování proměnných prostředí.
async function redis(cmds) {
  const url = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
  const tok = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !tok) throw new Error("no-redis");
  const r = await fetch(url.replace(/\/$/, "") + "/pipeline", { method: "POST", headers: { Authorization: "Bearer " + tok, "Content-Type": "application/json" }, body: JSON.stringify(cmds.map(c => [c[0], PREFIX + c[1], ...c.slice(2)])) });
  if (!r.ok) throw new Error("redis " + r.status);
  return (await r.json()).map(x => { if (x.error) throw new Error(x.error); return x.result; });
}

// Přehraje trasu podle stejných pravidel jako hra: každá linka max 1×, přestupní zastávka (ani start) se neopakuje,
// cesta končí vystoupením v cíli. g = data/graph.json, a/b = názvy startu a cíle.
function validate(g, a, b, legs, partial) {   // partial = rozehraná hra: smí být prázdná a nemusí končit v cíli
  if (!Array.isArray(legs) || (!legs.length && !partial) || legs.length > g.lines.length) return false;
  const ia = g.stops.indexOf(a), ib = g.stops.indexOf(b);
  if (ia < 0 || ib < 0 || ia === ib) return false;
  let c = ia; const used = new Set(), vis = new Set([ia]);
  for (let i = 0; i < legs.length; i++) {
    const x = legs[i]; if (!Array.isArray(x)) return false;
    const [l, t] = x;
    if (!Number.isInteger(l) || !Number.isInteger(t) || !g.lines[l] || t < 0 || t >= g.stops.length || used.has(l) || vis.has(t) || t === c) return false;
    if (!g.lines[l].d.some(q => { const k = q.indexOf(c); return k >= 0 && q.slice(k + 1).includes(t); })) return false;
    if (t === ib && i < legs.length - 1) return false;
    used.add(l); vis.add(t); c = t;
  }
  return partial ? true : c === ib;
}

// ---------- přihlášení přes Google (ID token) + vlastní relace v HttpOnly cookie ----------
const CLIENT = () => process.env.GOOGLE_CLIENT_ID || null, SECRET = () => process.env.SESSION_SECRET || null;
const b64u = s => Buffer.from(s, "base64url");
let jw = { t: 0, keys: [] };
async function jwks() {
  if (Date.now() - jw.t < 36e5 && jw.keys.length) return jw.keys;
  const r = await fetch(process.env.GOOGLE_JWKS_URL || "https://www.googleapis.com/oauth2/v3/certs");
  if (!r.ok) throw new Error("jwks");
  jw = { t: Date.now(), keys: (await r.json()).keys || [] }; return jw.keys;
}
// Ověří podpis (RS256, klíče Google), vydavatele, příjemce (náš client ID), platnost a ověřený e-mail.
async function verifyGoogle(cred) {
  if (typeof cred !== "string" || cred.length > 4096) throw new Error("bad");
  const parts = cred.split("."); if (parts.length !== 3) throw new Error("bad");
  const [h, p, s] = parts, head = JSON.parse(b64u(h)), pay = JSON.parse(b64u(p));
  if (head.alg !== "RS256") throw new Error("alg");
  let jwk = (await jwks()).find(k => k.kid === head.kid);
  if (!jwk) { jw.t = 0; jwk = (await jwks()).find(k => k.kid === head.kid); }     // rotace klíčů
  if (!jwk) throw new Error("kid");
  if (!crypto.verify("RSA-SHA256", Buffer.from(h + "." + p), crypto.createPublicKey({ key: jwk, format: "jwk" }), b64u(s))) throw new Error("sig");
  const ev = pay.email_verified === true || pay.email_verified === "true";
  if (!["accounts.google.com", "https://accounts.google.com"].includes(pay.iss) || !CLIENT() || pay.aud !== CLIENT() || !(pay.exp > Date.now() / 1000) || !pay.sub || !pay.email || !ev) throw new Error("claims");
  return { sub: String(pay.sub), email: String(pay.email).toLowerCase() };
}
const sign = v => crypto.createHmac("sha256", SECRET()).update(v).digest("base64url");
const COOKIE = "idosle_session", MAXAGE = 30 * 86400;
function makeCookie(sub) {
  const v = Buffer.from(JSON.stringify({ s: sub, e: Math.floor(Date.now() / 1000) + MAXAGE })).toString("base64url");
  return `${COOKIE}=${v}.${sign(v)}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=${MAXAGE}`;
}
const clearCookie = `${COOKIE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0`;
function session(req) {                                                              // -> sub přihlášeného, nebo null
  const m = new RegExp("(?:^|;\\s*)" + COOKIE + "=([^;]+)").exec((req.headers && req.headers.cookie) || "");
  if (!m || !SECRET()) return null;
  const [v, sg] = m[1].split("."); if (!v || !sg) return null;
  const ex = sign(v); if (sg.length !== ex.length || !crypto.timingSafeEqual(Buffer.from(sg), Buffer.from(ex))) return null;
  try { const o = JSON.parse(b64u(v)); return o.e > Date.now() / 1000 ? String(o.s) : null; } catch (e) { return null; }
}
const crossSite = req => ((req.headers && req.headers["sec-fetch-site"]) || "") === "cross-site";
const body = req => { let b = req.body; if (typeof b === "string") { try { b = JSON.parse(b); } catch (e) { b = null; } } return b && typeof b === "object" ? b : {}; };

// ---------- uživatelská jména hry (nezávislá na účtu Google, unikátní) ----------
const NAME_RE = /^[\p{L}\p{N}][\p{L}\p{N} ._-]{1,18}[\p{L}\p{N}]$/u;
const normName = s => s.normalize("NFKC").toLowerCase();
const checkName = s => { s = String(s || "").normalize("NFKC").replace(/\s+/g, " ").trim(); return NAME_RE.test(s) && !/^anonym/i.test(s) ? s : null; };
async function ensureUser(sub, email) {                                              // první přihlášení vytvoří účet s náhodným jménem
  const [name] = await redis([["HGET", "u:" + sub, "name"]]); if (name) return name;
  for (let i = 0; i < 8; i++) {
    const nm = "Hráč-" + String(1000 + crypto.randomInt(9000));
    const [ok] = await redis([["SET", "un:" + normName(nm), sub, "NX"]]);
    if (ok) { await redis([["HSET", "u:" + sub, "email", email, "name", nm, "created", new Date().toISOString()]]); return nm; }
  }
  throw new Error("name");
}
const MAP_MODES = ["line", "none", "last"];
async function getUser(sub) {                                                        // {name, mapMode|null} nebo null
  const [r] = await redis([["HMGET", "u:" + sub, "name", "mapmode"]]);
  return r && r[0] ? { name: r[0], mapMode: MAP_MODES.includes(r[1]) ? r[1] : null } : null;
}
async function rename(sub, raw) {                                                    // vrací nové jméno, nebo vyhodí "badname"/"taken"
  const nm = checkName(raw); if (!nm) throw new Error("badname");
  const [old] = await redis([["HGET", "u:" + sub, "name"]]); if (old === null || old === undefined) throw new Error("login");
  const nn = normName(nm), on = normName(old);
  if (nn !== on) {
    const [ok] = await redis([["SET", "un:" + nn, sub, "NX"]]); if (!ok) throw new Error("taken");
    await redis([["DEL", "un:" + on]]);
  }
  await redis([["HSET", "u:" + sub, "name", nm]]); return nm;
}
module.exports = { read, pragueDate, SC, redis, validate, CLIENT, SECRET, verifyGoogle, makeCookie, clearCookie, session, crossSite, body, ensureUser, rename, getUser, MAP_MODES };