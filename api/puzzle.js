// Vercel serverless funkce: vrací JEN dnešní zadání. Datum určuje server (Europe/Prague),
// takže ho nejde ovlivnit nastavením hodin na zařízení. Budoucí zadání ve stránce ani v API nejsou.
const fs = require("fs"), path = require("path");
const EPOCH = Date.UTC(2026, 10, 28);                       // hra č. 1 = 28. 11. 2026 (shodně s šablonou)
module.exports = (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  const date = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Prague" }).format(new Date()); // RRRR-MM-DD
  let all;
  try { all = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", "puzzles.json"), "utf8")); }
  catch (e) { return res.status(500).json({ error: "puzzles-unavailable" }); }
  const p = all[date];
  if (!p) return res.status(404).json({ error: "no-puzzle", date });
  const [y, m, d] = date.split("-").map(Number);
  res.status(200).json({ date, num: Math.round((Date.UTC(y, m - 1, d) - EPOCH) / 864e5) + 1, a: p[0], b: p[1], best: p[2] || 0, now: Date.now() });   // now = čas serveru, podle něj stránka měří čas hry
};