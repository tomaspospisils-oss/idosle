// GET /api/game?date=… – rozehraná hra přihlášeného hráče; POST /api/game {date, base, legs} – uloží ji.
// legs jsou páry [„linka|typ“, „zastávka“] podle názvů (přežije nový build dat). Optimistický zámek: pokud se stav
// na serveru mezitím změnil z jiného zařízení (base != t), server vrátí 409 s novějším stavem a nic nepřepíše.
const L = require("./_lib");
const TTL = 3 * 86400;
module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  const sub = L.session(req); if (!sub) return res.status(401).json({ error: "login" });
  const days = [L.pragueDate(0), L.pragueDate(1)];
  try {
    if (req.method === "GET") {
      const date = String((req.query || {}).date || days[0]); if (!days.includes(date)) return res.status(400).json({ error: "bad" });
      const [v] = await L.redis([["GET", `game:${sub}:${date}`]]);
      return res.status(200).json(v ? JSON.parse(v) : { legs: null, t: 0 });
    }
    if (req.method !== "POST") return res.status(405).json({ error: "method" });
    if (L.crossSite(req)) return res.status(403).json({ error: "origin" });
    const b = L.body(req), date = String(b.date || ""); if (!days.includes(date)) return res.status(400).json({ error: "bad" });
    let g, pz; try { g = L.read("graph.json"); pz = L.read("puzzles.json"); } catch (e) { return res.status(500).json({ error: "data" }); }
    const p = pz[date]; if (!p) return res.status(404).json({ error: "no-puzzle" });
    // názvy -> indexy v grafu serveru a kontrola, že jde o platnou (nedokončenou nebo dokončenou) trasu podle pravidel
    const li = new Map(g.lines.map((l, i) => [l.n + "|" + l.t, i])), si = new Map(g.stops.map((n, i) => [n, i]));
    if (!Array.isArray(b.legs) || b.legs.length > g.lines.length) return res.status(400).json({ error: "invalid" });
    const idx = b.legs.map(x => Array.isArray(x) ? [li.get(x[0]), si.get(x[1])] : [undefined, undefined]);
    if (!L.validate(g, p[0], p[1], idx, true)) return res.status(400).json({ error: "invalid" });
    const num = v => { v = Number(v); return Number.isFinite(v) && v > 0 && v <= Date.now() + 60000 ? Math.round(v) : null; };   // začátek / konec měření času
    const key = `game:${sub}:${date}`, [cur] = await L.redis([["GET", key]]), c = cur ? JSON.parse(cur) : null;
    if (c && c.t !== Number(b.base || 0)) return res.status(409).json({ error: "conflict", legs: c.legs, t: c.t, st: c.st || null, te: c.te || null });
    const t = Math.max(Date.now(), (c ? c.t : 0) + 1);
    await L.redis([["SET", key, JSON.stringify({ legs: b.legs, t, st: num(b.st), te: num(b.te) }), "EX", String(TTL)]]);
    res.status(200).json({ ok: true, t });
  } catch (e) { res.status(503).json({ error: "storage" }); }
};