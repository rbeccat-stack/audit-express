"""
Audit Growth Express — core audit logic.

Fetches website content, calls OpenRouter LLM, returns structured audit.
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import AsyncGenerator

import httpx
from bs4 import BeautifulSoup

OPENROUTER_API_KEY = ""  # Set via env var or .env file
OPENROUTER_MODEL = "openai/gpt-4o-mini"  # fast + cheap for MVP
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = "audit@remibk-studio.fr"
REMI_EMAIL = "remi@remibk-studio.fr"

_env_paths = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    "/root/.hermes/.env",
]
for _p in _env_paths:
    if os.path.exists(_p):
        with open(_p) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line.startswith("#") or "=" not in _line:
                    continue
                _k, _v = _line.split("=", 1)
                _k = _k.strip()
                _v = _v.strip()
                if _k == "OPENROUTER_API_KEY" and _v and _v != "***":
                    OPENROUTER_API_KEY = _v
                if _k == "RESEND_API_KEY" and _v and _v != "***":
                    RESEND_API_KEY = _v
        if OPENROUTER_API_KEY:
            break

# Also check process env
_env_var = os.environ.get("OPENROUTER_API_KEY", "")
if _env_var:
    OPENROUTER_API_KEY = _env_var

_resend_env = os.environ.get("RESEND_API_KEY", "")
if _resend_env:
    RESEND_API_KEY = _resend_env

REQUEST_TIMEOUT = 30.0
MAX_TEXT_LENGTH = 12_000  # characters to feed the LLM


# ── helpers ────────────────────────────────────────────────────────

def _extract_text(html: str, url: str) -> str:
    """Strip HTML → clean text, remove boilerplate."""
    soup = BeautifulSoup(html, "lxml")

    # Remove noise
    for tag in soup(["script", "style", "nav", "footer", "header",
                      "iframe", "noscript", "svg", "form", "button"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()

    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "\n… [truncated]"

    return text


def _normalise_url(raw: str) -> str:
    """If no scheme, prepend https://."""
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw.rstrip("/")


async def _try_fetch(client: httpx.AsyncClient, url: str, path: str = "") -> str | None:
    """Fetch a single page, return cleaned text or None."""
    full_url = url + path
    try:
        resp = await client.get(full_url, follow_redirects=True, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return None
        text = _extract_text(resp.text, full_url)
        return text if len(text) > 100 else None
    except Exception:
        return None


# ── LLM call ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es un growth hacker senior. Tu analyses des entreprises à partir du contenu de leur site web.

Pour chaque entreprise, tu identifies :
1. Une **force growth** détectée (SEO, réseau social, contenu, partenariats…) — précis, chiffré si possible
2. Une **opportunité growth** non exploitée — actionable, concrète, avec une piste de mise en œuvre
3. Une **question d'entretien** pertinente que le recruteur pourrait poser
4. Un **candidat fit** : pourquoi Rémi (growth hacker, 8k contacts générés chez Locabri, automation Make.com, data-driven) est le bon profil

Réponds UNIQUEMENT en JSON valide. Pas de markdown, pas de texte avant/après."""


async def _call_llm(entreprise: str, site_text: str) -> dict:
    """Call OpenRouter and return parsed JSON audit."""
    if not OPENROUTER_API_KEY:
        return _fallback_audit(entreprise, "API key OpenRouter manquante — audit simulé")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://audit-express.remi.dev",
        "X-Title": "Audit Growth Express",
    }

    user_prompt = f"""Entreprise : {entreprise}

CONTENU DU SITE WEB :
{site_text}

Retourne UNIQUEMENT un JSON valide avec ces champs :
- "entreprise": nom de l'entreprise
- "force_detectee": une force growth détectée (précise, chiffrée si possible)
- "opportunity_growth": une opportunité growth non exploitée (actionnable)
- "question_entretien": une question d'entretien pertinente pour le recruteur
- "candidat_fit": pourquoi Rémi (growth hacker) est le bon profil
- "temps_generation": "~28s"
"""

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 800,
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        try:
            resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            # Extract JSON from possible markdown fences
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_match:
                content = json_match.group(1)
            parsed = json.loads(content)
            parsed.setdefault("entreprise", entreprise)
            parsed.setdefault("temps_generation", "~28s")
            return parsed
        except Exception as exc:
            return _fallback_audit(entreprise, f"Erreur LLM : {exc}")


async def _send_email(to_email: str, audit: dict) -> None:
    """Send audit result via Resend API."""
    if not RESEND_API_KEY or not to_email:
        return

    entreprise = audit.get("entreprise", "cette entreprise")
    force = audit.get("force_detectee", "")
    opportunity = audit.get("opportunity_growth", "")
    question = audit.get("question_entretien", "")
    fit = audit.get("candidat_fit", "")
    timing = audit.get("temps_generation", "")

    html = f"""
<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"></head>
<body style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px 24px; color: #1f2937;">
  <h2 style="font-size: 20px; font-weight: 700; margin-bottom: 24px;">
    Audit Growth Express — {entreprise}
  </h2>

  <div style="border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px 20px; margin-bottom: 12px;">
    <p style="font-size: 11px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; color: #6b7280; margin: 0 0 8px;">💪 Force détectée</p>
    <p style="font-size: 15px; color: #1f2937; line-height: 1.6; margin: 0;">{force}</p>
  </div>

  <div style="border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px 20px; margin-bottom: 12px;">
    <p style="font-size: 11px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; color: #6b7280; margin: 0 0 8px;">📈 Opportunity growth</p>
    <p style="font-size: 15px; color: #1f2937; line-height: 1.6; margin: 0;">{opportunity}</p>
  </div>

  <div style="border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px 20px; margin-bottom: 12px;">
    <p style="font-size: 11px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; color: #6b7280; margin: 0 0 8px;">❓ Question entretien</p>
    <p style="font-size: 15px; color: #1f2937; line-height: 1.6; margin: 0;">{question}</p>
  </div>

  <div style="border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px 20px; margin-bottom: 24px;">
    <p style="font-size: 11px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; color: #6b7280; margin: 0 0 8px;">🎯 Candidat fit</p>
    <p style="font-size: 15px; color: #1f2937; line-height: 1.6; margin: 0;">{fit}</p>
  </div>

  <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
  <p style="font-size: 13px; color: #6b7280; margin: 0;">
    Généré en {timing} · <a href="https://audit.remibk-studio.fr" style="color: #7c3aed;">audit.remibk-studio.fr</a>
  </p>
</body>
</html>
"""

    payload = {
        "from": f"Rémi — Audit Growth <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": f"Votre audit growth — {entreprise}",
        "html": html,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            logging.info(f"Email sent to {to_email}: {resp.json().get('id')}")
    except Exception as exc:
        logging.warning(f"Email send failed: {exc}")


def _fallback_audit(entreprise: str, reason: str) -> dict:
    """Return a placeholder audit when something fails."""
    return {
        "entreprise": entreprise,
        "force_detectee": f"Analyse temporairement indisponible. {reason}",
        "opportunity_growth": "Vérifie la disponibilité du service et réessaie.",
        "question_entretien": "Comment mesurez-vous l'impact de vos canaux d'acquisition actuels ?",
        "candidat_fit": "Rémi — growth hacker data-driven, automation Make.com, 8k contacts générés chez Locabri.",
        "temps_generation": "~28s",
    }


# ── Public API ─────────────────────────────────────────────────────

async def run_audit(url: str, email: str = "") -> AsyncGenerator[dict, None]:
    """
    Generator that yields SSE events.

    Yields dicts with keys:
      {"type": "progress", "data": "message"}
      {"type": "result", "data": {...}}
      {"type": "error", "data": "message"}
    """
    start = time.time()
    entreprise = url.split("//")[-1].split("/")[0].replace("www.", "")

    # 1. Progress
    yield {"type": "progress", "data": "🔍 Scraping du site…"}

    # 2. Fetch website
    full_url = _normalise_url(url)
    pages_text = {}

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AuditExpress/1.0)"},
    ) as client:
        # Try homepage + common pages in parallel
        tasks = {
            "/": _try_fetch(client, full_url, ""),
            "/about": _try_fetch(client, full_url, "/about"),
            "/about-us": _try_fetch(client, full_url, "/about-us"),
            "/blog": _try_fetch(client, full_url, "/blog"),
        }
        results = await asyncio.gather(*tasks.values())

        for path, text in zip(tasks.keys(), results):
            if text:
                pages_text[path] = text

    if not pages_text:
        yield {"type": "error", "data": "Impossible d'atteindre ce site — vérifie l'URL et réessaie."}
        return

    # 3. Combine
    combined = ""
    for path, text in pages_text.items():
        label = f"--- Page: {full_url}{path} ---\n"
        combined += label + text + "\n\n"

    if len(combined) > MAX_TEXT_LENGTH:
        combined = combined[:MAX_TEXT_LENGTH] + "\n… [truncated]"

    # 4. LLM
    yield {"type": "progress", "data": "🤖 Synthèse IA…"}

    try:
        audit = await _call_llm(entreprise, combined)
    except Exception as exc:
        yield {"type": "error", "data": f"Erreur lors de l'analyse : {exc}"}
        return

    # Add timing
    elapsed = round(time.time() - start)
    audit["temps_generation"] = f"~{elapsed}s"

    yield {"type": "result", "data": audit}

    # Send email in background (non-blocking)
    if email:
        asyncio.create_task(_send_email(email, audit))