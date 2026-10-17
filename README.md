# Resume Tailor

Paste a job description and get a resume tailored to it, downloadable as **DOCX** and **PDF**.
Everything runs on this laptop; your resume and API key stay in the `data` folder here.

## First-time setup (Windows)

1. **Install Python** (once): go to <https://www.python.org/downloads/>, download the latest version,
   run the installer and **tick "Add python.exe to PATH"** on the first screen.
2. **Double-click `start.bat`** in this folder.
   The first run takes 1–3 minutes while it installs what it needs. Later runs start in seconds.
3. A browser tab opens at <http://127.0.0.1:5050>. **Keep the black window open** while you use the app;
   close it when you're done.

> If Windows shows "Windows protected your PC", click **More info → Run anyway**.

## Using it

1. **Settings**: choose the AI provider, paste the API key, click **Test connection**.
   - *Anthropic (Claude)*: just the key.
   - *OpenAI, Gemini, Groq, OpenRouter, DeepSeek*: key only; the URL and model are preset.
   - *Other (OpenAI-compatible)*: paste the provider's base URL and model name too.
   - The model box can be left blank to use the preset default, or overwritten with any model your key supports.
2. **Master Resume**: upload the full resume (PDF, DOCX or TXT) once. The AI turns it into editable sections;
   check every section, fix anything wrong and click **Save master resume**.
   Put *everything* here, because tailored versions only use what's in the master resume.
3. **Tailor**: paste a job description, choose 1 or 2 pages, optionally add instructions, and click **Tailor my resume**.
   You get a before/after match score, the keywords covered and missing, an editable resume with a live PDF preview,
   and a tailored cover letter, generated in a separate response to keep each AI output smaller.
   The cover letter uses both the master and tailored resumes. The AI targets five concise bullets for each role
   when the master resume supports them. Edit the cover letter, update it from your latest resume edits, copy it,
   or download it as a text file.
4. **History**: every tailored resume is saved and can be reopened, edited and re-downloaded.

The AI is told never to invent jobs, titles, dates, degrees, skills or numbers. Anything the job asks for that
isn't in your experience is listed under "Missing" instead of being added. Still read every resume before sending it.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Python 3.10 or newer is not installed" | Install Python as in step 1 (tick *Add to PATH*), then run `start.bat` again. |
| Setup failed / packages won't install | Check the internet connection, delete the `.venv` folder, run `start.bat` again. |
| Browser didn't open | Open <http://127.0.0.1:5050> yourself. |
| "Invalid API key" / "Model not found" | Fix them in **Settings** and click **Test connection**. |
| Upload says it can't read the file | It's probably a scanned PDF. Upload the DOCX, or use **Paste text instead**. |
| Port already in use | Another copy is already running. Close the other black window. |

## Moving it to another computer

Copy this whole folder **without** the `.venv` folder (it's rebuilt automatically).
Include the `data` folder to keep the settings, master resume and history; leave it out for a clean start.

## For developers

```
pip install -r requirements.txt
python app.py
```
Files: `app.py` (Flask server and routes), `llm.py` (providers), `prompts.py` (prompts and JSON schema),
`resume_io.py` (file reading, DOCX/PDF rendering), `static/` (UI). The port can be changed with the `RESUME_TAILOR_PORT` env var.
