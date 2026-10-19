"""LLM providers: Anthropic (Claude) natively, everything else via an OpenAI-compatible endpoint."""

import json
import re
import time

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

EXPERIENCE_BATCH_SIZE = 3


class LLMError(Exception):
    """An error with a message that is safe and useful to show in the UI."""


def _is_quota_error(error):
    details = [str(error), str(getattr(error, "code", "") or "")]
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        error_body = body.get("error", body)
        if isinstance(error_body, dict):
            details.extend(str(error_body.get(key, "") or "") for key in ("code", "type", "message"))
    text = " ".join(details).lower()
    return any(term in text for term in (
        "insufficient_quota", "insufficient quota", "out of credits",
        "insufficient credits", "credit balance", "billing hard limit",
        "exceeded your current quota", "check your plan and billing",
        "credit balance is too low",
    ))


def _retry_delay(error, fallback):
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) or {}
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return min(60.0, max(0.0, float(retry_after)))
    except (TypeError, ValueError):
        return fallback


def _with_rate_limit_retries(request, error_type, provider):
    delays = (2, 5, 10)
    for attempt in range(len(delays) + 1):
        try:
            return request()
        except error_type as error:
            if _is_quota_error(error):
                raise LLMError(
                    f"{provider} reports that the API account has run out of credits or quota. "
                    "Check the provider's billing and usage limits."
                ) from error
            if attempt == len(delays):
                raise LLMError(
                    f"{provider} is temporarily rate limiting requests after several retries. "
                    "Wait a minute and try again."
                ) from error
            time.sleep(_retry_delay(error, delays[attempt]))


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

    client = anthropic.Anthropic(api_key=settings["api_key"], timeout=600, max_retries=0)

    def request():
        msg = None
        last_bad_request = None
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
                return msg
            except anthropic.BadRequestError as e:
                last_bad_request = e
        raise last_bad_request

    try:
        msg = _with_rate_limit_retries(request, anthropic.RateLimitError, "Anthropic")
    except anthropic.AuthenticationError:
        raise LLMError("Invalid Anthropic API key. Check it in Settings.")
    except anthropic.PermissionDeniedError:
        raise LLMError("This API key doesn't have access to that model.")
    except anthropic.NotFoundError:
        raise LLMError("Model not found. Check the model name in Settings.")
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

    client = openai.OpenAI(api_key=settings["api_key"], base_url=base_url, timeout=600, max_retries=0)
    system_with_schema = (
        f"{system}\n\nRespond with ONLY a JSON object (no markdown, no commentary) "
        f"that matches this JSON Schema exactly:\n{json.dumps(schema)}"
    )
    messages = [{"role": "system", "content": system_with_schema}, {"role": "user", "content": user}]

    def request():
        last_bad_request = None
        request_variants = (
            {"max_tokens": 8192, "response_format": {"type": "json_object"}},
            {"max_tokens": 8192},
            {"max_completion_tokens": 8192, "response_format": {"type": "json_object"}},
            {"max_completion_tokens": 8192},
        )
        for options in request_variants:
            try:
                return client.chat.completions.create(
                    model=model, messages=messages, **options
                )
            except openai.BadRequestError as e:
                last_bad_request = e
        raise last_bad_request

    try:
        resp = _with_rate_limit_retries(request, openai.RateLimitError, "The AI provider")
    except openai.AuthenticationError:
        raise LLMError("Invalid API key. Check it in Settings.")
    except openai.PermissionDeniedError:
        raise LLMError("This API key doesn't have access to that model.")
    except openai.NotFoundError:
        raise LLMError("Model or endpoint not found. Check the base URL and model name in Settings.")
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


def tailor_resume(settings, master, job_description, extra=""):
    user = prompts.tailor_user_prompt(json.dumps(master, indent=1), job_description, extra)
    try:
        data = call_json(settings, prompts.TAILOR_SYSTEM, user, prompts.TAILOR_SCHEMA)
    except LLMError as e:
        raise LLMError(f"Could not generate the tailored resume structure: {e}") from e
    resume = normalize_resume(data.get("resume", {}))
    source_experience = normalize_resume({"experience": master.get("experience", [])})["experience"]
    resume["experience"] = source_experience
    for start in range(0, len(source_experience), EXPERIENCE_BATCH_SIZE):
        batch = source_experience[start:start + EXPERIENCE_BATCH_SIZE]
        roles = [{"role_index": start + offset, "role": role} for offset, role in enumerate(batch)]
        try:
            result = call_json(
                settings,
                prompts.EXPERIENCE_BULLETS_SYSTEM,
                prompts.experience_bullets_user_prompt(
                    json.dumps(roles, indent=1), job_description, extra
                ),
                prompts.EXPERIENCE_BULLETS_SCHEMA,
            )
        except LLMError as e:
            companies = ", ".join(
                role.get("company") or role.get("title") or "a role" for role in batch
            )
            raise LLMError(f"Could not tailor bullets for {companies}: {e}") from e
        generated_roles = result.get("roles", [])
        if not isinstance(generated_roles, list):
            raise LLMError(
                "The AI returned invalid experience bullets. Please try tailoring again."
            )
        expected_indexes = set(range(start, start + len(batch)))
        actual_indexes = []
        for generated in generated_roles:
            if (
                not isinstance(generated, dict)
                or isinstance(generated.get("role_index"), bool)
                or not isinstance(generated.get("role_index"), int)
            ):
                raise LLMError(
                    "The AI returned invalid experience bullets. Please try tailoring again."
                )
            actual_indexes.append(generated["role_index"])
        if set(actual_indexes) != expected_indexes or len(actual_indexes) != len(expected_indexes):
            raise LLMError(
                "The AI returned incomplete or mismatched experience bullets. Please try tailoring again."
            )
        for generated in generated_roles:
            index = generated["role_index"]
            bullets = generated.get("bullets", [])
            if not isinstance(bullets, list):
                raise LLMError(
                    "The AI returned invalid experience bullets. Please try tailoring again."
                )
            resume["experience"][index]["bullets"] = [
                str(b).strip() for b in bullets if str(b).strip()
            ][:5]

    cover_letter = generate_cover_letter(settings, master, resume, job_description)
    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else {}
    return {
        "resume": resume,
        "cover_letter": cover_letter,
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


def generate_cover_letter(settings, master, resume, job_description):
    data = call_json(
        settings,
        prompts.COVER_LETTER_SYSTEM,
        prompts.cover_letter_user_prompt(
            json.dumps(master, indent=1),
            json.dumps(normalize_resume(resume), indent=1),
            job_description,
        ),
        prompts.COVER_LETTER_SCHEMA,
    )
    cover_letter = str(data.get("cover_letter", "")).strip()
    if not cover_letter:
        raise LLMError("The AI returned an empty cover letter. Please try updating it again.")
    return cover_letter


def test_connection(settings):
    schema = prompts._obj({"ok": {"type": "boolean"}})
    data = call_json(settings, "You are a connectivity check.", 'Reply with {"ok": true}.', schema)
    return bool(data.get("ok"))
