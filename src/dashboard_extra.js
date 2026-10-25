// ---- إضافات v5 (يُدرَج بعد dashboard_posts.js): معاينة الريل، ولّد بديلاً، النشر التلقائي لريل الصباح،
//      السحب في التقويم، شريط متابعة التحديث بعد الحفظ، زوار الموقع من كل منصة ----
const SETTINGS = JSON.parse(($("setdata") || {}).textContent || "{}");
const PAGES = window.PAGES_BASE || "";

// ---------- شاهد الفيديو قبل الموافقة ----------
// الفيديو يُبنى عند الطلب (reel-preview.yml) باسم يحمل بصمة المحتوى، والنشر يستعمل الملف نفسه.
function probeVideo(url) {
  return new Promise((resolve) => {
    const v = document.createElement("video"); let settled = false;
    const done = (ok) => { if (settled) return; settled = true; v.removeAttribute("src"); v.load(); resolve(ok); };
    v.preload = "metadata"; v.muted = true;
    v.onloadedmetadata = () => done(true); v.onerror = () => done(false);
    setTimeout(() => done(false), 15000);
    v.src = url + "?t=" + Date.now();
  });
}
function playInLb(url) {
  const lb = $("lb"), img = lb.querySelector("img"), v = $("lbVid");
  v.src = url; v.hidden = false; img.hidden = true; lb.classList.remove("multi"); lb.classList.add("on"); v.play().catch(() => {});
}
function watchUntilReady(btn, out, url) {
  const t0 = Date.now(); btn.disabled = true;
  const tick = async () => {
    if (await probeVideo(url)) { btn.disabled = false; say(out, "✅ الفيديو جاهز. اضغط «شاهد الفيديو».", true); toast("فيديو الريل جاهز ✓", true); return; }
    if (Date.now() - t0 > 15 * 60e3) { btn.disabled = false; say(out, "تأخّر بناء الفيديو. أعد المحاولة بعد قليل.", false); return; }
    setTimeout(tick, 25000);
  };
  setTimeout(tick, 90000);
}
document.addEventListener("click", async (e) => {
  const b = e.target.closest('[data-act="watch"]'); if (!b) return;
  const id = b.dataset.id, url = PAGES + "images/" + b.dataset.vname, out = b.closest(".post").querySelector(".actmsg");
  say(out, "أتحقق من الفيديو…", true);
  if (await probeVideo(url)) { say(out, "", true); playInLb(url); return; }
  if (!confirm("لم يُبنَ فيديو هذا الريل بعد (أو تغيّر بعد التعديل). أبنيه الآن؟\nيستغرق 3 إلى 5 دقائق، وأُعلمك هنا عندما يجهز. والنشر يستعمل هذا الفيديو نفسه.")) { say(out, "", true); return; }
  try {
    await gh("actions/workflows/reel-preview.yml/dispatches", { method: "POST", body: JSON.stringify({ ref: "main", inputs: { id } }) });
    say(out, "⏳ جارٍ بناء الفيديو (3–5 دقائق). تابع عملك، وسأُعلمك هنا عندما يجهز.", true);
    watchUntilReady(b, out, url);
  } catch (err) { say(out, err.message, false); }
});

// ---------- ولّد بديلاً ----------
document.addEventListener("click", async (e) => {
  const b = e.target.closest('[data-act="regen"]'); if (!b) return;
  const p = POSTS[b.dataset.id], out = b.closest(".post").querySelector(".actmsg"); if (!p) return;
  const title = (p.image && p.image.title) || p.id;
  if (!confirm("سأكتب منشوراً جديداً مكان «" + title + "»، في الموعد نفسه (" + p.publish_at + ") وبالقالب نفسه، ويُحذف الحالي.\nيصل البديل مسودة لتراجعها. متابعة؟")) return;
  const rid = "r" + Date.now().toString(36);
  try {
    say(out, "جارٍ إرسال الطلب…", true);
    await putRequest("id: " + q(rid) + "\nreplace: " + q(p.id) + "\n", "generate: regen " + p.id);
    say(out, "⏳ يُكتب البديل الآن (دقيقتان تقريباً)، ثم تتحدّث اللوحة وحدها.", true);
    b.parentElement.querySelectorAll("button").forEach((x) => (x.disabled = true));
  } catch (err) { say(out, err.message, false); }
});

// ---------- النشر التلقائي لريل الصباح ----------
(function autoMorning() {
  const box = $("autoMorning"); if (!box) return;
  box.onchange = async () => {
    const on = box.checked;
    const ids = Object.values(POSTS).filter((p) => p.image && p.image.style === "morning" && (on ? p.group === "draft" : p.group === "upcoming")).map((p) => p.id);
    const msg = on
      ? "سيُنشر ريل الصباح كل يوم الساعة 9:00 دون أن تراجعه." + (ids.length ? "\nوسأوافق الآن على " + ids.length + " ريل صباحي قادم ينتظر موافقتك." : "") + "\nمتابعة؟"
      : "سيعود ريل الصباح مسودة تنتظر موافقتك كل يوم." + (ids.length ? "\nوسأُلغي موافقة " + ids.length + " ريل صباحي قادم لم يُنشر بعد." : "") + "\nمتابعة؟";
    if (!confirm(msg)) { box.checked = !on; return; }
    box.disabled = true;
    try {
      await edit((x) => JSON.stringify(Object.assign(JSON.parse(x || "{}"), { auto_approve_morning: on }), null, 2) + "\n",
        "settings: auto-approve morning " + (on ? "on" : "off"), "content/settings.json");
      if (ids.length) await edit((x) => ids.reduce((t, id) => setApproved(t, id, on ? "true" : "false"), x), "queue: morning auto " + (on ? "on" : "off"), QFILE);
      SETTINGS.auto_approve_morning = on;
      toast(on ? "☀️ ريل الصباح يُنشر تلقائياً من الآن ✓" : "ريل الصباح يعود مسودة تنتظر موافقتك ✓", true);
    } catch (err) { box.checked = !on; toast(err.message, false); }
    box.disabled = false;
  };
})();

// ---------- التقويم: سحب منشور إلى يوم آخر ----------
(function calDrag() {
  const cg = $("calGrid"); if (!cg) return;
  const clear = () => cg.querySelectorAll(".cday.over").forEach((d) => d.classList.remove("over"));
  cg.addEventListener("dragstart", (e) => {
    const c = e.target.closest("[data-cal]"); if (!c || c.getAttribute("draggable") !== "true") return;
    e.dataTransfer.setData("text/plain", c.dataset.cal); e.dataTransfer.effectAllowed = "move"; c.classList.add("dragging");
  });
  cg.addEventListener("dragend", (e) => { const c = e.target.closest("[data-cal]"); if (c) c.classList.remove("dragging"); clear(); });
  cg.addEventListener("dragover", (e) => {
    const d = e.target.closest(".cday[data-day]"); if (!d) return;
    e.preventDefault(); e.dataTransfer.dropEffect = "move";
    if (!d.classList.contains("over")) { clear(); d.classList.add("over"); }
  });
  cg.addEventListener("drop", async (e) => {
    const d = e.target.closest(".cday[data-day]"); if (!d) return;
    e.preventDefault(); clear();
    const id = e.dataTransfer.getData("text/plain"), p = POSTS[id]; if (!p) return;
    const day = d.dataset.day; if ((p.publish_at || "").startsWith(day)) return;
    const when = day + " " + (p.publish_at || "").slice(11, 16), now = nowLocal();
    if (day < now.slice(0, 10)) { toast("لا يمكن نقل منشور إلى يوم مضى.", false); return; }
    if (when <= now && p.group === "upcoming" && !confirm("هذا الموعد مضى اليوم، والمنشور معتمد: سيُنشر في التشغيل القادم (خلال 30 دقيقة). متابعة؟")) return;
    try {
      await edit((x) => setWhen(x, id, when), "queue: move " + id + " to " + when, QFILE);
      p.publish_at = when; renderCal(); toast("نُقل إلى " + when + " ✓", true);
    } catch (err) { toast(err.message, false); }
  });
})();

// ---------- شريط متابعة التحديث بعد الحفظ ----------
// كل حفظ يشغّل بناء اللوحة على GitHub (1–3 دقائق)؛ نتابع التشغيل ونعرض متى تجهز النسخة الجديدة.
const sync = { since: 0, t: null };
function syncBar(html, cls) {
  const bar = $("syncbar"); if (!bar) return;
  if (!html) { bar.hidden = true; return; }
  bar.className = cls || ""; bar.innerHTML = html; bar.hidden = false;
  const r = bar.querySelector("[data-reload]"); if (r) r.onclick = () => location.reload();
  const x = bar.querySelector("[data-close]"); if (x) x.onclick = () => { bar.hidden = true; clearTimeout(sync.t); };
}
window.onSaved = (kind) => {
  if (!PROXY) return;
  if (!sync.since) sync.since = Date.now() - 20000;     // نتابع كل التشغيلات منذ أول حفظ لم يكتمل بعد
  syncBar('<span class="spin"></span> حُفظ ✓ ' + (kind === "generate" ? "يجري التوليد ثم تحديث اللوحة…" : "تُحدَّث اللوحة الآن (1–3 دقائق)…"), "");
  clearTimeout(sync.t); sync.t = setTimeout(pollSync, 15000);
};
async function pollSync() {
  try {
    const r = await gh("actions/workflows/dashboard.yml/runs?per_page=10");
    const runs = (r.workflow_runs || []).filter((x) => Date.parse(x.created_at) >= sync.since);
    const age = Math.round((Date.now() - sync.since) / 60000);
    if (!runs.length) {
      if (age > 8) { syncBar(""); sync.since = 0; return; }
      syncBar('<span class="spin"></span> بانتظار بدء تحديث اللوحة…', ""); sync.t = setTimeout(pollSync, 15000); return;
    }
    const pending = runs.filter((x) => x.status !== "completed");
    if (pending.length) {
      const st = pending.some((x) => x.status === "in_progress") ? "تُبنى اللوحة الجديدة" : "في الدور خلف عملية أخرى";
      syncBar('<span class="spin"></span> ' + st + "… (" + Math.max(1, age) + " د)", ""); sync.t = setTimeout(pollSync, 12000); return;
    }
    const last = runs[0]; sync.since = 0;
    if (last.conclusion === "success") syncBar('✅ اللوحة محدّثة بآخر تعديلاتك <button type="button" data-reload>اعرض التحديث</button>', "ok");
    else syncBar('⚠️ تعذّر تحديث اللوحة هذه المرة (' + last.conclusion + '). حُفظ تعديلك، ويظهر مع التحديث القادم. <button type="button" data-close>إغلاق</button>', "no");
  } catch (e) { syncBar(""); sync.since = 0; }
}

// ---------- زوار الموقع من كل منصة ----------
const SRC_AR = { facebook: "فيسبوك", instagram: "إنستغرام", threads: "ثريدز", linkedin: "لينكدإن", telegram: "تيليجرام", google: "بحث Google", other: "مواقع أخرى", direct: "مباشر" };
let visitsLoaded = false;
async function loadVisits() {
  if (visitsLoaded) return; visitsLoaded = true;
  const note = $("visitsNote"), body = $("visitsBody"); if (!note || !body) return;
  if (!PROXY) { note.textContent = "تظهر أرقام الزوار في نسخة اللوحة على Vercel فقط."; return; }
  let d;
  try { const r = await fetch("/api/visits", { credentials: "same-origin" }); d = await r.json(); }
  catch (e) { note.textContent = "تعذّر جلب أرقام الزوار الآن."; visitsLoaded = false; return; }
  if (!d.configured) {
    note.innerHTML = "العدّاد جاهز في موقعك، وينقصه مكان مجاني يحفظ فيه الأرقام. خطوة واحدة منك (دقيقة):" +
      '<ol class="vsteps"><li>افتح <b>vercel.com</b> ← مشروع <b>social-dashboard</b> ← تبويب <b>Storage</b>.</li>' +
      "<li>اضغط <b>Create Database</b> واختر <b>Upstash for Redis</b> بالخطة المجانية <b>Free</b>، ثم <b>Connect</b> بهذا المشروع.</li>" +
      "<li>أخبرني «تم» لأعيد نشر اللوحة، فتبدأ الأرقام بالظهور هنا من أول زائر.</li></ol>";
    return;
  }
  if (d.error) { note.textContent = d.error; return; }
  const days = d.days || [];
  const sum = (n) => { const t = {}; days.slice(0, n).forEach((x) => Object.entries(x.counts).forEach(([k, v]) => (t[k] = (t[k] || 0) + v))); return t; };
  const w = sum(7), m = sum(30), total = (o) => Object.values(o).reduce((a, b) => a + b, 0);
  if (!total(sum(60))) { note.textContent = "لا زيارات مسجّلة بعد. يُحسب كل زائر يفتح موقعك مرة واحدة في الجلسة، ويُعرف مصدره من رابط السيرة أو من الموقع الذي جاء منه."; return; }
  note.textContent = "آخر 7 أيام: " + total(w) + " زيارة · آخر 30 يوماً: " + total(m) + " زيارة. الزيارة = زائر فتح الموقع (مرة لكل جلسة).";
  const rows = Object.entries(m).sort((a, b) => b[1] - a[1]), mx = rows.length ? rows[0][1] : 1;
  const series = days.slice(0, 30).reverse(), smx = Math.max(1, ...series.map((x) => total(x.counts)));
  body.innerHTML = "<h3>المصادر في آخر 30 يوماً</h3><div class=\"vbars\">" + rows.map(([k, v]) =>
      '<div class="vbar"><span>' + (SRC_AR[k] || k) + '</span><i><b style="width:' + Math.round(v / mx * 100) + '%"></b></i><span>' + v + " (" + (w[k] || 0) + " هذا الأسبوع)</span></div>").join("") + "</div>" +
    "<h3>الزيارات يومياً (30 يوماً)</h3><div class=\"vdays\">" + series.map((x) => {
      const t = total(x.counts); return '<span style="height:' + Math.round(t / smx * 100) + '%" data-t="' + x.day.slice(5) + ": " + t + '"></span>'; }).join("") + "</div>";
}
document.querySelectorAll("button[data-f=stats]").forEach((b) => b.addEventListener("click", loadVisits));
if (location.hash === "#stats") loadVisits();
