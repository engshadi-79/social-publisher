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
  if (im.slides && im.slides.length) b += slidesYaml(im.slides);
  if (im.scenes && im.scenes.length) b += scenesYaml(im.scenes);
  if (im.photo_query) b += "    photo_query: " + q(im.photo_query) + "\n";
  if (im.style) b += "    style: " + q(im.style) + "\n";
  if (im.hue != null) b += "    hue: " + im.hue + "\n";
  if (im.bg_from) b += "    bg_from: " + q(im.bg_from) + "\n";
  if (im.visual_prompt) b += "    visual_prompt: " + q(im.visual_prompt) + "\n";
  if (im.seed != null) b += "    seed: " + im.seed + "\n";
  b += "  platforms:\n";
  for (const [k, v] of Object.entries(p.platforms || {})) b += "    " + k + ": " + q(v) + "\n";
  b += targetsYaml(p.targets);
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
function liveApproved(text, id) {
  const lines = text.split(String.fromCharCode(10)), [a, b] = postRange(lines, id);
  for (let i = a; i < b; i++) { const m = lines[i].match(/^  approved:\s*(\w+)/); if (m) return m[1] === "true"; }
  return false;
}
async function deleteBg(id) {
  const path = "content/media/" + id + "-bg.png";
  let sha; try { sha = (await gh("contents/" + path)).sha; } catch (e) { return; }
  await gh("contents/" + path, { method: "DELETE", body: JSON.stringify({ message: "media: regenerate " + id, sha }) });
}

// صور الشرائح/المشاهد المحفوظة تُستعمل ولو تغيّرت كلمات البحث، فنحذف ما تغيّر ليُجلب من جديد
async function deleteChangedPhotos(id, oldList, newList, oldBase, newBase) {
  const n = Math.max((oldList || []).length, (newList || []).length);
  for (let i = 1; i <= n; i++) {
    const o = (oldList || [])[i - 1] || {}, w = (newList || [])[i - 1] || {};
    if ((o.photo_query || oldBase || "") === (w.photo_query || newBase || "")) continue;
    const path = "content/media/" + id + "-s" + String(i).padStart(2, "0") + ".jpg";
    let sha; try { sha = (await gh("contents/" + path)).sha; } catch (e) { continue; }
    await gh("contents/" + path, { method: "DELETE", body: JSON.stringify({ message: "media: new photo " + id + " #" + i, sha }) });
  }
}

// ---------- نافذة التعديل ----------
// ---------- نمط التصميم ولونه ----------
const STYLES = {
  infographic: { cards: "بطاقات", bento: "بنتو", timeline: "خط زمني", bold: "جريء", glass: "زجاجي", steps: "درج", neon: "نيون", checklist: "قائمة تحقق", bignum: "الرقم الكبير", blueprint: "مخطط", pills: "كبسولات", columns: "شريط جانبي" },
  reel: { morning: "ريل الصباح (لقطات حقيقية)", motion: "موشن نيلي (بموسيقى)", "motion-sunset": "موشن غروب (بموسيقى)", "motion-mint": "موشن نعناعي (بموسيقى)", geo: "أشكال هندسية", bold: "جريء", split: "شقّان", card: "بطاقة", terminal: "طرفية", neon: "نيون", paper: "ورقي", mesh: "شبكة ألوان" },
  carousel: { blueprint: "مخطط", editorial: "مجلة", terminal: "طرفية", poster: "ملصق", sticky: "ورقة ملصقة", duo: "لوحان", neon: "نيون", paper: "ورقي", gradient: "تدرج" },
};
const HUES = [0, 35, 70, 140, 190, 250, 290, 325];
let eHue = null;
function fillLook(tpl, style, hue) {
  const box = $("eLook"), opts = STYLES[tpl];
  box.hidden = !(tpl === "infographic" || tpl === "carousel" || tpl === "reel");
  const sel = $("eStyle");
  sel.parentElement.querySelector("label").hidden = sel.hidden = !opts;
  sel.innerHTML = '<option value="">تلقائي</option>' + Object.entries(opts || {}).map(([k, n]) => '<option value="' + k + '">' + n + "</option>").join("");
  sel.value = opts && opts[style] ? style : "";
  eHue = hue != null ? hue : null;
  const hb = $("eHueBox");
  hb.innerHTML = '<button type="button" class="auto' + (eHue == null ? " on" : "") + '" data-h="">تلقائي</button>' +
    HUES.map((h) => '<button type="button" data-h="' + h + '" class="' + (eHue === h ? "on" : "") + '" style="background:hsl(' + ((215 + h) % 360) + ',58%,38%)" title="لون ' + (HUES.indexOf(h) + 1) + '"></button>').join("");
  hb.querySelectorAll("button").forEach((b) => (b.onclick = () => { eHue = b.dataset.h === "" ? null : parseInt(b.dataset.h, 10); hb.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); }));
}
const PLATS = ["facebook", "instagram", "threads", "linkedin", "telegram"];
let editId = null;
function openEdit(id) {
  const p = POSTS[id]; if (!p) return;
  editId = id; const im = p.image || {};
  $("eTitle").value = im.title || ""; $("eBody").value = im.body || ""; $("ePoints").value = (im.points || []).join("\n"); $("eSlides").value = p.template === "reel" ? scenesToText(im.scenes) : slidesToText(im.slides);
  $("eQuery").value = im.photo_query || ""; $("eVP").value = im.visual_prompt || "";
  $("eTemplate").value = p.template; fillLook(p.template, im.style, im.hue); $("eWhen").value = (p.publish_at || "").replace(" ", "T");
  if ($("eTopic")) $("eTopic").value = p.topic || "";
  PLATS.forEach((k) => { $("ep_" + k).checked = !!(p.platforms && p.platforms[k]); $("et_" + k).value = (p.platforms && p.platforms[k]) || ""; });
  accPicker("eAcc", p.targets || null);
  $("eHead").textContent = "تعديل: " + (im.title || id);
  $("eNote").textContent = p.approved ? "هذا المنشور معتمد: سيُنشر بالنص الجديد في موعده." : "";
  say($("eMsg"), "", true); $("editBox").classList.add("on");
}
$("eTemplate").onchange = () => fillLook($("eTemplate").value, "", null);
$("eCancel").onclick = () => $("editBox").classList.remove("on");
$("eSave").onclick = async () => {
  const m = $("eMsg"), v = (i) => $(i).value.trim(), old = POSTS[editId];
  const platforms = {};
  PLATS.forEach((k) => { if ($("ep_" + k).checked && v("et_" + k)) platforms[k] = v("et_" + k); });
  const tpl = $("eTemplate").value, eSlides = tpl === "carousel" ? parseSlides($("eSlides").value) : tpl === "reel" ? parseScenes($("eSlides").value) : [], points = v("ePoints").split("\n").map((x) => x.trim()).filter(Boolean);
  const multi = tpl === "carousel" || tpl === "reel", err = (tpl === "carousel" && slidesError(eSlides)) ? slidesError(eSlides) : (tpl === "reel" && scenesError(eSlides)) ? scenesError(eSlides) : (!multi && !v("eTitle")) ? "العنوان مطلوب." : !Object.keys(platforms).length ? "اختر منصة واحدة على الأقل بنص غير فارغ." :
    !v("eWhen") ? "اختر الموعد." : (tpl === "infographic" && (points.length < 2 || points.length > 6)) ? "الإنفوجرافك يحتاج من 2 إلى 6 نقاط." :
    (platforms.threads && platforms.threads.length > 500) ? "نص ثريدز أطول من 500 حرف." :
    (platforms.instagram && platforms.instagram.length > 2200) ? "نص إنستغرام أطول من 2200 حرف." :
    (platforms.linkedin && platforms.linkedin.length > 3000) ? "نص لينكدإن أطول من 3000 حرف." :
    ($("eTopic") && !v("eTopic")) ? "اختر الموضوع." : "";
  if (err) { say(m, err, false); return; }
  const oi = old.image || {};
  const img = { style: $("eStyle").value || undefined, hue: eHue != null && (tpl === "infographic" || tpl === "reel" || tpl === "carousel") ? eHue : undefined, title: multi ? eSlides[0].title : v("eTitle"), body: multi ? "" : v("eBody"), seed: oi.seed != null ? oi.seed : 1 };
  if (tpl === "reel") eSlides.forEach((sc, i) => { const o = (oi.scenes || [])[i] || {};
    if (o.video_url && (o.photo_query || "") === (sc.photo_query || "")) { sc.video_url = o.video_url; if (o.thumb) sc.thumb = o.thumb; } });
  if (tpl === "carousel") img.slides = eSlides; else if (tpl === "reel") { img.scenes = eSlides; if (v("eQuery")) img.photo_query = v("eQuery"); } else if (tpl === "infographic") img.points = points; else { img.photo_query = v("eQuery"); if (v("eVP")) img.visual_prompt = v("eVP"); }
  let targets;
  try { targets = readTargets("eAcc", Object.keys(platforms)); } catch (e4) { say(m, e4.message, false); return; }
  const nu = { id: editId, approved: old.approved, targets, publish_at: v("eWhen").replace("T", " "), template: tpl,
    topic: $("eTopic") ? v("eTopic") : old.topic, image: img, platforms };
  const imageChanged = tpl !== old.template || img.photo_query !== oi.photo_query || img.visual_prompt !== oi.visual_prompt;
  try {
    say(m, "جارٍ الحفظ…", true);
    await edit((x) => replacePost(x, editId, Object.assign({}, nu, { approved: liveApproved(x, editId) })), "queue: edit " + editId, QFILE);
    if (imageChanged) await deleteBg(editId);
    if (tpl === "reel" || tpl === "carousel") await deleteChangedPhotos(editId, oi.scenes || oi.slides, img.scenes || img.slides, oi.photo_query || "", img.photo_query || "");
    POSTS[editId] = Object.assign({}, POSTS[editId], nu, { approved: POSTS[editId].approved, group: POSTS[editId].group });
    const card = document.querySelector('.post [data-id="' + editId + '"]');
    if (card) { const post = card.closest(".post"); const t = post.querySelector(".title"), ln = post.querySelector(".line");
      if (t) t.textContent = img.title; if (ln) ln.textContent = "✎ حُفظ التعديل: الموعد " + nu.publish_at + " (تتحدّث بقية التفاصيل والصورة بعد دقائق)"; }
    say(m, "تم الحفظ في المستودع ✅ تتحدّث بطاقة اللوحة (وصورتها إن تغيّرت) خلال دقائق.", true);
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
    html += '<div class="cday' + (key === todayKey ? " today" : "") + '" data-day="' + key + '"><div class="cdh">' + DAYS_AR[d.getDay()] + " " + d.getDate() + "</div>" +
      (list.length ? list.map((p) => '<button class="cchip g-' + p.group + '" data-cal="' + p.id + '"' + (p.group === "draft" || p.group === "upcoming" ? ' draggable="true"' : "") + '><b dir="ltr">' + p.publish_at.slice(11) + "</b> " +
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


// ---------- إعادة نشر منشور (نسخة جديدة بنفس المحتوى والصورة) ----------
let repId = null;
function nowLocal() { const d = new Date(), p2 = (n) => String(n).padStart(2, "0"); return ymd(d) + " " + p2(d.getHours()) + ":" + p2(d.getMinutes()); }
function openRepub(id) {
  const p = POSTS[id]; if (!p) return;
  repId = id; $("rTitle").textContent = (p.image && p.image.title) || id;
  PLATS.forEach((k) => { $("rp_" + k).checked = !!(p.platforms && p.platforms[k]); $("rp_" + k).disabled = !(p.platforms && p.platforms[k]); });
  const d = new Date(Date.now() + 3600e3), p2 = (n) => String(n).padStart(2, "0");
  $("rWhen").value = ymd(d) + "T" + p2(d.getHours()) + ":" + p2(d.getMinutes());
  accPicker("rAcc", p.targets || null);
  document.querySelector('input[name=rMode][value=now]').checked = true;
  say($("rMsg"), "", true); $("repBox").classList.add("on");
}
$("rCancel").onclick = () => $("repBox").classList.remove("on");
$("rGo").onclick = async () => {
  const m = $("rMsg"), src = POSTS[repId], mode = document.querySelector("input[name=rMode]:checked").value;
  const plats = PLATS.filter((k) => $("rp_" + k).checked && src.platforms[k]);
  if (!plats.length) { say(m, "اختر منصة واحدة على الأقل.", false); return; }
  if (mode === "later" && !$("rWhen").value) { say(m, "اختر الموعد.", false); return; }
  const when = mode === "later" ? $("rWhen").value.replace("T", " ") : nowLocal();
  const id = repId.replace(/-r[a-z0-9]{4}$/, "") + "-r" + Date.now().toString(36).slice(-4);
  const im = Object.assign({}, src.image);
  if (!["carousel", "infographic"].includes(src.template)) im.bg_from = (src.image && src.image.bg_from) || repId;
  let targets;
  try { targets = readTargets("rAcc", plats); } catch (e5) { say(m, e5.message, false); return; }
  const copy = { id, approved: mode !== "draft", publish_at: when, template: src.template, topic: src.topic, image: im, targets,
    platforms: Object.fromEntries(plats.map((k) => [k, src.platforms[k]])) };
  try {
    say(m, "جارٍ الحفظ…", true);
    await edit((x) => (x.endsWith("\n") ? x : x + "\n") + serializePost(copy), "queue: republish " + repId + " as " + id, QFILE);
    say(m, mode === "draft" ? "حُفظت نسخة مسودة ✅ تظهر في «بانتظار موافقتك» خلال دقائق."
      : mode === "now" ? "بدأ النشر ✅ تظهر النتيجة في اللوحة بعد دقائق." : "جُدولت ✅ ستُنشر في الموعد المحدد.", true);
    setTimeout(() => $("repBox").classList.remove("on"), 1800);
  } catch (e) { say(m, e.message, false); }
};
document.addEventListener("click", (e) => { const b = e.target.closest('[data-act="repub"]'); if (b) openRepub(b.dataset.id); });

// ---------- موافقة بالجملة على المسودات الظاهرة ----------
$("bulkApprove").onclick = async () => {
  const ids = [...document.querySelectorAll('.post[data-s="draft"]')].filter((p) => !p.hidden)
    .map((p) => (p.querySelector('[data-act="approve"]') || {}).dataset).filter(Boolean).map((d) => d.id);
  const m = $("bulkMsg");
  if (!ids.length) { say(m, "لا مسودات ظاهرة.", false); return; }
  if (!confirm("سأوافق على " + ids.length + " منشور وتُنشر في مواعيدها. متابعة؟")) return;
  try {
    say(m, "جارٍ الحفظ…", true);
    await edit((x) => ids.reduce((t, id) => setApproved(t, id, "true"), x), "queue: approve " + ids.length + " drafts", QFILE);
    say(m, "تمت الموافقة على " + ids.length + " منشور ✅ تظهر في «سيُنشر» بعد دقائق.", true);
    ids.forEach((id) => { const a = document.querySelector('[data-act="approve"][data-id="' + id + '"]'); if (a) a.parentElement.querySelectorAll("button").forEach((x) => (x.disabled = true)); });
    $("bulkApprove").hidden = true;
  } catch (e) { say(m, e.message, false); }
};

// ---------- الأداء: أرقام على البطاقات + لوحة تجميع ----------
const INS = JSON.parse(document.getElementById("insdata").textContent || "{}");
const PLAT_NAME = { facebook: "فيسبوك", instagram: "إنستغرام", threads: "ثريدز", linkedin: "لينكدإن", telegram: "تيليجرام" };
const score = (m) => (m.likes || 0) + 2 * (m.comments || 0) + 3 * (m.shares || 0) + 2 * (m.saved || 0);
function postScore(id) {
  const per = INS[id] || {}; let s = 0, any = false;
  Object.values(per).forEach((m) => { if (m && !m.error) { any = true; s += score(m); } });
  return any ? s : null;
}
function metricsLine(id) {
  const per = INS[id]; if (!per) return "";
  return Object.entries(per).map(([k, m]) => {
    const nm = PLAT_NAME[k.split(":")[0]] || k;
    if (!m || m.error) return nm + ": —";
    const bits = [];
    if (m.views != null) bits.push("👁 " + m.views); if (m.reach != null) bits.push("👁 " + m.reach);
    bits.push("❤ " + (m.likes || 0), "💬 " + (m.comments || 0));
    if (m.shares) bits.push("↗ " + m.shares); if (m.saved) bits.push("🔖 " + m.saved);
    return nm + ": " + bits.join(" ");
  }).join(" · ");
}
document.querySelectorAll(".post").forEach((p) => {
  const b = p.querySelector("[data-id]"); if (!b) return;
  const t = metricsLine(b.dataset.id); if (!t) return;
  const ln = p.querySelector(".line"); if (!ln) return;
  const d = document.createElement("div"); d.className = "hint"; d.textContent = "📊 " + t; ln.after(d);
});
function renderStats() {
  const rows = Object.values(POSTS).map((p) => ({ p, s: postScore(p.id) })).filter((r) => r.s != null);
  const body = $("statsBody"), note = $("statsNote");
  if (!rows.length) {
    note.textContent = "لا أرقام بعد. تُسحب إحصاءات المنشورات مع الفحص اليومي (الساعة 8 صباحاً تقريباً)، وقد ترفض المنصة بعضها إن كانت صلاحية القراءة غير ممنوحة للتوكن.";
    body.innerHTML = ""; return;
  }
  const denied = new Set(); Object.values(INS).forEach((per) => Object.entries(per).forEach(([k, m]) => { if (m && m.error && /permission|صلاحية|Page Public/i.test(m.error)) denied.add(PLAT_NAME[k.split(":")[0]] || k); }));
  const warn = denied.size ? " ⚠️ لا تتوفر أرقام " + [...denied].join(" و") + ": توكنها ينقصه إذن قراءة الإحصاءات (يلزم تجديد التوكن بإذن إضافي)." : "";
  note.textContent = warn + " التقييم = إعجابات + ٢×تعليقات + ٣×مشاركات + ٢×حفظ. المتوسط لكل منشور، وكلما زاد العدد كان الرقم أدق.";
  const topicName = (id) => { const o = [...$("qTopic").options].find((x) => x.value === id); return o ? o.textContent : (id || "—"); };
  const groupBy = (keyFn) => { const g = {}; rows.forEach((r) => { const k = keyFn(r.p); if (k == null) return; (g[k] = g[k] || []).push(r.s); }); return Object.entries(g).map(([k, v]) => [k, v.reduce((a, b) => a + b, 0) / v.length, v.length]).sort((a, b) => b[1] - a[1]); };
  const TPL = { infographic: "إنفوجرافك", carousel: "كاروسيل", reel: "ريل", split: "صورة", photo: "صورة", tip: "نصيحة", quote: "اقتباس" };
  const table = (title, data, label) => "<h3>" + title + "</h3><table class=\"st\">" + data.map(([k, avg, n]) => "<tr><td>" + label(k) + "</td><td>" + avg.toFixed(1) + "</td><td>" + n + " منشور</td></tr>").join("") + "</table>";
  const top = rows.slice().sort((a, b) => b.s - a.s).slice(0, 5);
  body.innerHTML =
    "<h3>الأفضل أداءً</h3><table class=\"st\">" + top.map((r) => "<tr><td>" + (r.p.image && r.p.image.title || r.p.id) + "</td><td>" + r.s + "</td></tr>").join("") + "</table>" +
    table("حسب القالب", groupBy((p) => p.template), (k) => TPL[k] || k) +
    table("حسب النمط", groupBy((p) => (p.image && p.image.style) || null), (k) => k) +
    table("حسب وقت النشر", groupBy((p) => (p.publish_at || "").slice(11, 13) + ":00"), (k) => k) +
    table("حسب الموضوع", groupBy((p) => p.topic || null), topicName);
}
renderStats();

// ---------- الشريط العلوي والجانبي (تصميم v4) ----------
function toast(msg, ok) {
  let t = document.getElementById("toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
  t.textContent = msg; t.className = "toast show " + (ok === false ? "no" : "ok");
  clearTimeout(t._h); t._h = setTimeout(() => (t.className = "toast"), 5000);
}
async function dispatchWf(file) { await gh("actions/workflows/" + file + "/dispatches", { method: "POST", body: JSON.stringify({ ref: "main" }) }); }
$("tbRefresh").onclick = () => location.reload();
$("tbAdd").onclick = () => show("addpost");
$("tbPublish").onclick = async () => {
  if (!confirm("سأشغّل النشر الآن لكل منشور معتمد حان موعده. متابعة؟")) return;
  try { await dispatchWf("publish.yml"); toast("بدأ تشغيل النشر ✓ تظهر النتيجة بعد دقائق.", true); } catch (e) { toast(e.message, false); }
};
if ($("btnHealth")) $("btnHealth").onclick = async () => { try { await dispatchWf("health.yml"); toast("بدأ فحص الصحة ✓ تتحدّث البطاقات بعد دقائق.", true); } catch (e) { toast(e.message, false); } };
if ($("btnDaily")) $("btnDaily").onclick = async () => { if (!confirm("أولّد مسودات اليوم الآن؟ (تستغرق دقائق)")) return; try { await dispatchWf("daily.yml"); toast("بدأ توليد المسودات ✓ تصلك في الطابور بعد دقائق.", true); } catch (e) { toast(e.message, false); } };
(function sideAccounts() {
  const col = { facebook: ["#1877F2", "f", "#fff"], instagram: ["#E1306C", "ig", "#fff"], threads: ["#ffffff", "@", "#000"], linkedin: ["#0A66C2", "in", "#fff"], telegram: ["#229ED9", "tg", "#fff"] };
  const box = $("sideAcc"); if (!box) return;
  [...new Set(ACC.map((a) => a.platform))].forEach((p) => { const c = col[p]; if (!c) return; const i = document.createElement("i"); i.textContent = c[1]; i.style.background = c[0]; i.style.color = c[2]; i.title = PLAT_NAME[p] || p; box.appendChild(i); });
})();

// ---------- مؤشرات وأعمدة إضافية في «الأداء» ----------
(function statsExtra() {
  const body = $("statsBody"); if (!body || !body.innerHTML.trim()) return;
  const sum = { likes: 0, comments: 0, shares: 0, reach: 0 };
  Object.values(INS).forEach((per) => Object.values(per).forEach((m) => { if (!m || m.error) return; sum.likes += m.likes || 0; sum.comments += m.comments || 0; sum.shares += m.shares || 0; sum.reach += (m.reach || m.views || 0); }));
  const pub = Object.values(POSTS).filter((p) => p.group === "published").length;
  const f = (n) => n >= 1000 ? (n / 1000).toFixed(1) + "K" : String(n);
  let html = '<div class="skpis"><div class="sk"><span>منشورات منشورة</span><b>' + pub + '</b></div><div class="sk"><span>إعجابات</span><b>' + f(sum.likes) + '</b></div><div class="sk"><span>تعليقات</span><b>' + f(sum.comments) + '</b></div><div class="sk"><span>وصول / مشاهدات</span><b>' + f(sum.reach) + "</b></div></div>";
  const byHour = {}; Object.values(POSTS).forEach((p) => { const sc = postScore(p.id); if (sc == null) return; const h = (p.publish_at || "").slice(11, 13) + ":00"; (byHour[h] = byHour[h] || []).push(sc); });
  const hrs = Object.entries(byHour).map(([h, v]) => [h, v.reduce((a, b) => a + b, 0) / v.length]).sort();
  if (hrs.length) { const mx = Math.max(...hrs.map((x) => x[1])) || 1; html += '<h3>متوسط التفاعل بحسب ساعة النشر</h3><div class="bars2">' + hrs.map(([h, v]) => '<div class="bar2"><span dir="ltr">' + h + '</span><i><b style="width:' + Math.round(v / mx * 100) + '%"></b></i><span>' + v.toFixed(1) + "</span></div>").join("") + "</div>"; }
  body.insertAdjacentHTML("afterbegin", html);
})();

// ---------- نسخ السكربتات والروابط ----------
document.addEventListener("click", async (e) => {
  const b = e.target.closest(".cpy"); if (!b) return;
  try { await navigator.clipboard.writeText(b.dataset.copy || ""); toast("نُسخ ✓", true); } catch (x) { toast("تعذّر النسخ، انسخ يدوياً.", false); }
});
