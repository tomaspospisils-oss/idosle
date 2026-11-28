// POST /api/score – přihlášený hráč nahraje dohranou trasu; server ji ověří proti pravidlům a uloží do žebříčku dne.
const L = require("./_lib");
module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return res.status(405).json({ error: "method" });
  if (L.crossSite(req)) return res.status(403).json({ error: "origin" });
  const sub = L.session(req); if (!sub) return res.status(401).json({ error: "login" });   // bez přihlášení nejde nahrát
  const b = L.body(req), date = String(b.date || "");
  if (![L.pragueDate(0), L.pragueDate(1)].includes(date)) return res.status(400).json({ error: "bad" });
  let g, pz; try { g = L.read("graph.json"); pz = L.read("puzzles.json"); } catch (e) { return res.status(500).json({ error: "data" }); }
  if (b.ver !== g.ver) return res.status(409).json({ error: "stale" });          // stránka v prohlížeči je z jiné verze dat
  const p = pz[date]; if (!p) return res.status(404).json({ error: "no-puzzle" });
  if (!L.validate(g, p[0], p[1], b.legs)) return res.status(400).json({ error: "invalid" });
  const n = b.legs.length, key = "lb:" + date;
  if (n > 999) return res.status(400).json({ error: "invalid" });
  try {
    const [nm] = await L.redis([["HGET", "u:" + sub, "name"]]); if (!nm) return res.status(401).json({ error: "login" });
    const [added] = await L.redis([["ZADD", key, "NX", String((1000 - n) * L.SC + (L.SC - 1 - Math.floor(Date.now() / 1000))), sub]]);
    if (!added) return res.status(409).json({ error: "already" });
    await L.redis([["EXPIRE", key, 7776000]]);
    const [rank, total] = await L.redis([["ZREVRANK", key, sub], ["ZCARD", key]]);
    res.status(200).json({ ok: true, n, rank: rank + 1, total });
  } catch (e) { res.status(503).json({ error: "storage" }); }
};