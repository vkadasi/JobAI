// Resume Tailor front-end (vanilla JS, no build step).

const $ = (sel) => document.querySelector(sel);
const state = { settings: null, master: null, current: null, saveTimer: null };

// ---------------------------------------------------------------- utilities

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {},
    ...opts,
    body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body,
  });
  if (!res.ok) {
    let msg = `Something went wrong (${res.status}).`;
    try { msg = (await res.json()).error || msg; } catch (_) {}
    throw new Error(msg);
  }
  return res;
}
const apiJson = async (path, opts) => (await api(path, opts)).json();

function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (isError ? " error" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), isError ? 7000 : 3000);
}

function busy(msg) {
  $("#overlay-msg").textContent = msg || "Working…";
  $("#overlay").classList.toggle("hidden", !msg);
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) node.append(c instanceof Node ? c : document.createTextNode(c ?? ""));
  return node;
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) + " " +
    d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

// ---------------------------------------------------------------- tabs

function showTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + name));
  if (name === "history") loadHistory();
  window.scrollTo(0, 0);
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

// ---------------------------------------------------------------- structured resume editor

const BLANK = {
  skills: () => ({ category: "", items: [] }),
  experience: () => ({ title: "", company: "", location: "", start: "", end: "", bullets: [] }),
  projects: () => ({ name: "", link: "", bullets: [] }),
  education: () => ({ degree: "", school: "", location: "", start: "", end: "", details: "" }),
  extra_sections: () => ({ title: "", items: [] }),
};

function renderEditor(container, resume, onChange) {
  container.innerHTML = "";
  const rerender = () => { renderEditor(container, resume, onChange); onChange(); };

  const input = (label, obj, key, opts = {}) => {
    const field = opts.multiline
      ? el("textarea", { rows: opts.rows || 3 })
      : el("input", { type: "text" });
    field.value = opts.list ? (obj[key] || []).join(opts.sep) : (obj[key] || "");
    if (opts.placeholder) field.placeholder = opts.placeholder;
    field.addEventListener("input", () => {
      obj[key] = opts.list
        ? field.value.split(opts.sep === "\n" ? /\n/ : /,/).map((s) => s.trim()).filter(Boolean)
        : field.value;
      onChange();
    });
    return el("label", {}, label, field);
  };
  const bulletsField = (label, obj, key) =>
    input(label + " (one per line)", obj, key, { multiline: true, list: true, sep: "\n", rows: Math.max(3, (obj[key] || []).length + 1) });

  const listSection = (title, key, renderItem, addLabel) => {
    const fs = el("fieldset", {}, el("legend", {}, title));
    resume[key].forEach((item, i) => {
      const head = el("div", { class: "item-head" },
        el("button", { title: "Move up", onclick: () => { if (i > 0) { [resume[key][i - 1], resume[key][i]] = [resume[key][i], resume[key][i - 1]]; rerender(); } } }, "↑"),
        el("button", { title: "Move down", onclick: () => { if (i < resume[key].length - 1) { [resume[key][i + 1], resume[key][i]] = [resume[key][i], resume[key][i + 1]]; rerender(); } } }, "↓"),
        el("button", { class: "danger", title: "Remove", onclick: () => { resume[key].splice(i, 1); rerender(); } }, "Remove"),
      );
      fs.append(el("div", { class: "item" }, head, renderItem(item)));
    });
    fs.append(el("button", { class: "add", onclick: () => { resume[key].push(BLANK[key]()); rerender(); } }, "+ " + addLabel));
    return fs;
  };

  const c = resume.contact;
  container.append(
    el("fieldset", {}, el("legend", {}, "Header"),
      el("div", { class: "f2" }, input("Full name", resume, "name"), input("Headline", resume, "headline")),
      el("div", { class: "f2" }, input("Email", c, "email"), input("Phone", c, "phone")),
      el("div", { class: "f3" }, input("Location", c, "location"), input("LinkedIn", c, "linkedin"), input("Website", c, "website")),
    ),
    el("fieldset", {}, el("legend", {}, "Summary"), input("", resume, "summary", { multiline: true, rows: 4 })),
    listSection("Skills", "skills", (s) => el("div", {},
      input("Category", s, "category", { placeholder: "e.g. Product" }),
      input("Skills (comma separated)", s, "items", { list: true, sep: ", " }),
    ), "Add skill group"),
    listSection("Experience", "experience", (e) => el("div", {},
      el("div", { class: "f2" }, input("Title", e, "title"), input("Company", e, "company")),
      el("div", { class: "f3" }, input("Location", e, "location"), input("Start", e, "start"), input("End", e, "end")),
      bulletsField("Bullets", e, "bullets"),
    ), "Add role"),
    listSection("Projects", "projects", (p) => el("div", {},
      el("div", { class: "f2" }, input("Name", p, "name"), input("Link", p, "link")),
      bulletsField("Bullets", p, "bullets"),
    ), "Add project"),
    listSection("Education", "education", (ed) => el("div", {},
      el("div", { class: "f2" }, input("Degree", ed, "degree"), input("School", ed, "school")),
      el("div", { class: "f3" }, input("Location", ed, "location"), input("Start", ed, "start"), input("End", ed, "end")),
      input("Details (GPA, honours…)", ed, "details"),
    ), "Add education"),
    el("fieldset", {}, el("legend", {}, "Certifications"), bulletsField("Certifications", resume, "certifications")),
    listSection("Other sections (awards, languages, volunteering…)", "extra_sections", (s) => el("div", {},
      input("Section title", s, "title"),
      bulletsField("Items", s, "items"),
    ), "Add section"),
  );
}

// ---------------------------------------------------------------- export / preview

async function exportResume(fmt, resume, analysis, frame) {
  try {
    const res = await api(`/api/export/${fmt}`, { method: "POST", body: { resume, analysis, inline: !!frame } });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    if (frame) {
      frame.src = url + "#navpanes=0&view=FitH";
      frame.nextElementSibling.classList.add("hidden");
      return;
    }
    const cd = res.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
    const a = el("a", { href: url, download: m ? decodeURIComponent(m[1]) : `Resume.${fmt}` });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (e) {
    toast(e.message, true);
  }
}

// ---------------------------------------------------------------- settings

async function loadSettings() {
  state.settings = await apiJson("/api/settings");
  const s = state.settings;
  const sel = $("#st-provider");
  sel.innerHTML = "";
  for (const [key, p] of Object.entries(s.presets)) sel.append(el("option", { value: key }, p.label));
  sel.value = s.provider;
  $("#st-base").value = s.base_url || "";
  $("#st-model").value = s.model || "";
  $("#st-paper").value = s.paper || "A4";
  $("#st-key").value = "";
  updateSettingsHints();
  updateBanner();
}

function updateSettingsHints() {
  const s = state.settings;
  const p = s.presets[$("#st-provider").value];
  $("#st-base-wrap").classList.toggle("hidden", $("#st-provider").value === "anthropic");
  $("#st-base").placeholder = p.base_url || "https://your-provider.com/v1";
  $("#st-model").placeholder = p.model || "model name";
  $("#st-model-hint").textContent = p.model ? `Leave blank to use the default: ${p.model}` : "Enter the model name from your provider's docs.";
  $("#st-key-hint").textContent = s.api_key_masked ? `Saved key: ${s.api_key_masked} (leave blank to keep it)` : "No key saved yet.";
}

$("#st-provider").addEventListener("change", () => { $("#st-base").value = ""; $("#st-model").value = ""; updateSettingsHints(); });

async function saveSettings() {
  await apiJson("/api/settings", {
    method: "POST",
    body: {
      provider: $("#st-provider").value, api_key: $("#st-key").value, base_url: $("#st-base").value,
      model: $("#st-model").value, paper: $("#st-paper").value,
    },
  });
  await loadSettings();
}

$("#st-save").addEventListener("click", async () => {
  try { await saveSettings(); toast("Settings saved."); } catch (e) { toast(e.message, true); }
});

$("#st-test").addEventListener("click", async () => {
  const status = $("#st-status");
  try {
    await saveSettings();
    status.textContent = "Testing…";
    await apiJson("/api/settings/test", { method: "POST" });
    status.textContent = "✅ Connected. You're good to go.";
  } catch (e) {
    status.textContent = "❌ " + e.message;
  }
});

function updateBanner() {
  const b = $("#setup-banner");
  const needKey = !state.settings?.api_key_masked;
  const needMaster = !state.master;
  if (!needKey && !needMaster) return b.classList.add("hidden");
  b.innerHTML = "";
  b.append("Before tailoring: ");
  if (needKey) b.append(el("a", { onclick: () => showTab("settings") }, "add your API key in Settings"));
  if (needKey && needMaster) b.append(" and ");
  if (needMaster) b.append(el("a", { onclick: () => showTab("master") }, "set up your master resume"));
  b.append(".");
  b.classList.remove("hidden");
}

// ---------------------------------------------------------------- master resume

function showMaster(resume) {
  state.master = resume;
  $("#m-empty").classList.toggle("hidden", !!resume);
  if (resume) renderEditor($("#m-editor"), resume, () => {});
  else $("#m-editor").innerHTML = "";
  updateBanner();
}

async function loadMaster() {
  const { resume } = await apiJson("/api/master");
  showMaster(resume);
}

async function importMaster(formData) {
  busy("Reading the resume with AI… (usually 20–60 seconds)");
  try {
    const { resume } = await apiJson("/api/master/import", { method: "POST", body: formData });
    state.master = resume;
    showMaster(resume);
    await apiJson("/api/master", { method: "POST", body: { resume } });
    toast("Imported and saved. Please review every section below.");
  } catch (e) {
    toast(e.message, true);
  } finally {
    busy(null);
  }
}

$("#m-file").addEventListener("change", (ev) => {
  const f = ev.target.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  ev.target.value = "";
  importMaster(fd);
});
$("#m-paste-toggle").addEventListener("click", () => $("#m-paste").classList.toggle("hidden"));
$("#m-parse").addEventListener("click", () => {
  const fd = new FormData();
  fd.append("text", $("#m-text").value);
  importMaster(fd);
});
$("#m-blank").addEventListener("click", async () => {
  if (state.master && !confirm("Replace the current master resume with a blank one?")) return;
  const { resume } = await apiJson("/api/empty-resume");
  showMaster(resume);
});
$("#m-save").addEventListener("click", async () => {
  if (!state.master) return toast("Nothing to save yet.", true);
  try {
    const { resume } = await apiJson("/api/master", { method: "POST", body: { resume: state.master } });
    showMaster(resume);
    toast("Master resume saved.");
  } catch (e) { toast(e.message, true); }
});
$("#m-preview").addEventListener("click", () => state.master && exportResume("pdf", state.master, null, $("#m-frame")));

// ---------------------------------------------------------------- tailoring

function showResult(item) {
  state.current = item;
  item.cover_letter = item.cover_letter || "";
  const a = item.analysis || {};
  $("#result").classList.remove("hidden");
  $("#r-title").textContent = [a.job_title, a.company].filter(Boolean).join(" · ") || "Tailored resume";
  $("#r-sub").textContent = "Created " + fmtDate(item.created);
  $("#s-before").textContent = a.match_score_before ?? "–";
  $("#s-after").textContent = a.match_score_after ?? "–";
  const chips = (node, list) => { node.innerHTML = ""; (list || []).forEach((k) => node.append(el("span", {}, k))); if (!list?.length) node.append(el("em", { class: "muted" }, "None")); };
  chips($("#kw-matched"), a.matched_keywords);
  chips($("#kw-missing"), a.missing_keywords);
  const lis = (node, list) => { node.innerHTML = ""; (list || []).forEach((x) => node.append(el("li", {}, x))); };
  lis($("#changes"), a.changes);
  lis($("#tips"), a.gaps_and_tips);
  $("#jd").value = item.job_description || $("#jd").value;
  $("#r-cover-letter").value = item.cover_letter;

  renderEditor($("#r-editor"), item.resume, () => {
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(() => api(`/api/history/${item.id}`, {
      method: "PUT", body: { resume: item.resume, cover_letter: item.cover_letter },
    }).catch((e) => toast("Could not save changes to History: " + e.message, true)), 800);
  });
  $("#r-frame").removeAttribute("src");
  $("#r-frame-hint").classList.remove("hidden");
  exportResume("pdf", item.resume, item.analysis, $("#r-frame"));
}

$("#r-cover-letter").addEventListener("input", () => {
  if (!state.current) return;
  state.current.cover_letter = $("#r-cover-letter").value;
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(() => api(`/api/history/${state.current.id}`, {
    method: "PUT", body: { cover_letter: state.current.cover_letter },
  }).catch((e) => toast("Could not save the cover letter to History: " + e.message, true)), 800);
});

$("#r-cover-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("#r-cover-letter").value);
    toast("Cover letter copied.");
  } catch (e) {
    toast("Could not copy the cover letter. Check clipboard permissions.", true);
  }
});

$("#r-cover-download").addEventListener("click", () => {
  if (!state.current) return;
  const blob = new Blob([$("#r-cover-letter").value], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const name = (state.current.analysis?.company || "Company").replace(/[^A-Za-z0-9_-]+/g, "_");
  const a = el("a", { href: url, download: `Cover_Letter_${name}.txt` });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
});

$("#tailor-btn").addEventListener("click", async () => {
  const jd = $("#jd").value.trim();
  if (jd.length < 50) return toast("Paste the full job description first.", true);
  busy("Tailoring your resume and writing the cover letter… (usually 30–90 seconds)");
  try {
    const item = await apiJson("/api/tailor", { method: "POST", body: { job_description: jd, pages: $("#pages").value, extra: $("#extra").value } });
    showResult(item);
    $("#result").scrollIntoView({ behavior: "smooth" });
  } catch (e) {
    toast(e.message, true);
  } finally {
    busy(null);
  }
});

$("#r-preview").addEventListener("click", () => state.current && exportResume("pdf", state.current.resume, state.current.analysis, $("#r-frame")));
$("#r-pdf").addEventListener("click", () => state.current && exportResume("pdf", state.current.resume, state.current.analysis));
$("#r-docx").addEventListener("click", () => state.current && exportResume("docx", state.current.resume, state.current.analysis));

// ---------------------------------------------------------------- history

async function loadHistory() {
  const { items } = await apiJson("/api/history");
  const body = $("#h-body");
  body.innerHTML = "";
  $("#h-empty").classList.toggle("hidden", items.length > 0);
  for (const it of items) {
    body.append(el("tr", {},
      el("td", {}, fmtDate(it.created)),
      el("td", {}, it.job_title || "—"),
      el("td", {}, it.company || "—"),
      el("td", {}, it.score != null ? String(it.score) : "—"),
      el("td", {},
        el("button", { class: "link", onclick: async () => { showResult(await apiJson(`/api/history/${it.id}`)); showTab("tailor"); } }, "Open"),
        el("button", { class: "link danger", onclick: async () => { if (confirm("Delete this tailored resume?")) { await api(`/api/history/${it.id}`, { method: "DELETE" }); loadHistory(); } } }, "Delete"),
      ),
    ));
  }
}

// ---------------------------------------------------------------- boot

(async function init() {
  try {
    await Promise.all([loadSettings(), loadMaster()]);
    if (!state.settings.api_key_masked) showTab("settings");
    else if (!state.master) showTab("master");
  } catch (e) {
    toast("Could not reach the app server. Is the black window still open?", true);
  }
})();
