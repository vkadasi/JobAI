"""Prompts and JSON schemas used to parse and tailor resumes."""

import copy

# ---------------------------------------------------------------------------
# Resume schema (shared by the master resume and every tailored version)
# ---------------------------------------------------------------------------

_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}


def _obj(props):
    return {
        "type": "object",
        "properties": props,
        "required": list(props.keys()),
        "additionalProperties": False,
    }


RESUME_SCHEMA = _obj({
    "name": _STR,
    "headline": _STR,
    "contact": _obj({
        "email": _STR,
        "phone": _STR,
        "location": _STR,
        "linkedin": _STR,
        "website": _STR,
    }),
    "summary": _STR,
    "skills": {"type": "array", "items": _obj({"category": _STR, "items": _STR_LIST})},
    "experience": {"type": "array", "items": _obj({
        "title": _STR,
        "company": _STR,
        "location": _STR,
        "start": _STR,
        "end": _STR,
        "bullets": _STR_LIST,
    })},
    "projects": {"type": "array", "items": _obj({
        "name": _STR,
        "link": _STR,
        "bullets": _STR_LIST,
    })},
    "education": {"type": "array", "items": _obj({
        "degree": _STR,
        "school": _STR,
        "location": _STR,
        "start": _STR,
        "end": _STR,
        "details": _STR,
    })},
    "certifications": _STR_LIST,
    "extra_sections": {"type": "array", "items": _obj({"title": _STR, "items": _STR_LIST})},
})

ANALYSIS_SCHEMA = _obj({
    "job_title": _STR,
    "company": _STR,
    "match_score_before": {"type": "integer"},
    "match_score_after": {"type": "integer"},
    "matched_keywords": _STR_LIST,
    "missing_keywords": _STR_LIST,
    "changes": _STR_LIST,
    "gaps_and_tips": _STR_LIST,
})

TAILOR_SCHEMA = _obj({"analysis": ANALYSIS_SCHEMA, "resume": copy.deepcopy(RESUME_SCHEMA)})


def empty_resume():
    return {
        "name": "", "headline": "",
        "contact": {"email": "", "phone": "", "location": "", "linkedin": "", "website": ""},
        "summary": "", "skills": [], "experience": [], "projects": [],
        "education": [], "certifications": [], "extra_sections": [],
    }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PARSE_SYSTEM = """You convert raw resume text into structured JSON.

Rules:
- Copy the candidate's content faithfully. Do not invent, embellish or drop facts.
- Keep each bullet as written (fix only obvious extraction artifacts such as broken line wraps or stray symbols).
- Dates stay in the candidate's format (e.g. "Jan 2021", "2019"). Use "Present" for current roles.
- Group skills into sensible categories if the resume does not already do so.
- Awards, publications, volunteering, languages and similar go into extra_sections.
- Use an empty string or empty list for anything that is not present."""

TAILOR_SYSTEM = """You are an expert resume writer and ATS specialist. You tailor a candidate's master resume to one specific job description.

Hard rules (honesty):
- Never invent employers, job titles, dates, degrees, certifications, tools or metrics that are not in the master resume.
- You may rephrase, reorder, merge, shorten or drop bullets, and mirror the job description's terminology wherever the candidate's real experience genuinely supports it.
- If the job asks for something the candidate has no evidence of, do not add it. List it in missing_keywords and suggest how to address it in gaps_and_tips.

How to tailor:
- headline: a short professional title aligned with the target role.
- summary: 2-4 sentences connecting the candidate's strongest relevant experience to this role's core needs.
- experience: keep every role (with original title, company and dates) but rewrite and reorder the bullets so the most relevant ones come first. Start bullets with strong action verbs and keep any quantified results. Older or less relevant roles get fewer bullets.
- skills: lead with the skills the job asks for that the candidate actually has; drop irrelevant ones.
- projects and extra_sections: keep the ones that strengthen this application.
- Keep contact details and education facts unchanged.
- Plain text only: no markdown, no emojis, no special symbols.

Analysis:
- match_score_before / match_score_after: your honest 0-100 estimate of how well the master resume and the tailored resume match the job.
- matched_keywords: important job keywords the tailored resume now covers.
- missing_keywords: important job requirements the candidate has no evidence for.
- changes: short list of what you changed and why.
- gaps_and_tips: practical advice (e.g. points to raise in the cover letter or interview)."""

LENGTH_HINTS = {
    "1": "Target length: must fit on ONE page. Be selective: about 3-5 bullets for recent roles, 1-2 for older roles.",
    "2": "Target length: up to TWO pages. Include more detail for relevant roles.",
}


def parse_user_prompt(resume_text):
    return f"Convert this resume into the JSON structure.\n\n<resume_text>\n{resume_text}\n</resume_text>"


def tailor_user_prompt(master_json, job_description, pages="1", extra=""):
    parts = [
        f"<master_resume_json>\n{master_json}\n</master_resume_json>",
        f"<job_description>\n{job_description}\n</job_description>",
        LENGTH_HINTS.get(pages, LENGTH_HINTS["1"]),
    ]
    if extra.strip():
        parts.append(f"Additional instructions from the candidate:\n{extra.strip()}")
    parts.append("Return the tailored resume and analysis as JSON.")
    return "\n\n".join(parts)
