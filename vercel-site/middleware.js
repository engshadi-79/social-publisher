// حماية لوحة التحكم على الخادم: لا يصل أي ملف (صفحة أو صورة) إلا بعد تسجيل الدخول.
// كلمة المرور في متغير البيئة DASHBOARD_PASSWORD على Vercel (لا تُكتب في الكود).
// إن لم تُضبط، يُغلق الموقع بالكامل (فشل آمن).
import { next } from '@vercel/functions';
import { createHmac, timingSafeEqual } from 'node:crypto';

export const config = { runtime: 'nodejs' };

const COOKIE = 'dash_auth';
const MAX_AGE = 60 * 60 * 24 * 30;

const token = (pw) => createHmac('sha256', pw).update('social-dashboard-session-v1').digest('hex');
const safeEq = (a, b) => {
  const x = Buffer.from(String(a)), y = Buffer.from(String(b));
  return x.length === y.length && timingSafeEqual(x, y);
};
const cookieOf = (req, name) => {
  const m = (req.headers.get('cookie') || '').split(/;\s*/).find((c) => c.startsWith(name + '='));
  return m ? decodeURIComponent(m.slice(name.length + 1)) : '';
};
const page = (msg = '', status = 200) => new Response(`<!doctype html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>لوحة التحكم</title>
<style>
:root{--bg:#f4f7fa;--card:#fff;--ink:#0b1f3a;--mute:#5d6b7c;--line:#e2e8ef;--teal:#0f9d8f}
@media (prefers-color-scheme:dark){:root{--bg:#0a111d;--card:#111b2b;--ink:#e8eef5;--mute:#93a1b3;--line:#1f2d41;--teal:#2dd4bf}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--ink);font-family:"Segoe UI",Tahoma,sans-serif}
form{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:30px 26px;width:min(92vw,380px);text-align:center;box-shadow:0 10px 40px rgba(0,0,0,.15)}
h1{font-size:1.2rem;margin:0 0 6px}p{color:var(--mute);margin:0 0 18px;font-size:.92rem}
input{width:100%;padding:12px 14px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font:inherit;margin-bottom:12px}
button{width:100%;padding:12px;border:0;border-radius:10px;background:var(--teal);color:#04211e;font:inherit;font-weight:800;cursor:pointer}
.err{color:#d64545;min-height:1.4em;margin-top:10px;font-size:.9rem}
</style></head><body>
<form method="post" action="/login"><h1>🔒 لوحة التحكم</h1><p>أدخل كلمة المرور للمتابعة.</p>
<input name="password" type="password" autocomplete="current-password" placeholder="كلمة المرور" autofocus required>
<button type="submit">دخول</button><div class="err" role="alert">${msg}</div></form></body></html>`,
  { status, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } });

export default async function middleware(request) {
  const pw = process.env.DASHBOARD_PASSWORD || '';
  if (!pw) return page('الموقع مغلق: لم تُضبط كلمة المرور على الخادم بعد.', 503);

  const url = new URL(request.url);
  const expected = token(pw);

  // عدّاد الزيارات يستقبل نبضات موقع المهندس من أي زائر: بلا جلسة، ولا يكشف شيئاً (يكتب أرقاماً فقط)
  if (url.pathname === '/api/hit') return next();

  if (url.pathname === '/login' && request.method === 'POST') {
    const form = await request.formData();
    if (safeEq(form.get('password') || '', pw)) {
      return new Response(null, { status: 303, headers: {
        location: '/',
        'set-cookie': `${COOKIE}=${expected}; Path=/; Max-Age=${MAX_AGE}; HttpOnly; Secure; SameSite=Strict`,
      } });
    }
    await new Promise((r) => setTimeout(r, 900));          // يبطّئ التخمين المتكرر
    return page('كلمة المرور غير صحيحة.', 401);
  }
  if (url.pathname === '/logout') {
    return new Response(null, { status: 303, headers: { location: '/login', 'set-cookie': `${COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict` } });
  }
  if (safeEq(cookieOf(request, COOKIE), expected)) {
    return url.pathname === '/login' ? new Response(null, { status: 303, headers: { location: '/' } }) : next();
  }
  return url.pathname === '/login' ? page() : new Response(null, { status: 303, headers: { location: '/login' } });
}
