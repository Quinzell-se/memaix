# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lager 1 — provider-adaptrar bakom ETT anrop (FEATURE-LLM-ENGINE.md).

Tre adaptrar täcker åtta leverantörsval:
- anthropic            → Messages API
- google               → Gemini generateContent
- openai-compatible    → chat/completions: openai, openrouter, mistral,
                         ollama, vllm och egen endpoint — samma format,
                         olika bas-URL.

Säkerhetskontraktet (specens §Säkerhet, byggs här — inte efteråt):
- API-nyckeln läses per anrop via config.secret(), skickas i header (aldrig
  i URL), hålls inte i klientobjektet och förekommer aldrig i fel/loggar.
- Egress: inga redirects följs; länk-lokala/metadata-adresser vägras.
  Privata LAN-adresser är däremot tillåtna — lokal Ollama är ett huvudfall.
- Leverantörsfel saneras och trunkeras innan de når anroparen.

Inga leverantörs-SDK:er — httpx (befintligt beroende) rakt mot REST.
Verktygsanrop (tools) kommer i Fas 2; signaturen är förberedd.
"""

from __future__ import annotations

import ipaddress
import time
from urllib.parse import urlparse

import httpx

_TIMEOUT = 30.0
_ERROR_BODY_MAX = 300

# Default-endpoints för API-leverantörer; endpoint-leverantörer (ollama/vllm/
# openai-compatible) kräver explicit URL (setup_engine/admin_llm validerar).
_DEFAULT_ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "mistral": "https://api.mistral.ai/v1",
}

_BLOCKED_HOSTS = {"metadata.google.internal", "metadata", "instance-data"}


class LLMError(RuntimeError):
    """Sanerat leverantörsfel — säkert att visa för admin (aldrig nyckeln)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class LLMNotConfigured(LLMError):
    """Inget model-block — BYO-läge; motorn är avstängd per design."""

    def __init__(self):
        super().__init__("inget model-block i memaix.yaml (BYO-läge)")


def _guard_endpoint(url: str) -> None:
    """Vägra länk-lokala/metadata-mål. Privat LAN är tillåtet (lokal Ollama)."""
    host = urlparse(url).hostname or ""
    if host.lower() in _BLOCKED_HOSTS:
        raise LLMError(f"endpoint-värd tillåts inte: {host}")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return  # värdnamn — DNS-upplösning sker i httpx; kända metadatanamn stoppade ovan
    if ip.is_link_local:
        raise LLMError(f"länk-lokal endpoint tillåts inte: {host}")


def _sanitize(body: str) -> str:
    return body.replace("\n", " ")[:_ERROR_BODY_MAX]


class LLMClient:
    """Ett anrop — complete(messages) → text. Adapter väljs av model-blocket."""

    def __init__(self, model_cfg: dict, api_key: str | None):
        self.provider = model_cfg.get("provider", "")
        self.model = model_cfg.get("name", "")
        self.endpoint = (model_cfg.get("endpoint") or "").rstrip("/")
        self._key = api_key  # hålls bara under objektets (korta) livstid

    @classmethod
    def from_config(cls, cfg: dict) -> "LLMClient":
        """Bygg från config.load()-resultatet. LLMNotConfigured i BYO-läge."""
        model = (cfg.get("memaix") or {}).get("model") or {}
        if not model.get("provider"):
            raise LLMNotConfigured()
        key = None
        ref = model.get("api_key_ref")
        if ref:
            from .. import config as _config

            try:
                key = _config.secret(ref)
            except (KeyError, ValueError) as exc:
                raise LLMError(f"API-nyckelns ref gick inte att lösa: {type(exc).__name__}")
        return cls(model, key)

    # ------------------------------------------------------------------

    def complete(self, messages: list, max_tokens: int = 1024) -> str:
        """En icke-strömmande tur utan verktyg (Fas 1). messages:
        [{"role": "user"|"assistant"|"system", "content": str}, …]"""
        if self.provider == "anthropic":
            return self._anthropic(messages, max_tokens)
        if self.provider == "google":
            return self._google(messages, max_tokens)
        return self._openai_compatible(messages, max_tokens)

    def test(self) -> dict:
        """Minimalt riktigt anrop — admin-knappen och doctor. Hemlighetsfritt svar."""
        started = time.monotonic()
        reply = self.complete(
            [{"role": "user", "content": "Svara med exakt ordet: ok"}], max_tokens=16
        )
        return {
            "ok": True,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "reply": reply.strip()[:80],
        }

    # ------------------------------------------------------------------

    def _post(self, url: str, headers: dict, payload: dict) -> dict:
        _guard_endpoint(url)
        try:
            resp = httpx.post(
                url, json=payload, headers=headers,
                timeout=_TIMEOUT, follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            # httpx-fel innehåller URL:en men aldrig headers — säkert att visa.
            raise LLMError(f"kunde inte nå {self.provider}: {type(exc).__name__}")
        if resp.status_code >= 400:
            raise LLMError(
                f"{self.provider} svarade {resp.status_code}: {_sanitize(resp.text)}",
                status=resp.status_code,
            )
        try:
            return resp.json()
        except ValueError:
            raise LLMError(f"{self.provider} svarade inte med JSON")

    def _anthropic(self, messages: list, max_tokens: int) -> str:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [m for m in messages if m["role"] != "system"],
        }
        if system:
            payload["system"] = system
        base = self.endpoint or "https://api.anthropic.com"
        data = self._post(
            f"{base}/v1/messages",
            {"x-api-key": self._key or "", "anthropic-version": "2023-06-01"},
            payload,
        )
        blocks = data.get("content") or []
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")

    def _openai_compatible(self, messages: list, max_tokens: int) -> str:
        base = self.endpoint or _DEFAULT_ENDPOINTS.get(self.provider, "")
        if not base:
            raise LLMError(f"{self.provider} kräver en endpoint-URL")
        # Ollama m.fl. anges ofta utan /v1 — normalisera i stället för att gissa fel.
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        headers = {}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        data = self._post(
            f"{base}/chat/completions",
            headers,
            {"model": self.model, "max_tokens": max_tokens, "messages": messages},
        )
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"{self.provider}: tomt svar (inga choices)")
        return (choices[0].get("message") or {}).get("content") or ""

    def _google(self, messages: list, max_tokens: int) -> str:
        contents = [
            {"role": "model" if m["role"] == "assistant" else "user",
             "parts": [{"text": m["content"]}]}
            for m in messages if m["role"] != "system"
        ]
        payload: dict = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        base = self.endpoint or "https://generativelanguage.googleapis.com"
        data = self._post(
            f"{base}/v1beta/models/{self.model}:generateContent",
            {"x-goog-api-key": self._key or ""},  # header — aldrig ?key= i URL/loggar
            payload,
        )
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMError("google: tomt svar (inga candidates)")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts)
