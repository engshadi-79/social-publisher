// ---- إدارة المواضيع والمنشورات عبر GitHub API (يُدرَج داخل اللوحة) ----
const REPO = "__REPO__", TFILE = "content/topics.yaml", QFILE = "content/queue.yaml";
const PROXY = !!window.GH_PROXY;     // على Vercel: الطلبات تمرّ عبر /api/gh والمفتاح على الخادم
const hasAuth = () => PROXY || !!getTok();
const getTok = () => { try { return localStorage.getItem("gh_tok") || sessionStorage.getItem("gh_tok") || ""; } catch (e) { return ""; } };
const setTok = (v, keep) => { try { sessionStorage.setItem("gh_tok", v); keep ? localStorage.setItem("gh_tok", v) : localStorage.removeItem("gh_tok"); } catch (e) {} };
const b64d = (b) => new TextDecoder().decode(Uint8Array.from(atob(b.replace(/\n/g, "")), (c) => c.charCodeAt(0)));
const b64e = (s) => { let bin = ""; new TextEncoder().encode(s).forEach((x) => (bin += String.fromCharCode(x))); return btoa(bin); };
const q = (s) => JSON.stringify(s);


// ---------- شرائح الكاروسيل: تحويل النص <-> بنية ----------
function parseSlides(text) {
  return text.split(/^\s*---\s*$/m).map((blk) => {
    const sl = { kicker: "", title: "", body: "", points: [] }, body = [];
    blk.split("\n").map((l) => l.trim()).filter(Boolean).forEach((l) => {
      if (l.startsWith("# ")) sl.title = l.slice(2).trim();
      else if (l.startsWith("@ ")) sl.kicker = l.slice(2).trim();
      else if (l.startsWith("- ")) sl.points.push(l.slice(2).trim());
      else body.push(l);
    });
    sl.body = body.join(" "); return sl;
  }).filter((s) => s.title || s.body || s.points.length);
}
function slidesToText(slides) {
  return (slides || []).map((s) => [s.title ? "# " + s.title : "", s.kicker ? "@ " + s.kicker : "", s.body || "",
    ...(s.points || []).map((p) => "- " + p)].filter(Boolean).join("\n")).join("\n---\n");
}
function slidesYaml(slides) {
  return "    slides:\n" + slides.map((s) => "      - kicker: " + q(s.kicker || "") + "\n        title: " + q(s.title) + "\n        body: " + q(s.body || "") +
    (s.points && s.points.length ? "\n        points:\n" + s.points.map((x) => "          - " + q(x)).join("\n") : "")).join("\n") + "\n";
}
// مشاهد الريل: نفس صيغة الشرائح مع سطرين إضافيين: «~ 3.5» للثواني و«? كلمات» للصورة
function parseScenes(text) {
  return text.split(/^\s*---\s*$/m).map((blk) => {
    const sc = { kicker: "", title: "", body: "", seconds: 3.4, photo_query: "" }, body = [];
    blk.split("\n").map((l) => l.trim()).filter(Boolean).forEach((l) => {
      if (l.startsWith("# ")) sc.title = l.slice(2).trim();
      else if (l.startsWith("@ ")) sc.kicker = l.slice(2).trim();
      else if (l.startsWith("~ ")) sc.seconds = parseFloat(l.slice(2)) || 3.4;
      else if (l.startsWith("? ")) sc.photo_query = l.slice(2).trim();
      else body.push(l);
    });
    sc.body = body.join(" "); return sc;
  }).filter((s) => s.title || s.body);
}
function scenesToText(scenes) {
  return (scenes || []).map((s) => [s.title ? "# " + s.title : "", s.kicker ? "@ " + s.kicker : "", s.body || "",
    s.seconds ? "~ " + s.seconds : "", s.photo_query ? "? " + s.photo_query : ""].filter(Boolean).join("\n")).join("\n---\n");
}
function scenesYaml(scenes) {
  return "    scenes:\n" + scenes.map((s) => "      - kicker: " + q(s.kicker || "") + "\n        title: " + q(s.title) + "\n        body: " + q(s.body || "") +
    "\n        seconds: " + (Math.min(8, Math.max(1.5, s.seconds || 3.4))) + (s.photo_query ? "\n        photo_query: " + q(s.photo_query) : "")).join("\n") + "\n";
}
const scenesError = (sc) => (sc.length < 3 || sc.length > 8) ? "الريل يحتاج من 3 إلى 8 مشاهد." : (sc.some((s) => !s.title) ? "لكل مشهد عنوان («# العنوان»)." : (sc.some((s) => s.title.length > 70) ? "عنوان المشهد أطول من 70 حرفاً." : (sc.some((s) => s.body.length > 150) ? "نص المشهد أطول من 150 حرفاً." : "")));
const slidesError = (sl) => (sl.length < 3 || sl.length > 10) ? "الكاروسيل يحتاج من 3 إلى 10 شرائح." : (sl.some((s) => !s.title) ? "لكل شريحة عنوان («# العنوان»)." : "");


// ---------- اختيار الحسابات المستهدفة ----------
const ACC = JSON.parse(document.getElementById("accdata").textContent);
const PLAT_AR = { facebook: "فيسبوك", instagram: "إنستغرام", threads: "ثريدز", linkedin: "لينكدإن", telegram: "تيليجرام" };
function accPicker(boxId, selected) {
  const box = document.getElementById(boxId); if (!box) return; box.innerHTML = "";
  Object.keys(PLAT_AR).forEach((pl) => {
    const list = ACC.filter((a) => a.platform === pl); if (list.length < 2) return;
    const chosen = (selected && selected[pl]) || list.filter((a) => a.default).map((a) => a.id);
    box.insertAdjacentHTML("beforeend", '<div class="accrow"><b>' + PLAT_AR[pl] + ' — على أي حساب؟</b><br>' + list.map((a) =>
      '<label><input type="checkbox" data-pl="' + pl + '" data-acc="' + a.id + '"' + (chosen.includes(a.id) ? " checked" : "") + "> " +
      a.label.replace(/</g, "&lt;") + "</label>").join("") + "</div>");
  });
}
function readTargets(boxId, activePlatforms) {
  const out = {}, box = document.getElementById(boxId);
  for (const pl of Object.keys(PLAT_AR)) {
    const list = ACC.filter((a) => a.platform === pl); if (list.length < 2 || !box) continue;
    const picked = [...box.querySelectorAll('input[data-pl="' + pl + '"]:checked')].map((i) => i.dataset.acc);
    if (activePlatforms.includes(pl) && !picked.length) throw new Error("اختر حساباً واحداً على الأقل لمنصة " + PLAT_AR[pl] + ".");
    const dfl = list.filter((a) => a.default).map((a) => a.id);
    if (picked.slice().sort().join() !== dfl.slice().sort().join()) out[pl] = picked;
  }
  return out;
}
const targetsYaml = (t) => t && Object.keys(t).length ? "  targets:\n" + Object.entries(t).map(([pl, ids]) => "    " + pl + ":\n" + ids.map((i) => "      - " + q(i)).join("\n")).join("\n") + "\n" : "";

// ---------- المواضيع ----------
function addBlock(text, t) {
  const tags = (t.tags || []).map(q).join(", ");
  const block = "  - id: " + q(t.id) + "\n    name: " + q(t.name) + "\n    description: " + q(t.description) +
    "\n    audience: " + q(t.audience) + "\n    tone: " + q(t.tone) + "\n    hashtags_fixed: [" + tags + "]\n";
  let x = text.replace(/^topics:[ \t]*\[\][ \t]*$/m, "topics:");
  if (!x.endsWith("\n")) x += "\n";
  return x + block;
}

function removeBlock(text, id) {
  const out = []; let skip = false;
  for (const l of text.split("\n")) {
    if (/^  - id:/.test(l)) skip = l.replace(/^  - id:\s*"?/, "").replace(/"?\s*$/, "") === id;
    else if (skip && /^\S/.test(l)) skip = false;
    if (!skip) out.push(l);
  }
  let x = out.join("\n");
  if (!/^  - id:/m.test(x)) x = x.replace(/^topics:[ \t]*$/m, "topics: []");
  return x;
}

// ---------- المنشورات (queue.yaml) ----------
const idOf = (l) => l.replace(/^- id:\s*"?/, "").replace(/"?\s*$/, "");
function postRange(lines, id) {
  const s = lines.findIndex((l) => /^- id:/.test(l) && idOf(l) === id);
  if (s < 0) throw new Error("لم أجد المنشور في الطابور (ربما حُذف).");
  let e = lines.length;
  for (let i = s + 1; i < lines.length; i++) if (/^- id:/.test(lines[i])) { e = i; break; }
  return [s, e];
}
function setApproved(text, id, val) {
  const lines = text.split("\n"), [s, e] = postRange(lines, id);
  for (let i = s; i < e; i++) if (/^  approved:/.test(lines[i])) { lines[i] = "  approved: " + val; return lines.join("\n"); }
  throw new Error("بنية المنشور غير متوقعة.");
}
function removePost(text, id) {
  const lines = text.split("\n"), [s, e] = postRange(lines, id);
  lines.splice(s, e - s);
  return lines.join("\n");
}
function addPost(text, p) {
  let b = "- id: " + q(p.id) + "\n  approved: false\n  publish_at: " + q(p.when) + "\n  template: " + p.template + "\n";
  if (p.topic) b += "  topic: " + q(p.topic) + "\n";
  b += "  image:\n    title: " + q(p.title) + "\n    body: " + q(p.body) + "\n";
  if (p.points && p.points.length) b += "    points:\n" + p.points.map((x) => "      - " + q(x)).join("\n") + "\n";
  if (p.slides && p.slides.length) b += p.template === "reel" ? scenesYaml(p.slides) : slidesYaml(p.slides);
  if (p.query) b += "    photo_query: " + q(p.query) + "\n";
  if (p.vp) b += "    visual_prompt: " + q(p.vp) + "\n";
  b += "    seed: " + p.seed + "\n  platforms:\n";
  for (const k of p.platforms) b += "    " + k + ": " + q(p.text) + "\n";
  b += targetsYaml(p.targets);
  let x = text.replace(/^\[\][ \t]*$/m, "");
  if (x.length && !x.endsWith("\n")) x += "\n";
  return x + b;
}

// ---------- GitHub ----------
async function gh(path, opt) {
  const r = PROXY
    ? await fetch("/api/gh?p=" + encodeURIComponent(path), Object.assign({}, opt, { headers: { "Content-Type": "application/json" }, credentials: "same-origin" }))
    : await fetch("https://api.github.com/repos/" + REPO + "/" + path, Object.assign({}, opt, {
      headers: { Authorization: "Bearer " + getTok(), Accept: "application/vnd.github+json", "Content-Type": "application/json" } }));
  if (PROXY && r.status === 401) { location.href = "/login"; throw new Error("انتهت الجلسة، سجّل الدخول من جديد."); }
  if (PROXY && r.status === 501) throw new Error("لم يُضبط مفتاح GitHub على الخادم بعد (GITHUB_PAT على Vercel).");
  if ([401, 403, 404].includes(r.status)) throw new Error("المفتاح غير صالح أو صلاحيته ناقصة (يلزم Contents: Read and write على هذا المستودع).");
  if ([409, 422].includes(r.status)) throw new Error("تعارض أثناء الحفظ، أعد المحاولة.");
  if (!r.ok) throw new Error("تعذّر الاتصال بـ GitHub (" + r.status + ").");
  if (r.status === 204) return {};
  return r.json();
}
async function edit(fn, msg, file) {
  file = file || TFILE;
  if (!hasAuth()) throw new Error("ألصق مفتاح GitHub أولاً في قسم «ربط GitHub» أسفل الصفحة.");
  const f = await gh("contents/" + file);
  const text = fn(b64d(f.content));
  await gh("contents/" + file, { method: "PUT", body: JSON.stringify({ message: msg, content: b64e(text), sha: f.sha }) });
}

const $ = (id) => document.getElementById(id);
const say = (el, t, ok) => { el.textContent = t; el.className = "msg " + (ok ? "ok" : "no"); };

$("tokSave").onclick = () => {
  const v = $("tok").value.trim(); if (!v) return;
  setTok(v, $("remember").checked); $("tok").value = "";
  say($("tokMsg"), "تم حفظ المفتاح في هذا المتصفح.", true);
};

// ---- مواضيع ----
$("fAdd").onclick = async () => {
  const m = $("fMsg"), v = (i) => $(i).value.trim();
  if (!v("fName")) { say(m, "اكتب اسم الموضوع.", false); return; }
  const tags = v("fTags").split(/[\s,،]+/).filter(Boolean).map((x) => (x.startsWith("#") ? x : "#" + x));
  const t = { id: "t" + Date.now().toString(36), name: v("fName"), description: v("fDesc"), audience: v("fAud"), tone: v("fTone"), tags };
  try {
    say(m, "جارٍ الحفظ…", true);
    await edit((x) => addBlock(x, t), "topics: add " + t.id, TFILE);
    say(m, "تمت الإضافة ✅ ستظهر في القائمة بعد دقيقة تقريباً (تُحدَّث اللوحة تلقائياً).", true);
    ["fName", "fDesc", "fAud", "fTone", "fTags"].forEach((i) => ($(i).value = ""));
  } catch (e) { say(m, e.message, false); }
};
$("topicList").onclick = async (e) => {
  const id = e.target.dataset && e.target.dataset.del;
  if (!id || !confirm("حذف هذا الموضوع؟")) return;
  try {
    await edit((x) => removeBlock(x, id), "topics: remove " + id, TFILE);
    e.target.closest(".tp").remove(); say($("fMsg"), "تم الحذف ✅", true);
  } catch (err) { say($("fMsg"), err.message, false); }
};

// ---- منشورات: إضافة ----
accPicker("pAcc", null);
const updCount = () => { const n = $("pText").value.length; $("pCount").textContent = n + " حرفاً" + (n > 500 && $("pl_threads").checked ? " — ثريدز حدّه 500!" : ""); };
$("pText").oninput = updCount; $("pl_threads").onchange = updCount;
$("pAdd").onclick = async () => {
  const m = $("pMsg"), v = (i) => $(i).value.trim();
  const plats = ["facebook", "instagram", "threads", "linkedin", "telegram"].filter((k) => $("pl_" + k).checked);
  const when = v("pWhen").replace("T", " ");
  const tplv = $("pTemplate").value, isCar = tplv === "carousel" || tplv === "reel", slides = tplv === "reel" ? parseScenes($("pSlides").value) : isCar ? parseSlides($("pSlides").value) : [];
  const mErr = tplv === "reel" ? scenesError(slides) : isCar ? slidesError(slides) : "";
  const err = mErr ? mErr : (!isCar && !v("pTitle")) ? "اكتب عنوان الصورة." : !v("pText") ? "اكتب نص المنشور." : !plats.length ? "اختر منصة واحدة على الأقل." :
    !when ? "اختر موعد النشر." :
    (isCar ? false : $("pTemplate").value === "infographic" && (v("pPoints").split("\n").filter((x) => x.trim()).length < 2)) ? "الإنفوجرافك يحتاج نقطتين على الأقل (كل نقطة في سطر)." :
    ($("pTopic") && !v("pTopic")) ? "اختر الموضوع." :
    (plats.includes("threads") && v("pText").length > 500) ? "نص ثريدز يجب ألا يتجاوز 500 حرف." :
    (plats.includes("linkedin") && v("pText").length > 3000) ? "نص لينكدإن يجب ألا يتجاوز 3000 حرف." :
    (plats.includes("instagram") && v("pText").length > 2200) ? "نص إنستغرام يجب ألا يتجاوز 2200 حرف." : "";
  if (err) { say(m, err, false); return; }
  let targets;
  try { targets = readTargets("pAcc", plats); } catch (e3) { say(m, e3.message, false); return; }
  const d = when.slice(0, 10);
  const p = { id: d + "-w" + Date.now().toString(36).slice(-4), when, template: $("pTemplate").value, topic: $("pTopic") ? v("pTopic") : "",
    title: isCar ? slides[0].title : v("pTitle"), body: isCar ? "" : v("pBody"), slides, query: v("pQuery"), vp: v("pVP"), points: v("pPoints").split("\n").map((x) => x.trim()).filter(Boolean), seed: 1 + Math.floor(Math.random() * 90), platforms: plats, targets, text: v("pText") };
  try {
    say(m, "جارٍ الحفظ…", true);
    await edit((x) => addPost(x, p), "queue: add " + p.id, QFILE);
    say(m, "أُضيف كمسودة ✅ خلال دقيقتين تظهر بصورتها في «بانتظار موافقتك» لتراجعها ثم توافق.", true);
    ["pTitle", "pBody", "pQuery", "pVP", "pPoints", "pSlides", "pText"].forEach((i) => ($(i).value = "")); updCount();
  } catch (e2) { say(m, e2.message, false); }
};

// ---- منشورات: موافقة / إلغاء / حذف (أزرار البطاقات) ----
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-act]"); if (!b) return;
  const id = b.dataset.id, act = b.dataset.act;
  if (!["approve", "unapprove", "del"].includes(act)) return;   // الأزرار الأخرى لها معالجات في dashboard_posts.js
  const out = b.closest(".post").querySelector(".actmsg");
  if (act === "del" && !confirm("حذف هذا المنشور من الطابور؟")) return;
  try {
    say(out, "جارٍ الحفظ…", true);
    if (act === "approve") await edit((x) => setApproved(x, id, "true"), "queue: approve " + id, QFILE);
    if (act === "unapprove") await edit((x) => setApproved(x, id, "false"), "queue: unapprove " + id, QFILE);
    if (act === "del") await edit((x) => removePost(x, id), "queue: remove " + id, QFILE);
    say(out, act === "approve" ? "تمت الموافقة ✅ سيُنشر في موعده (يفحص النظام كل 30 دقيقة)." : act === "unapprove" ? "أُلغيت الموافقة ✅" : "حُذف ✅", true);
    b.parentElement.querySelectorAll("button").forEach((x) => (x.disabled = true));
  } catch (err) { say(out, err.message, false); }
});

// ---- توليد منشورات تلقائياً: يكتب طلباً في المستودع فيشغّل سير عمل التوليد ----
async function putRequest(text, msg) {
  if (!hasAuth()) throw new Error("ألصق مفتاح GitHub أولاً في قسم «ربط GitHub» أسفل الصفحة.");
  let sha;
  try { sha = (await gh("contents/content/generate_request.yaml")).sha; } catch (e) { sha = undefined; }
  await gh("contents/content/generate_request.yaml", { method: "PUT",
    body: JSON.stringify({ message: msg, content: b64e(text), sha }) });
}
$("gGo").onclick = async () => {
  const m = $("gMsg");
  const topicId = $("gTopic") ? $("gTopic").value : "", topicText = $("gTopicText") ? $("gTopicText").value.trim() : "";
  const when = $("gWhen").value.replace("T", " ");
  if (!topicId && !topicText) { say(m, "اكتب الموضوع.", false); return; }
  if (!when) { say(m, "اختر موعد أول منشور.", false); return; }
  const id = "g" + Date.now().toString(36);
  const yml = "id: " + q(id) + "\ncount: " + parseInt($("gCount").value, 10) + "\nstyle: " + q($("gStyle").value) + "\nslides: " + parseInt($("gSlides").value, 10) + "\nstart: " + q(when) + "\n" +
    (topicId ? "topic_id: " + q(topicId) : "topic_text: " + q(topicText)) + "\n";
  try {
    say(m, "جارٍ إرسال الطلب…", true);
    await putRequest(yml, "generate: request " + id);
    say(m, "طُلب التوليد ✅ خلال دقيقتين إلى ثلاث تظهر المسودات (مع صورها) في «بانتظار موافقتك». حدّث الصفحة بعد ذلك.", true);
  } catch (e) { say(m, e.message, false); }
};
