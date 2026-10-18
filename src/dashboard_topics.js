// ---- إدارة المواضيع عبر GitHub API (يُدرَج داخل اللوحة) ----
const REPO = "__REPO__", FILE = "content/topics.yaml";
const getTok = () => { try { return localStorage.getItem("gh_tok") || sessionStorage.getItem("gh_tok") || ""; } catch (e) { return ""; } };
const setTok = (v, keep) => { try { sessionStorage.setItem("gh_tok", v); keep ? localStorage.setItem("gh_tok", v) : localStorage.removeItem("gh_tok"); } catch (e) {} };
const b64d = (b) => new TextDecoder().decode(Uint8Array.from(atob(b.replace(/\n/g, "")), (c) => c.charCodeAt(0)));
const b64e = (s) => { let bin = ""; new TextEncoder().encode(s).forEach((x) => (bin += String.fromCharCode(x))); return btoa(bin); };
const q = (s) => JSON.stringify(s);

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

async function gh(path, opt) {
  const r = await fetch("https://api.github.com/repos/" + REPO + "/" + path, Object.assign({}, opt, {
    headers: { Authorization: "Bearer " + getTok(), Accept: "application/vnd.github+json", "Content-Type": "application/json" } }));
  if ([401, 403, 404].includes(r.status)) throw new Error("المفتاح غير صالح أو صلاحيته ناقصة (يلزم Contents: Read and write على هذا المستودع).");
  if ([409, 422].includes(r.status)) throw new Error("تعارض أثناء الحفظ، أعد المحاولة.");
  if (!r.ok) throw new Error("تعذّر الاتصال بـ GitHub (" + r.status + ").");
  return r.json();
}

async function edit(fn, msg) {
  if (!getTok()) throw new Error("ألصق مفتاح GitHub أولاً في قسم «ربط GitHub» أدناه.");
  const f = await gh("contents/" + FILE);
  const text = fn(b64d(f.content));
  await gh("contents/" + FILE, { method: "PUT", body: JSON.stringify({ message: msg, content: b64e(text), sha: f.sha }) });
}

const $ = (id) => document.getElementById(id);
const say = (el, t, ok) => { el.textContent = t; el.className = "msg " + (ok ? "ok" : "no"); };

$("tokSave").onclick = () => {
  const v = $("tok").value.trim(); if (!v) return;
  setTok(v, $("remember").checked); $("tok").value = "";
  say($("tokMsg"), "تم حفظ المفتاح في هذا المتصفح.", true);
};

$("fAdd").onclick = async () => {
  const m = $("fMsg"), v = (i) => $(i).value.trim();
  if (!v("fName")) { say(m, "اكتب اسم الموضوع.", false); return; }
  const tags = v("fTags").split(/[\s,،]+/).filter(Boolean).map((x) => (x.startsWith("#") ? x : "#" + x));
  const t = { id: "t" + Date.now().toString(36), name: v("fName"), description: v("fDesc"), audience: v("fAud"), tone: v("fTone"), tags };
  try {
    say(m, "جارٍ الحفظ…", true);
    await edit((x) => addBlock(x, t), "topics: add " + t.id);
    say(m, "تمت الإضافة ✅ ستظهر في القائمة بعد دقيقة تقريباً (تُحدَّث اللوحة تلقائياً).", true);
    ["fName", "fDesc", "fAud", "fTone", "fTags"].forEach((i) => ($(i).value = ""));
  } catch (e) { say(m, e.message, false); }
};

$("topicList").onclick = async (e) => {
  const id = e.target.dataset && e.target.dataset.del;
  if (!id || !confirm("حذف هذا الموضوع؟")) return;
  try {
    await edit((x) => removeBlock(x, id), "topics: remove " + id);
    e.target.closest(".tp").remove(); say($("fMsg"), "تم الحذف ✅", true);
  } catch (err) { say($("fMsg"), err.message, false); }
};
