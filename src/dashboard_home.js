// ---- الصفحة الرئيسية «لوحة التحكم» (v6): ملخص حقيقي من المنشورات والإحصاءات وزيارات الموقع ----
const HEALTH = JSON.parse(($("healthdata") || {}).textContent || "{}");
const TPL_AR = { infographic: "إنفوجرافك", carousel: "كاروسيل", reel: "ريل", split: "صورة", photo: "صورة", tip: "نصيحة", quote: "اقتباس", announcement: "إعلان", story: "ستوري" };
const PL_MINI = { facebook: "f", instagram: "ig", threads: "@", linkedin: "in", telegram: "tg" };
const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtN = (n) => n >= 10000 ? (n / 1000).toFixed(1).replace(/\.0$/, "") + "K" : n.toLocaleString("en-US");
const dayKey = (d) => ymd(d);
const daysAgo = (n) => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - n); return d; };
const titleOf = (p) => (p.image && p.image.title) || p.id;
let VISITS = null;                                     // {configured, days:[{day, counts}]} من /api/visits

function postMetrics(id) {
  const per = INS[id] || {}; let reach = 0, eng = 0, likes = 0, comments = 0, any = false;
  Object.values(per).forEach((m) => {
    if (!m || m.error) return; any = true;
    reach += (m.reach || 0) + (m.views || 0);
    likes += m.likes || 0; comments += m.comments || 0;
    eng += (m.likes || 0) + (m.comments || 0) + (m.shares || 0) + (m.saved || 0);
  });
  return any ? { reach, eng, likes, comments } : null;
}
function inRange(p, from, to) { const d = (p.publish_at || "").slice(0, 10); return d >= dayKey(from) && d <= dayKey(to); }
function trendHtml(cur, prev) {
  if (!prev) return "";
  const pct = Math.round((cur - prev) / prev * 100);
  return '<span class="hv-trend' + (pct < 0 ? " down" : "") + '">' + (pct < 0 ? "↓ " : "↑ ") + Math.abs(pct) + "%</span>";
}
function visitsSum(fromN, toN) {                       // أيام مضت: من fromN إلى toN (0 = اليوم)
  if (!VISITS || !VISITS.days) return null;
  const t = {}; let total = 0;
  VISITS.days.forEach((x, i) => { if (i >= toN && i < fromN) Object.entries(x.counts).forEach(([k, v]) => { t[k] = (t[k] || 0) + v; total += v; }); });
  return { total, bySrc: t };
}

// ---------- المؤشرات الأربعة + الرسم ----------
function renderMetrics() {
  const R = parseInt(($("hvRange") || {}).value || "30", 10);
  const now = new Date(), from = daysAgo(R - 1), pFrom = daysAgo(2 * R - 1), pTo = daysAgo(R);
  const pub = Object.values(POSTS).filter((p) => p.group === "published");
  const agg = (list) => list.reduce((a, p) => { const m = postMetrics(p.id); if (m) { a.reach += m.reach; a.eng += m.eng; a.n++; } return a; }, { reach: 0, eng: 0, n: 0 });
  const cur = agg(pub.filter((p) => inRange(p, from, now))), prev = agg(pub.filter((p) => inRange(p, pFrom, pTo)));
  $("mReach").textContent = cur.n ? fmtN(cur.reach) : "—";
  $("mReachF").innerHTML = cur.n ? trendHtml(cur.reach, prev.reach) + "<span>من " + cur.n + " منشوراً مقيساً</span>" : "<span>تظهر بعد فحص الإحصاءات اليومي</span>";
  $("mEng").textContent = cur.n ? fmtN(cur.eng) : "—";
  $("mEngF").innerHTML = (cur.n ? trendHtml(cur.eng, prev.eng) : "") + "<span>إعجاب وتعليق ومشاركة وحفظ</span>";
  const v = visitsSum(R, 0), vp = R <= 30 ? visitsSum(2 * R, R) : null;
  if (!PROXY) { $("mVisits").textContent = "—"; $("mVisitsF").innerHTML = "<span>تظهر في نسخة Vercel</span>"; }
  else if (!VISITS) { $("mVisits").textContent = "…"; }
  else if (!VISITS.configured) { $("mVisits").textContent = "—"; $("mVisitsF").innerHTML = "<span>العدّاد غير مربوط بعد</span>"; }
  else { $("mVisits").textContent = fmtN(v.total); $("mVisitsF").innerHTML = (vp ? trendHtml(v.total, vp.total) : "") + "<span>زائر فتح موقعك (مرة لكل جلسة)</span>"; }
  const ym = ymd(now).slice(0, 7), pm = ymd(new Date(now.getFullYear(), now.getMonth() - 1, 1)).slice(0, 7);
  const thisM = pub.filter((p) => p.publish_at.startsWith(ym)).length, lastM = pub.filter((p) => p.publish_at.startsWith(pm)).length;
  const sched = Object.values(POSTS).filter((p) => p.group === "upcoming" && p.publish_at.startsWith(ym)).length;
  $("mMonth").textContent = thisM;
  $("mMonthF").innerHTML = (thisM - lastM ? '<span class="hv-trend' + (thisM < lastM ? " down" : "") + '">' + (thisM >= lastM ? "↑ " : "↓ ") + Math.abs(thisM - lastM) + "</span><span>عن الشهر السابق</span>" : "<span>مثل الشهر السابق</span>") + (sched ? "<span>· " + sched + " مجدول</span>" : "");
  renderChart(R, pub);
  renderUtm(R);
}

function smoothPath(pts) {                              // منحنى ناعم يمرّ بالنقاط (Catmull-Rom → Bézier)
  if (pts.length < 2) return "";
  let d = "M" + pts[0][0].toFixed(1) + " " + pts[0][1].toFixed(1);
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
    const lo = Math.min(p1[1], p2[1]), hi = Math.max(p1[1], p2[1]), cl = (y) => Math.min(hi, Math.max(lo, y));   // لا ينزل المنحنى تحت المحور
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, cl(p1[1] + (p2[1] - p0[1]) / 6)], c2 = [p2[0] - (p3[0] - p1[0]) / 6, cl(p2[1] - (p3[1] - p1[1]) / 6)];
    d += " C" + c1.map((x) => x.toFixed(1)).join(" ") + " " + c2.map((x) => x.toFixed(1)).join(" ") + " " + p2[0].toFixed(1) + " " + p2[1].toFixed(1);
  }
  return d;
}
function renderChart(R, pub) {
  const days = [], reach = [], eng = [];
  for (let i = R - 1; i >= 0; i--) { days.push(dayKey(daysAgo(i))); reach.push(0); eng.push(0); }
  pub.forEach((p) => { const k = days.indexOf(p.publish_at.slice(0, 10)), m = postMetrics(p.id); if (k >= 0 && m) { reach[k] += m.reach; eng[k] += m.eng; } });
  const tr = reach.reduce((a, b) => a + b, 0), te = eng.reduce((a, b) => a + b, 0);
  $("cReach").textContent = tr ? fmtN(tr) : "—"; $("cEng").textContent = te ? fmtN(te) : "—";
  const box = $("hvChart");
  if (!tr && !te) { box.innerHTML = '<div class="hv-empty" style="height:100%;display:grid;place-items:center">لا أرقام في هذه الفترة بعد. تُسحب إحصاءات المنشورات مع الفحص اليومي.</div>'; return; }
  const W = 700, H = 190, L = 10, Rr = 690, T = 14, B = 168, n = days.length;
  const x = (i) => L + (Rr - L) * (n === 1 ? 0.5 : i / (n - 1));
  const mr = Math.max(1, ...reach), me = Math.max(1, ...eng);       // كل خط بمقياسه ليظهر شكله
  const pr = reach.map((v, i) => [x(i), B - (B - T) * v / mr]), pe = eng.map((v, i) => [x(i), B - (B - T) * 0.82 * v / me]);
  const lineR = smoothPath(pr), lineE = smoothPath(pe);
  const grid = [0, 1, 2, 3, 4].map((k) => "M" + L + " " + (T + (B - T) * k / 4) + "H" + Rr).join("");
  const ticks = [0, Math.round((n - 1) / 4), Math.round((n - 1) / 2), Math.round(3 * (n - 1) / 4), n - 1].filter((v, i, a) => a.indexOf(v) === i);
  const lab = (k) => { const d = new Date(days[k]); return k === n - 1 ? "اليوم" : d.getDate() + "/" + (d.getMonth() + 1); };
  box.innerHTML = '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none" role="img" aria-label="الوصول والتفاعل يومياً">' +
    '<defs><linearGradient id="hvLG" x1="0" x2="1"><stop offset="0" stop-color="#9271ff"/><stop offset="1" stop-color="#4e8dff"/></linearGradient>' +
    '<linearGradient id="hvAG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#9271ff" stop-opacity=".24"/><stop offset="1" stop-color="#9271ff" stop-opacity="0"/></linearGradient></defs>' +
    '<path d="' + grid + '" stroke="#29334a" stroke-width="1" stroke-dasharray="3 5" fill="none"/>' +
    '<path d="' + lineR + " L" + Rr + " " + B + " L" + L + " " + B + 'Z" fill="url(#hvAG)"/>' +
    '<path d="' + lineR + '" fill="none" stroke="url(#hvLG)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>' +
    '<path d="' + lineE + '" fill="none" stroke="#4e8dff" stroke-width="2" stroke-linecap="round" stroke-dasharray="5 5" vector-effect="non-scaling-stroke"/>' +
    ticks.map((k) => '<text x="' + x(k) + '" y="186" fill="#74819e" font-size="11" text-anchor="' + (k === 0 ? "start" : k === n - 1 ? "end" : "middle") + '" direction="ltr">' + lab(k) + "</text>").join("") +
    "</svg>";
}

// ---------- المنصات ----------
function renderPlatforms() {
  const items = (HEALTH.items || []), box = $("hvPlats"); let ok = 0;
  const rows = ACC.map((a) => {
    const h = items.find((x) => x.name === a.label) || {};
    const st = h.status || "off"; if (st === "ok") ok++;
    const lbl = { ok: "متصل", warn: "تنبيه", bad: "خطأ", off: "غير مُعدّ" }[st] || st;
    const nm = (a.label.split("—")[1] || a.label).trim();
    return '<div class="hv-plat"><div class="hv-plogo ' + a.platform + '">' + (PL_MINI[a.platform] || "•") + '</div><div class="hv-pinfo"><strong>' + esc(PLAT_NAME[a.platform] || a.platform) +
      "</strong><span>" + esc(st === "ok" ? nm : (h.detail || nm)) + '</span></div><span class="hv-pstate ' + st + '">' + lbl + "</span></div>";
  });
  box.innerHTML = rows.join("") || '<div class="hv-empty">لا حسابات بعد.</div>';
  const active = ACC.length - ACC.filter((a) => ((items.find((x) => x.name === a.label) || {}).status || "off") === "off").length;
  $("hvPfoot").textContent = ok + " من " + active + " منصات تعمل" + (HEALTH.checked_at ? " · آخر فحص " + HEALTH.checked_at.slice(0, 10) : "");
  $("hvConn").innerHTML = '<i class="hv-dot' + (ok < active ? " warn" : "") + '"></i>' + ok + " منصات متصلة";
}

// ---------- القوائم: بانتظارك، القادم، الأفضل ----------
const whenAr = (pa) => {
  const d = pa.slice(0, 10), t = pa.slice(11, 16), today = ymd(new Date()), tm = ymd(daysAgo(-1));
  return (d === today ? "اليوم" : d === tm ? "غداً" : DAYS_AR[new Date(d).getDay()]) + "<br>" + t;
};
function thumb(p) { return "images/thumb-" + p.id + (p.tok || "") + ".jpg"; }
function renderLists() {
  const all = Object.values(POSTS).sort((a, b) => a.publish_at.localeCompare(b.publish_at));
  const drafts = all.filter((p) => p.group === "draft").slice(0, 3);
  $("hvDrafts").innerHTML = drafts.length ? drafts.map((p) => '<button class="hv-draft" type="button" data-open="' + p.id + '"><img loading="lazy" src="' + thumb(p) + '" alt=""><div class="hv-dbody"><strong>' + esc(titleOf(p)) +
      '</strong><div class="hv-tags"><span class="hv-tag orange">' + esc(p.publish_at.slice(5, 16).replace(" ", " · ")) + '</span><span class="hv-tag purple">' + (TPL_AR[p.template] || p.template) + "</span>" +
      Object.keys(p.platforms || {}).map((k) => '<span class="hv-tag">' + (PLAT_NAME[k] || k) + "</span>").join("") + "</div></div></button>").join("")
    : '<div class="hv-empty">لا مسودات تنتظرك ✓<br>تصلك مسودات جديدة كل صباح.</div>';
  const cols = ["#9271ff", "#4e8dff", "#54d8e8", "#42d6a0"];
  const next = all.filter((p) => p.group === "upcoming").slice(0, 4);
  $("hvSched").innerHTML = next.length ? next.map((p, i) => '<div class="hv-sitem" style="--c:' + cols[i % 4] + '"><div class="hv-stime">' + whenAr(p.publish_at) + '</div><div class="hv-sline"></div><div class="hv-scard"><strong>' + esc(titleOf(p)) +
      "</strong><span>" + (TPL_AR[p.template] || p.template) + (p.image && p.image.style === "morning" ? " · ☀️ ريل الصباح" : "") + '</span><div class="hv-mini">' +
      Object.keys(p.platforms || {}).map((k) => "<i>" + (PL_MINI[k] || "•") + "</i>").join("") + "</div></div></div>").join("")
    : '<div class="hv-empty">لا منشورات معتمدة قادمة. وافق على المسودات لتظهر هنا.</div>';
  const top = Object.values(POSTS).map((p) => ({ p, s: postScore(p.id), m: postMetrics(p.id) })).filter((r) => r.s != null).sort((a, b) => b.s - a.s).slice(0, 3);
  $("hvTop").innerHTML = top.length ? top.map((r, i) => '<div class="hv-top"><div class="hv-rank">0' + (i + 1) + '</div><div class="hv-tcopy"><strong>' + esc(titleOf(r.p)) + "</strong><p>" + (TPL_AR[r.p.template] || r.p.template) + " · " + r.p.publish_at.slice(0, 10) +
      '</p><div class="hv-tstats"><span>♡ ' + fmtN(r.m.likes) + "</span><span>💬 " + fmtN(r.m.comments) + "</span>" + (r.m.reach ? "<span>◉ " + fmtN(r.m.reach) + "</span>" : "") + "</div></div></div>").join("")
    : '<div class="hv-empty">تظهر أفضل المنشورات بعد أول فحص للإحصاءات.</div>';
}

// ---------- توصية من البيانات ----------
function renderAdvice() {
  const rows = Object.values(POSTS).map((p) => ({ p, s: postScore(p.id) })).filter((r) => r.s != null);
  if (rows.length < 4) return;
  const avgBy = (key) => { const g = {}; rows.forEach((r) => { const k = key(r.p); if (!k) return; (g[k] = g[k] || []).push(r.s); });
    return Object.entries(g).filter(([, v]) => v.length >= 2).map(([k, v]) => [k, v.reduce((a, b) => a + b, 0) / v.length, v.length]).sort((a, b) => b[1] - a[1]); };
  const hours = avgBy((p) => p.publish_at.slice(11, 13) + ":00"), tpls = avgBy((p) => p.template);
  const all = rows.reduce((a, r) => a + r.s, 0) / rows.length, bits = [];
  if (hours.length >= 2) bits.push("منشوراتك في الساعة <b dir=\"ltr\">" + hours[0][0] + "</b> تحصد في المتوسط <b>" + hours[0][1].toFixed(1) + "</b> نقطة تفاعل، مقابل <b>" + all.toFixed(1) + "</b> لكل منشوراتك.");
  if (tpls.length >= 2) bits.push("أقوى قالب لديك حتى الآن: <b>" + (TPL_AR[tpls[0][0]] || tpls[0][0]) + "</b> (" + tpls[0][2] + " منشورات).");
  if (bits.length) $("hvAdvice").innerHTML = bits.join(" ") + " الأرقام تقريبية وتدقّ كلما زادت المنشورات.";
}

// ---------- روابط التتبّع ----------
function renderUtm(R) {
  document.querySelectorAll(".hv-urow").forEach((row) => {
    const c = row.querySelector(".hv-ucount"), v = visitsSum(R, 0);
    c.innerHTML = (v ? fmtN(v.bySrc[row.dataset.src] || 0) : "—") + " <small>زيارة</small>";
  });
}

// ---------- التشغيل ----------
(function initHome() {
  if (!$("homeView")) return;
  try { $("todayChip").textContent = new Date().toLocaleDateString("ar-EG-u-nu-latn", { day: "numeric", month: "long", year: "numeric" }); } catch (e) {}
  document.addEventListener("click", (e) => {
    const g = e.target.closest("[data-go]"); if (g) { e.preventDefault(); show(g.dataset.go); return; }
    const o = e.target.closest("[data-open]");
    if (o) { show("draft"); const b = document.querySelector('.post [data-id="' + o.dataset.open + '"]'); if (b) setTimeout(() => b.closest(".post").scrollIntoView({ behavior: "smooth", block: "center" }), 60); }
  });
  $("hvDaily").onclick = async () => {
    if (!confirm("أولّد مسودات اليوم الآن؟ تستغرق دقائق، وتصلك في «بانتظار موافقتك».")) return;
    try { await dispatchWf("daily.yml"); toast("بدأ توليد المسودات ✓ تصلك بعد دقائق.", true); } catch (e) { toast(e.message, false); }
  };
  $("hvRange").onchange = renderMetrics;
  renderPlatforms(); renderLists(); renderAdvice(); renderMetrics();
  if (PROXY) fetch("/api/visits", { credentials: "same-origin" }).then((r) => r.json()).then((d) => { VISITS = d; renderMetrics(); })
    .catch(() => { VISITS = { configured: false }; renderMetrics(); });
})();
