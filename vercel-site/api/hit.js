// عدّاد زيارات موقع المهندس حسب المنصة: يستقبل نبضة واحدة لكل جلسة زائر من الموقع نفسه.
// لا يحفظ أي بيانات شخصية: رقم يزيد في خانة (اليوم، المنصة) فقط.
// التخزين: Upstash Redis المجاني (يربطه صاحب اللوحة من Vercel Marketplace فتُضاف متغيراته تلقائياً).
const SOURCES = new Set(['facebook', 'instagram', 'threads', 'linkedin', 'telegram', 'google', 'other', 'direct']);
const TTL = 60 * 60 * 24 * 400;

const redis = () => {
  const url = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
  return url && token ? { url, token } : null;
};
const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Hebron' });   // YYYY-MM-DD

module.exports = async (req, res) => {
  res.setHeader('access-control-allow-origin', '*');
  res.setHeader('cache-control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(204).end();
  const db = redis();
  const s = String(new URL(req.url, 'http://x').searchParams.get('s') || '').toLowerCase();
  if (!db || !SOURCES.has(s)) return res.status(204).end();
  const key = 'visits:' + today();
  try {
    await fetch(db.url + '/pipeline', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + db.token, 'Content-Type': 'application/json' },
      body: JSON.stringify([['HINCRBY', key, s, 1], ['EXPIRE', key, TTL]]),
    });
  } catch (e) { /* العدّاد لا يعطّل الموقع أبداً */ }
  return res.status(204).end();
};
