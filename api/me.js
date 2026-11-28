// GET /api/me – kdo jsem (+ Google client ID pro tlačítko); POST /api/me {name} – změna jména ve hře.
const L = require("./_lib");
module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  const clientId = (L.CLIENT() && L.SECRET()) ? L.CLIENT() : null, sub = L.session(req);
  if (req.method === "GET") {
    let user = null;
    if (sub) { try { const [n] = await L.redis([["HGET", "u:" + sub, "name"]]); if (n) user = { name: n }; } catch (e) {} }
    return res.status(200).json({ clientId, user });
  }
  if (req.method !== "POST") return res.status(405).json({ error: "method" });
  if (L.crossSite(req)) return res.status(403).json({ error: "origin" });
  if (!sub) return res.status(401).json({ error: "login" });
  try { res.status(200).json({ user: { name: await L.rename(sub, L.body(req).name) } }); }
  catch (e) { const m = { badname: 400, taken: 409, login: 401 }[e.message]; res.status(m || 503).json({ error: m ? e.message : "storage" }); }
};