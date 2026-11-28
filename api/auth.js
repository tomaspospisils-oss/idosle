// POST /api/auth {credential} – přihlášení (ověří Google ID token a nastaví relační cookie); {logout:true} – odhlášení.
const L = require("./_lib");
module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return res.status(405).json({ error: "method" });
  if (L.crossSite(req)) return res.status(403).json({ error: "origin" });
  const b = L.body(req);
  if (b.logout) { res.setHeader("Set-Cookie", L.clearCookie); return res.status(200).json({ ok: true }); }
  if (!L.CLIENT() || !L.SECRET()) return res.status(503).json({ error: "config" });
  let g; try { g = await L.verifyGoogle(b.credential); } catch (e) { return res.status(401).json({ error: "token" }); }
  try {
    const name = await L.ensureUser(g.sub, g.email);
    res.setHeader("Set-Cookie", L.makeCookie(g.sub));
    res.status(200).json({ user: { name } });
  } catch (e) { res.status(503).json({ error: "storage" }); }
};