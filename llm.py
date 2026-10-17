"""LLM providers: Anthropic (Claude) natively, everything else via an OpenAI-compatible endpoint."""

import json
import re

import prompts

# Presets shown in the Settings screen. "openai_compatible" covers any provider
# that exposes an OpenAI-style /chat/completions endpoint.
PRESETS = {
    "anthropic": {"label": "Anthropic (Claude)", "base_url": "", "model": "claude-opus-5-5"},
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4.1"},
    "gemini": {"label": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "model": "gemini-2.5-flash"},
    "groq": {"label": "Groq", "base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile"},
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "model": "anthropic/claude-sonnet-4.5"},
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
    "custom": {"label": "Other (OpenAI-compatible)", "base_url": "", "model": ""},
}


class LLMError(Exception):
    """An error with a message that is safe and useful to show in the UI."""


def _extract_json(text):
    """Parse JSON from a model reply, tolerating code fences or surrounding prose."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise LLMError("The AI reply was not valid JSON. Please try again (or try a stronger model).")


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

def _anthropic_call(settings, system, user, schema):
    import anthropic

    client = anthropic.Anthropic(api_key=settings["api_key"], timeout=600)
    msg = None
    last_bad_request = None
    try:
        for token_limit in (64000, 32000):
            kwargs = dict(
                model=settings.get("model") or PRESETS["anthropic"]["model"],
                max_tokens=token_limit,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
            )
            try:
                try:
                    # Server-side fallback: if the model declines, the API retries on a suitable model.
                    with client.beta.messages.stream(
                        betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
                    ) as stream:
                        msg = stream.get_final_message()
                except anthropic.BadRequestError:
                    # Older models / accounts may not accept fallbacks; retry without it.
                    with client.messages.stream(**kwargs) as stream:
                        msg = stream.get_final_message()
                break
            except anthropic.BadRequestError as e:
                last_bad_request = e
        if msg is None:
            raise last_bad_request
    except anthropic.AuthenticationError:
        raise LLMError("Invalid Anthropic API key. Check it in Settings.")
    except anthropic.PermissionDeniedError:
        raise LLMError("This API key doesn't have access to that model.")
    except anthropic.NotFoundError:
        raise LLMError("Model not found. Check the model name in Settings.")
    except anthropic.RateLimitError:
        raise LLMError("Rate limited by Anthropic. Wait a minute and try again.")
    except anthropic.BadRequestError as e:
        raise LLMError(f"Request rejected: {e.message}")
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic API error ({e.status_code}). Try again shortly.")
    except anthropic.APIConnectionError:
        raise LLMError("Could not reach Anthropic. Check the internet connection.")

    if msg.stop_reason == "refusal":
        raise LLMError("The model declined this request. Try rephrasing the extra instructions.")
    if msg.stop_reason == "max_tokens":
        raise LLMError("Anthropic cut off the reply at this model's output-token limit. Try a model with a larger output limit, or shorten the master resume.")
    text = "".join(b.text for b in msg.content if b.type == "text")
    return _extract_json(text)


# ---------------------------------------------------------------------------
# OpenAI-compatible (OpenAI, Gemini, Groq, OpenRouter, DeepSeek, custom...)
# ---------------------------------------------------------------------------

def _openai_compatible_call(settings, system, user, schema):
    import openai

    preset = PRESETS.get(settings.get("provider"), PRESETS["custom"])
    base_url = settings.get("base_url") or preset["base_url"]
    model = settings.get("model") or preset["model"]
    if not base_url:
        raise LLMError("Set the API base URL in Settings.")
    if not model:
        raise LLMError("Set the model name in Settings.")

    client = openai.OpenAI(api_key=settings["api_key"], base_url=base_url, timeout=600)
    system_with_schema = (
        f"{system}\n\nRespond with ONLY a JSON object (no markdown, no commentary) "
        f"that matches this JSON Schema exactly:\n{json.dumps(schema)}"
    )
    messages = [{"role": "system", "content": system_with_schema}, {"role": "user", "content": user}]

    try:
        resp = None
        last_bad_request = None
        for token_limit in (8192, 4096):
            for token_parameter in ("max_tokens", "max_completion_tokens"):
                for response_format in ({"type": "json_object"}, None):
                    kwargs = {
                        "model": model,
                        "messages": messages,
                        token_parameter: token_limit,
                    }
                    if response_format:
                        kwargs["response_format"] = response_format
                    try:
                        resp = client.chat.completions.create(**kwargs)
                        break
                    except openai.BadRequestError as e:
                        last_bad_request = e
                if resp is not None:
                    break
            if resp is not None:
                break
        if resp is None:
            raise last_bad_request
    except openai.AuthenticationError:
        raise LLMError("Invalid API key. Check it in Settings.")
    except openai.PermissionDeniedError:
        raise LLMError("This API key doesn't have access to that model.")
    except openai.NotFoundError:
        raise LLMError("Model or endpoint not found. Check the base URL and model name in Settings.")
    except openai.RateLimitError:
        raise LLMError("Rate limited or out of credits. Wait a minute or check your plan.")
    except openai.BadRequestError as e:
        raise LLMError(f"Request rejected: {e.message}")
    except openai.APIStatusError as e:
        raise LLMError(f"API error ({e.status_code}). Try again shortly.")
    except openai.APIConnectionError:
        raise LLMError("Could not reach the API. Check the internet connection and base URL.")

    choice = resp.choices[0]
    if choice.finish_reason == "length":
        raise LLMError("The AI provider cut off the reply at its output-token limit. Try a model with a larger output limit, or shorten the master resume.")
    return _extract_json(choice.message.content or "")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def call_json(settings, system, user, schema):
    if not settings.get("api_key"):
        raise LLMError("No API key yet. Open Settings and paste your API key.")
    if settings.get("provider") == "anthropic":
        return _anthropic_call(settings, system, user, schema)
    return _openai_compatible_call(settings, system, user, schema)


def _merge_defaults(data, template):
    """Fill missing keys so downstream code can rely on the full resume shape."""
    if isinstance(template, dict):
        data = data if isinstance(data, dict) else {}
        return {k: _merge_defaults(data.get(k), v) for k, v in template.items()}
    if isinstance(template, list):
        return data if isinstance(data, list) else []
    return data if isinstance(data, str) else ("" if data is None else str(data))


def normalize_resume(data):
    resume = _merge_defaults(data, prompts.empty_resume())
    item_templates = {
        "skills": {"category": "", "items": []},
        "experience": {"title": "", "company": "", "location": "", "start": "", "end": "", "bullets": []},
        "projects": {"name": "", "link": "", "bullets": []},
        "education": {"degree": "", "school": "", "location": "", "start": "", "end": "", "details": ""},
        "extra_sections": {"title": "", "items": []},
    }
    for key, tmpl in item_templates.items():
        resume[key] = [_merge_defaults(item, tmpl) for item in resume[key] if isinstance(item, dict)]
        for item in resume[key]:
            for list_key in ("items", "bullets"):
                if list_key in item:
                    item[list_key] = [str(x) for x in item[list_key] if str(x).strip()]
    resume["certifications"] = [str(x) for x in resume["certifications"] if str(x).strip()]
    return resume


def parse_resume(settings, resume_text):
    data = call_json(settings, prompts.PARSE_SYSTEM, prompts.parse_user_prompt(resume_text), prompts.RESUME_SCHEMA)
    return normalize_resume(data)


def tailor_resume(settings, master, job_description, pages="1", extra=""):
    user = prompts.tailor_user_prompt(json.dumps(master, indent=1), job_description, pages, extra)
    data = call_json(settings, prompts.TAILOR_SYSTEM, user, prompts.TAILOR_SCHEMA)
    resume = normalize_resume(data.get("resume", {}))
    cover_letter_data = call_json(
        settings,
        prompts.COVER_LETTER_SYSTEM,
        prompts.cover_letter_user_prompt(json.dumps(resume, indent=1), job_description),
        prompts.COVER_LETTER_SCHEMA,
    )
    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else {}
    return {
        "resume": resume,
        "cover_letter": str(cover_letter_data.get("cover_letter", "")),
        "analysis": {
            "job_title": str(analysis.get("job_title", "")),
            "company": str(analysis.get("company", "")),
            "match_score_before": analysis.get("match_score_before", 0),
            "match_score_after": analysis.get("match_score_after", 0),
            "matched_keywords": list(analysis.get("matched_keywords", []) or []),
            "missing_keywords": list(analysis.get("missing_keywords", []) or []),
            "changes": list(analysis.get("changes", []) or []),
            "gaps_and_tips": list(analysis.get("gaps_and_tips", []) or []),
        },
    }


def test_connection(settings):
    schema = prompts._obj({"ok": {"type": "boolean"}})
    data = call_json(settings, "You are a connectivity check.", 'Reply with {"ok": true}.', schema)
    return bool(data.get("ok"))
