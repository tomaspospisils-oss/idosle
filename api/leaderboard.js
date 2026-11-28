// GET /api/leaderboard – top 10 dnešního dne (nejméně spojů nahoře), pozice přihlášeného hráče a optimum.
const L = require("./_lib");
module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  const q = req.query || {}, date = String(q.date || L.pragueDate(0));
  if (![L.pragueDate(0), L.pragueDate(1)].includes(date)) return res.status(400).json({ error: "bad" });
  const sub = L.session(req);
  let pz; try { pz = L.read("puzzles.json"); } catch (e) { return res.status(500).json({ error: "data" }); }
  const p = pz[date]; if (!p) return res.status(404).json({ error: "no-puzzle" });
  const key = "lb:" + date;
  try {
    const [total, flat] = await L.redis([["ZCARD", key], ["ZREVRANGE", key, "0", "9", "WITHSCORES"]]);
    const ids = flat.filter((_, i) => i % 2 === 0), sc = flat.filter((_, i) => i % 2 === 1).map(Number), ns = sc.map(s => 1000 - Math.floor(s / L.SC)), tm = s => { const m = L.SC - 1 - (s % L.SC); return m >= L.MAXMS ? null : m; };
    const names = ids.length ? await L.redis(ids.map(id => ["HGET", "u:" + id, "name"])) : [];
    let me = null;
    if (sub) {
      const [rank, score, nm] = await L.redis([["ZREVRANK", key, sub], ["ZSCORE", key, sub], ["HGET", "u:" + sub, "name"]]);
      if (rank !== null && rank !== undefined) me = { rank: rank + 1, n: 1000 - Math.floor(Number(score) / L.SC), ms: tm(Number(score)), name: nm || "" };
    }
    res.status(200).json({ date, total, top: ids.map((id, i) => ({ name: names[i] || "", n: ns[i], ms: tm(sc[i]), me: id === sub })), me, best: p[2] || 0 });
  } catch (e) { res.status(503).json({ error: "storage" }); }
};