// وسيط GitHub للوحة: يحمل المفتاح على الخادم (GITHUB_PAT)، فلا يُلصق في أي متصفح.
// الدخول محمي مرتين: middleware.js يمنع غير المسجَّلين، وهنا نتحقق من الكوكي أيضاً.
// يسمح فقط بما تحتاجه اللوحة: ملفات content/** ، وتشغيل سير عمل النشر/اللوحة/التوليد/معاينة الريل، وقراءة حالة تشغيلها.
const { createHmac, timingSafeEqual } = require('node:crypto');

const REPO = process.env.GITHUB_REPO || 'engshadi-79/social-publisher';
const WORKFLOWS = /^actions\/workflows\/(publish|dashboard|generate|health|daily|reel-preview)\.yml\/dispatches$/;
const RUNS = /^actions\/workflows\/(dashboard|reel-preview|generate)\.yml\/runs$/;   // متابعة التحديث بعد الحفظ (قراءة فقط)
const CONTENT = /^contents\/content\/[A-Za-z0-9._\-\/]+$/;

const sessionToken = (pw) => createHmac('sha256', pw).update('social-dashboard-session-v1').digest('hex');
const eq = (a, b) => { const x = Buffer.from(String(a)), y = Buffer.from(String(b)); return x.length === y.length && timingSafeEqual(x, y); };
const cookieOf = (req, name) => {
  const m = String(req.headers.cookie || '').split(/;\s*/).find((c) => c.startsWith(name + '='));
  return m ? decodeURIComponent(m.slice(name.length + 1)) : '';
};

module.exports = async (req, res) => {
  const pw = process.env.DASHBOARD_PASSWORD || '';
  const pat = process.env.GITHUB_PAT || '';
  if (!pw || !eq(cookieOf(req, 'dash_auth'), sessionToken(pw))) return res.status(401).json({ error: 'unauthorized' });
  if (!pat) return res.status(501).json({ error: 'GITHUB_PAT غير مضبوط على الخادم' });

  const url = new URL(req.url, 'http://x');
  const path = url.searchParams.get('p') || '';
  const method = req.method;
  const ok = (method === 'POST' && WORKFLOWS.test(path)) ||
             (['GET', 'PUT', 'DELETE'].includes(method) && CONTENT.test(path.split('?')[0]) && !path.includes('..')) ||
             (method === 'GET' && RUNS.test(path.split('?')[0]));
  if (!ok) return res.status(403).json({ error: 'forbidden' });

  let body;
  if (method !== 'GET' && method !== 'DELETE' || method === 'DELETE') {
    body = typeof req.body === 'string' ? req.body : (req.body ? JSON.stringify(req.body) : undefined);
  }
  const r = await fetch(`https://api.github.com/repos/${REPO}/${path}`, {
    method,
    headers: { Authorization: `Bearer ${pat}`, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json', 'User-Agent': 'social-dashboard' },
    body: method === 'GET' ? undefined : body,
  });
  const text = await r.text();
  res.status(r.status).setHeader('content-type', 'application/json').setHeader('cache-control', 'no-store').send(text || '{}');
};
