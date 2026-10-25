// أرقام زيارات موقع المهندس لآخر 60 يوماً حسب المنصة (للوحة فقط: محمية بالجلسة مثل /api/gh).
const { createHmac, timingSafeEqual } = require('node:crypto');

const sessionToken = (pw) => createHmac('sha256', pw).update('social-dashboard-session-v1').digest('hex');
const eq = (a, b) => { const x = Buffer.from(String(a)), y = Buffer.from(String(b)); return x.length === y.length && timingSafeEqual(x, y); };
const cookieOf = (req, name) => {
  const m = String(req.headers.cookie || '').split(/;\s*/).find((c) => c.startsWith(name + '='));
  return m ? decodeURIComponent(m.slice(name.length + 1)) : '';
};

module.exports = async (req, res) => {
  res.setHeader('cache-control', 'no-store');
  const pw = process.env.DASHBOARD_PASSWORD || '';
  if (!pw || !eq(cookieOf(req, 'dash_auth'), sessionToken(pw))) return res.status(401).json({ error: 'unauthorized' });
  const url = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) return res.status(200).json({ configured: false, days: [] });

  const days = [];
  for (let i = 0; i < 60; i++) {
    days.push(new Date(Date.now() - i * 864e5).toLocaleDateString('en-CA', { timeZone: 'Asia/Hebron' }));
  }
  const r = await fetch(url + '/pipeline', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
    body: JSON.stringify(days.map((d) => ['HGETALL', 'visits:' + d])),
  });
  if (!r.ok) return res.status(502).json({ configured: true, error: 'تعذّر الاتصال بقاعدة العدّاد' });
  const rows = await r.json();
  const out = days.map((d, i) => {
    const flat = (rows[i] && rows[i].result) || [];
    const counts = {};
    for (let k = 0; k < flat.length; k += 2) counts[flat[k]] = parseInt(flat[k + 1], 10) || 0;
    return { day: d, counts };
  });
  return res.status(200).json({ configured: true, days: out });
};
