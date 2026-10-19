// ---- تعديل المنشورات، إعادة المحاولة، التقويم، التوزيع التلقائي (يُدرَج بعد dashboard_topics.js) ----
const POSTS = JSON.parse(document.getElementById("postdata").textContent);
const SFILE = "content/state.json";

function serializePost(p) {
  const im = p.image || {};
  let b = "- id: " + q(p.id) + "\n  approved: " + (p.approved ? "true" : "false") + "\n  publish_at: " + q(p.publish_at) +
    "\n  template: " + p.template + "\n";
  if (p.topic) b += "  topic: " + q(p.topic) + "\n";
  b += "  image:\n    title: " + q(im.title || "") + "\n    body: " + q(im.body || "") + "\n";
  if (im.points && im.points.length) b += "    points:\n" + im.points.map((x) => "      - " + q(x)).join("\n") + "\n";
  if (im.photo_query) b += "    photo_query: " + q(im.photo_query) + "\n";
  if (im.visual_prompt) b += "    visual_prompt: " + q(im.visual_prompt) + "\n";
  if (im.seed != null) b += "    seed: " + im.seed + "\n";
  b += "  platforms:\n";
  for (const [k, v] of Object.entries(p.platforms || {})) b += "    " + k + ": " + q(v) + "\n";
  return b;
}
function replacePost(text, id, obj) {
  const lines = text.split("\n"), [s, e] = postRange(lines, id);
  lines.splice(s, e - s, ...serializePost(obj).replace(/\n$/, "").split("\n"));
  return lines.join("\n");
}
function setWhen(text, id, when) {
  const lines = text.split("\n"), [s, e] = postRange(lines, id);
  for (let i = s; i < e; i++) if (/^  publish_at:/.test(lines[i])) { lines[i] = "  publish_at: " + q(when); return lines.join("\n"); }
  throw new Error("لم أجد موعد المنشور.");
}
async function deleteBg(id) {
  const path = "content/media/" + id + "-bg.png";
  let sha; try { sha = (await gh("contents/" + path)).sha; } catch (e) { return; }
  await gh("contents/" + path, { method: "DELETE", body: JSON.stringify({ message: "media: regenerate " + id, sha }) });
}

// ---------- نافذة التعديل ----------
const PLATS = ["facebook", "instagram", "threads", "telegram"];
let editId = null;
function openEdit(id) {
  const p = POSTS[id]; if (!p) return;
  editId = id; const im = p.image || {};
  $("eTitle").value = im.title || ""; $("eBody").value = im.body || ""; $("ePoints").value = (im.points || []).join("\n");
  $("eQuery").value = im.photo_query || ""; $("eVP").value = im.visual_prompt || "";
  $("eTemplate").value = p.template; $("eWhen").value = (p.publish_at || "").replace(" ", "T");
  if ($("eTopic")) $("eTopic").value = p.topic || "";
  PLATS.forEach((k) => { $("ep_" + k).checked = !!(p.platforms && p.platforms[k]); $("et_" + k).value = (p.platforms && p.platforms[k]) || ""; });
  $("eHead").textContent = "تعديل: " + (im.title || id);
  $("eNote").textContent = p.approved ? "هذا المنشور معتمد: سيُنشر بالنص الجديد في موعده." : "";
  say($("eMsg"), "", true); $("editBox").classList.add("on");
}
$("eCancel").onclick = () => $("editBox").classList.remove("on");
$("eSave").onclick = async () => {
  const m = $("eMsg"), v = (i) => $(i).value.trim(), old = POSTS[editId];
  const platforms = {};
  PLATS.forEach((k) => { if ($("ep_" + k).checked && v("et_" + k)) platforms[k] = v("et_" + k); });
  const tpl = $("eTemplate").value, points = v("ePoints").split("\n").map((x) => x.trim()).filter(Boolean);
  const err = !v("eTitle") ? "العنوان مطلوب." : !Object.keys(platforms).length ? "اختر منصة واحدة على الأقل بنص غير فارغ." :
    !v("eWhen") ? "اختر الموعد." : (tpl === "infographic" && (points.length < 2 || points.length > 6)) ? "الإنفوجرافك يحتاج من 2 إلى 6 نقاط." :
    (tpl !== "infographic" && !(v("eQuery") || v("eVP"))) ? "اكتب كلمات إنجليزية للصورة." :
    (platforms.threads && platforms.threads.length > 500) ? "نص ثريدز أطول من 500 حرف." :
    (platforms.instagram && platforms.instagram.length > 2200) ? "نص إنستغرام أطول من 2200 حرف." :
    ($("eTopic") && !v("eTopic")) ? "اختر الموضوع." : "";
  if (err) { say(m, err, false); return; }
  const oi = old.image || {};
  const img = { title: v("eTitle"), body: v("eBody"), seed: oi.seed != null ? oi.seed : 1 };
  if (tpl === "infographic") img.points = points; else { img.photo_query = v("eQuery"); if (v("eVP")) img.visual_prompt = v("eVP"); }
  const nu = { id: editId, approved: old.approved, publish_at: v("eWhen").replace("T", " "), template: tpl,
    topic: $("eTopic") ? v("eTopic") : old.topic, image: img, platforms };
  const imageChanged = tpl !== old.template || img.photo_query !== oi.photo_query || img.visual_prompt !== oi.visual_prompt;
  try {
    say(m, "جارٍ الحفظ…", true);
    await edit((x) => replacePost(x, editId, nu), "queue: edit " + editId, QFILE);
    if (imageChanged) await deleteBg(editId);
    say(m, "تم الحفظ ✅ تتحدّث اللوحة (وصورتها إن تغيّرت) خلال دقيقتين.", true);
    setTimeout(() => $("editBox").classList.remove("on"), 1200);
  } catch (e) { say(m, e.message, false); }
};

// ---------- إعادة المحاولة ----------
async function retryPost(id) {
  await edit((text) => {
    const s = JSON.parse(text || "{}"), e = s[id];
    if (!e) throw new Error("لا توجد حالة لهذا المنشور.");
    for (const k of Object.keys(e)) if (e[k].status !== "published") delete e[k];
    if (!Object.keys(e).length) delete s[id];
    return JSON.stringify(s, null, 2) + "\n";
  }, "state: retry " + id, SFILE);
}

// ---------- أزرار البطاقات الإضافية ----------
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-act]"); if (!b) return;
  if (b.dataset.act === "edit") { openEdit(b.dataset.id); return; }
  if (b.dataset.act === "now") {
    const out = b.closest(".post").querySelector(".actmsg"), id = b.dataset.id;
    if (!confirm("سأجعل موعده الآن وأشغّل النشر فوراً. متابعة؟")) return;
    const d = new Date(), pad = (n) => String(n).padStart(2, "0");
    const when = ymd(d) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
    try {
      say(out, "جارٍ الحفظ…", true);
      await edit((x) => setWhen(x, id, when), "queue: publish now " + id, QFILE);
      try { await gh("actions/workflows/publish.yml/dispatches", { method: "POST", body: JSON.stringify({ ref: "main" }) });
        say(out, "بدأ النشر الآن ✅ يستغرق دقائق، وتظهر النتيجة في اللوحة بعد ذلك.", true);
      } catch (e2) { say(out, "حُدِّث الموعد، لكن تشغيل النشر الفوري يحتاج أن يملك المفتاح صلاحية Actions: Read and write. سيُنشر في التشغيل الدوري القادم.", false); }
      b.disabled = true;
    } catch (err) { say(out, err.message, false); }
    return;
  }
  if (b.dataset.act === "retry") {
    const out = b.closest(".post").querySelector(".actmsg");
    try { say(out, "جارٍ الحفظ…", true); await retryPost(b.dataset.id);
      say(out, "ستُعاد المحاولة في التشغيل القادم للنشر (خلال 30 دقيقة تقريباً) ✅", true); b.disabled = true;
    } catch (err) { say(out, err.message, false); }
  }
});

// ---------- التقويم الأسبوعي ----------
const DAYS_AR = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"];
let weekStart = (() => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - d.getDay()); return d; })();
const ymd = (d) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
function renderCal() {
  const end = new Date(weekStart); end.setDate(end.getDate() + 6);
  $("calLabel").textContent = ymd(weekStart) + " ← " + ymd(end);
  const todayKey = ymd(new Date()); let html = "";
  for (let i = 0; i < 7; i++) {
    const d = new Date(weekStart); d.setDate(d.getDate() + i); const key = ymd(d);
    const list = Object.values(POSTS).filter((p) => (p.publish_at || "").startsWith(key)).sort((a, b) => a.publish_at.localeCompare(b.publish_at));
    html += '<div class="cday' + (key === todayKey ? " today" : "") + '"><div class="cdh">' + DAYS_AR[d.getDay()] + " " + d.getDate() + "</div>" +
      (list.length ? list.map((p) => '<button class="cchip g-' + p.group + '" data-cal="' + p.id + '"><b dir="ltr">' + p.publish_at.slice(11) + "</b> " +
        (p.image && p.image.title ? p.image.title.replace(/</g, "&lt;") : p.id) + "</button>").join("") : '<div class="cempty">فراغ</div>') + "</div>";
  }
  $("calGrid").innerHTML = html;
}
$("calPrev").onclick = () => { weekStart.setDate(weekStart.getDate() - 7); renderCal(); };
$("calNext").onclick = () => { weekStart.setDate(weekStart.getDate() + 7); renderCal(); };
$("calToday").onclick = () => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - d.getDay()); weekStart = d; renderCal(); };
$("calGrid").onclick = (e) => { const c = e.target.closest("[data-cal]"); if (!c) return; const p = POSTS[c.dataset.cal];
  if (p && (p.group === "draft" || p.group === "upcoming")) openEdit(p.id); };
document.querySelector("button[data-f=calendar]").addEventListener("click", renderCal);

// ---------- توزيع المسودات تلقائياً ----------
function planSchedule(posts, hour) {
  const taken = new Set(Object.values(posts).filter((p) => p.group !== "draft").map((p) => (p.publish_at || "").slice(0, 10)));
  const drafts = Object.values(posts).filter((p) => p.group === "draft").sort((a, b) => a.publish_at.localeCompare(b.publish_at));
  const day = new Date(); day.setHours(0, 0, 0, 0); day.setDate(day.getDate() + 1);
  return drafts.map((p) => { while (taken.has(ymd(day))) day.setDate(day.getDate() + 1);
    const when = ymd(day) + " " + hour; taken.add(ymd(day)); return { id: p.id, from: p.publish_at, when }; });
}
$("calDistribute").onclick = async () => {
  const m = $("calMsg"), plan = planSchedule(POSTS, $("calHour").value);
  if (!plan.length) { say(m, "لا توجد مسودات لتوزيعها.", false); return; }
  if (!confirm("سأضع المسودات في أيام فارغة بدءاً من الغد:\n\n" + plan.map((x) => x.when + "  ←  " + (POSTS[x.id].image.title || x.id)).join("\n") + "\n\nمتابعة؟")) return;
  try {
    say(m, "جارٍ الحفظ…", true);
    await edit((text) => plan.reduce((t, x) => setWhen(t, x.id, x.when), text), "queue: schedule drafts", QFILE);
    say(m, "تم التوزيع ✅ تظهر المواعيد الجديدة خلال دقيقة تقريباً.", true);
  } catch (e) { say(m, e.message, false); }
};
