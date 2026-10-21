"""Resume Tailor: a small local web app. Run `python app.py` and open http://127.0.0.1:5050"""

import json
import os
import threading
import time
import uuid
import webbrowser
from datetime import datetime

from flask import Flask, jsonify, request, send_file, send_from_directory
import io

import llm
import prompts
import resume_io

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("RESUME_TAILOR_DATA") or os.path.join(ROOT, "data")
HISTORY = os.path.join(DATA, "history")
SETTINGS_FILE = os.path.join(DATA, "settings.json")
MASTER_FILE = os.path.join(DATA, "master_resume.json")
PORT = int(os.environ.get("RESUME_TAILOR_PORT", "5050"))

os.makedirs(HISTORY, exist_ok=True)
app = Flask(__name__, static_folder=os.path.join(ROOT, "static"), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

DEFAULT_SETTINGS = {"provider": "anthropic", "api_key": "", "base_url": "", "model": "", "paper": "A4"}


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_settings():
    return {**DEFAULT_SETTINGS, **_read_json(SETTINGS_FILE, {})}


def _mask(key):
    return (key[:6] + "…" + key[-4:]) if len(key) > 12 else ("set" if key else "")


def _history_path(item_id):
    safe = "".join(c for c in item_id if c.isalnum() or c in "-_")
    return os.path.join(HISTORY, safe + ".json")


def _err(msg, code=400):
    return jsonify({"error": msg}), code


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/settings")
def get_settings():
    s = load_settings()
    return jsonify({**{k: v for k, v in s.items() if k != "api_key"}, "api_key_masked": _mask(s["api_key"]),
                    "presets": llm.PRESETS})


@app.post("/api/settings")
def save_settings():
    body = request.get_json(force=True)
    s = load_settings()
    for key in ("provider", "base_url", "model", "paper"):
        if key in body:
            s[key] = str(body[key]).strip()
    if body.get("api_key"):  # blank means "keep the existing key"
        s["api_key"] = str(body["api_key"]).strip()
    if s["provider"] not in llm.PRESETS:
        return _err("Unknown provider.")
    _write_json(SETTINGS_FILE, s)
    return jsonify({"ok": True, "api_key_masked": _mask(s["api_key"])})


@app.post("/api/settings/test")
def test_settings():
    try:
        llm.test_connection(load_settings())
        return jsonify({"ok": True})
    except llm.LLMError as e:
        return _err(str(e))


@app.get("/api/master")
def get_master():
    return jsonify({"resume": _read_json(MASTER_FILE, None)})


@app.post("/api/master")
def save_master():
    body = request.get_json(force=True)
    resume = llm.normalize_resume(body.get("resume", {}))
    _write_json(MASTER_FILE, resume)
    return jsonify({"ok": True, "resume": resume})


@app.post("/api/master/import")
def import_master():
    """Accepts an uploaded file (PDF/DOCX/TXT) or pasted text, and parses it with the AI."""
    try:
        if "file" in request.files and request.files["file"].filename:
            f = request.files["file"]
            text = resume_io.extract_text(f.filename, f.read())
        else:
            text = (request.form.get("text") or "").strip()
            if len(text) < 50:
                return _err("Paste the full resume text or upload a file.")
        resume = llm.parse_resume(load_settings(), text)
    except ValueError as e:
        return _err(str(e))
    except llm.LLMError as e:
        return _err(str(e))
    return jsonify({"resume": resume})


@app.post("/api/tailor")
def tailor():
    body = request.get_json(force=True)
    jd = (body.get("job_description") or "").strip()
    if len(jd) < 50:
        return _err("Paste the full job description first.")
    master = _read_json(MASTER_FILE, None)
    if not master:
        return _err("Set up your master resume first (Master Resume tab).")
    include_cover_letter = body.get("include_cover_letter", True)
    if not isinstance(include_cover_letter, bool):
        return _err("Choose whether to generate a cover letter.")
    try:
        result = llm.tailor_resume(
            load_settings(), master, jd, body.get("extra", ""),
            include_cover_letter=include_cover_letter,
        )
    except llm.LLMError as e:
        return _err(str(e))

    item = {
        "id": datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6],
        "created": datetime.now().isoformat(timespec="seconds"),
        "job_description": jd,
        **result,
    }
    _write_json(_history_path(item["id"]), item)
    return jsonify(item)


@app.get("/api/history")
def history_list():
    items = []
    for name in sorted(os.listdir(HISTORY), reverse=True):
        if name.endswith(".json"):
            it = _read_json(os.path.join(HISTORY, name), None)
            if it:
                a = it.get("analysis", {})
                items.append({"id": it["id"], "created": it.get("created"), "job_title": a.get("job_title", ""),
                              "company": a.get("company", ""), "score": a.get("match_score_after")})
    return jsonify({"items": items})


@app.get("/api/history/<item_id>")
def history_get(item_id):
    it = _read_json(_history_path(item_id), None)
    return jsonify(it) if it else _err("Not found.", 404)


@app.post("/api/history/<item_id>/cover-letter")
def history_generate_cover_letter(item_id):
    path = _history_path(item_id)
    it = _read_json(path, None)
    if not it:
        return _err("Not found.", 404)
    master = _read_json(MASTER_FILE, None)
    if not master:
        return _err("Set up your master resume first (Master Resume tab).")
    body = request.get_json(force=True)
    resume = llm.normalize_resume(body.get("resume", it.get("resume", {})))
    try:
        cover_letter = llm.generate_cover_letter(
            load_settings(), master, resume, it.get("job_description", "")
        )
    except llm.LLMError as e:
        return _err(str(e))
    it["resume"] = resume
    it["cover_letter"] = cover_letter
    _write_json(path, it)
    return jsonify({"cover_letter": cover_letter})


@app.put("/api/history/<item_id>")
def history_update(item_id):
    path = _history_path(item_id)
    it = _read_json(path, None)
    if not it:
        return _err("Not found.", 404)
    body = request.get_json(force=True)
    if "resume" in body:
        it["resume"] = llm.normalize_resume(body["resume"])
    if "cover_letter" in body:
        it["cover_letter"] = str(body["cover_letter"])
    _write_json(path, it)
    return jsonify({"ok": True})


@app.delete("/api/history/<item_id>")
def history_delete(item_id):
    path = _history_path(item_id)
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"ok": True})


@app.post("/api/export/<fmt>")
def export(fmt):
    body = request.get_json(force=True)
    resume = llm.normalize_resume(body.get("resume", {}))
    paper = load_settings().get("paper", "A4")
    name = resume_io.safe_filename(resume, body.get("analysis"))
    inline = bool(body.get("inline"))
    if fmt == "pdf":
        data = resume_io.build_pdf(resume, paper)
        return send_file(io.BytesIO(data), mimetype="application/pdf", as_attachment=not inline,
                         download_name=name + ".pdf")
    if fmt == "docx":
        data = resume_io.build_docx(resume, paper)
        return send_file(io.BytesIO(data), as_attachment=True, download_name=name + ".docx",
                         mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    return _err("Unknown format.")


@app.get("/api/empty-resume")
def empty_resume():
    return jsonify({"resume": prompts.empty_resume()})


def _open_browser():
    time.sleep(1.2)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    print(f"\n  Resume Tailor is running at http://127.0.0.1:{PORT}\n  Keep this window open while you use it. Close it to stop.\n")
    if not os.environ.get("RESUME_TAILOR_NO_BROWSER"):
        threading.Thread(target=_open_browser, daemon=True).start()
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
