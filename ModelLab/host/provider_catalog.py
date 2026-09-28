from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any




class ProviderRequestError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, category: str = "REQUEST_ERROR"):
        super().__init__(message)
        self.status_code = status_code
        self.category = category


def fallback_error_category(exc: BaseException) -> str | None:
    """Return a fallback-safe category, or None for non-fallback errors.

    Fallback is intentionally narrow: quota/rate limiting, timeout, provider 5xx,
    and model-unavailable/not-found. Authentication and malformed requests fail closed.
    """
    status=getattr(exc,"status_code",None)
    category=str(getattr(exc,"category","") or "").upper()
    text=str(exc).lower()
    # Authentication and malformed deterministic requests are hard failures even if a
    # provider error body happens to contain words such as "quota" or "rate limit".
    if status in {400,401,403,422}:
        return None
    if category=="CONNECTION":
        return "PROVIDER_UNREACHABLE"
    if status == 429 or any(x in text for x in ("quota", "rate limit", "resource_exhausted", "too many requests")):
        return "QUOTA_OR_RATE_LIMIT"
    if status in {408, 504} or any(x in text for x in ("timed out", "timeout")):
        return "TIMEOUT"
    if status is not None and 500 <= int(status) <= 599:
        return "PROVIDER_5XX"
    if status == 404 and "model" in text and any(x in text for x in ("not found", "unavailable", "does not exist", "unknown")):
        return "MODEL_UNAVAILABLE"
    if any(x in text for x in ("model unavailable", "model is unavailable", "model not found", "capacity", "overloaded")):
        return "MODEL_UNAVAILABLE"
    return None

@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    base_url: str
    needs_api_key: bool = True
    note: str = ""


PROVIDERS: dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        "gemini",
        "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        True,
        "OpenAI-compatible Gemini API",
    ),
    "openai": ProviderSpec(
        "openai", "OpenAI", "https://api.openai.com/v1/", True, "OpenAI API"
    ),
    "groq": ProviderSpec(
        "groq", "Groq", "https://api.groq.com/openai/v1/", True, "Groq OpenAI compatibility"
    ),
    "openrouter": ProviderSpec(
        "openrouter", "OpenRouter", "https://openrouter.ai/api/v1/", True, "OpenRouter"
    ),
    "deepseek": ProviderSpec(
        "deepseek", "DeepSeek", "https://api.deepseek.com/", True, "DeepSeek OpenAI-compatible API"
    ),
    "ollama": ProviderSpec(
        "ollama", "Ollama (Local)", "http://localhost:11434/v1/", False, "Local Ollama OpenAI compatibility"
    ),
    "custom": ProviderSpec(
        "custom", "Custom OpenAI-compatible", "", False, "Custom base URL"
    ),
}


def provider_labels() -> list[str]:
    return [p.label for p in PROVIDERS.values()]


def provider_key_from_label(label: str) -> str:
    for key, spec in PROVIDERS.items():
        if spec.label == label:
            return key
    return "custom"


def normalize_base_url(base_url: str) -> str:
    base = str(base_url or "").strip()
    if not base:
        return ""
    # Users often paste a full chat endpoint. Normalize it back to the API base.
    for suffix in ("/chat/completions", "/models"):
        if base.rstrip("/").endswith(suffix):
            base = base.rstrip("/")[: -len(suffix)]
            break
    return base.rstrip("/") + "/"


def chat_url(base_url: str) -> str:
    return normalize_base_url(base_url) + "chat/completions"


def models_url(base_url: str) -> str:
    return normalize_base_url(base_url) + "models"


def _headers(api_key: str | None) -> dict[str, str]:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key.strip()}"
    return h


def _json_request(url: str, api_key: str | None, *, method: str = "GET", payload: dict | None = None, timeout: int = 30) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=_headers(api_key), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1600]
        raise ProviderRequestError(f"HTTP {exc.code}: {detail or exc.reason}", status_code=int(exc.code), category="HTTP") from exc
    except urllib.error.URLError as exc:
        raise ProviderRequestError(f"Connection failed: {exc.reason}", category="CONNECTION") from exc
    except Exception as exc:
        raise ProviderRequestError(f"Request failed: {exc}", category="REQUEST") from exc


def _extract_model_ids(body: dict) -> list[str]:
    data = body.get("data")
    if isinstance(data, list):
        ids = []
        for row in data:
            if isinstance(row, dict) and row.get("id"):
                ids.append(str(row["id"]))
            elif isinstance(row, str):
                ids.append(row)
        return ids
    # Fallback for non-OpenAI local APIs, should a custom endpoint return Ollama-style tags.
    models = body.get("models")
    if isinstance(models, list):
        ids = []
        for row in models:
            if isinstance(row, dict):
                ident = row.get("name") or row.get("model") or row.get("id")
                if ident:
                    ids.append(str(ident))
            elif isinstance(row, str):
                ids.append(row)
        return ids
    return []


def is_probably_chat_model(model_id: str) -> bool:
    s = model_id.lower()
    blocked = (
        "embedding", "embed-", "text-embedding", "moderation", "omni-moderation",
        "imagen", "image-generation", "gpt-image", "veo", "lyria", "tts",
        "transcribe", "whisper", "speech", "rerank", "reranker",
    )
    return not any(token in s for token in blocked)


def list_models(base_url: str, api_key: str | None, *, timeout: int = 30, chat_only: bool = True) -> list[str]:
    base = normalize_base_url(base_url)
    if not base:
        raise ValueError("Base URL kosong")
    try:
        body = _json_request(models_url(base), api_key, timeout=timeout)
        ids = _extract_model_ids(body)
    except RuntimeError as first_error:
        # Ollama older builds may expose /api/tags rather than /v1/models.
        if "localhost:11434" in base or "127.0.0.1:11434" in base:
            root = base.split("/v1/")[0].rstrip("/")
            body = _json_request(root + "/api/tags", api_key, timeout=timeout)
            ids = _extract_model_ids(body)
        else:
            raise first_error
    ids = sorted(set(x.strip() for x in ids if str(x).strip()), key=str.lower)
    if chat_only:
        filtered = [x for x in ids if is_probably_chat_model(x)]
        if filtered:
            ids = filtered
    if not ids:
        raise RuntimeError("Provider tersambung, tetapi endpoint models tidak mengembalikan model yang dapat dipilih.")
    return ids


def chat_completion(base_url: str, model: str, api_key: str | None, messages: list[dict[str, Any]], *, temperature: float = 0.15, timeout: int = 60, max_tokens: int | None = None) -> dict:
    if not str(model or "").strip():
        raise ValueError("Model belum dipilih")
    payload = {
        "model": str(model).strip(),
        "messages": messages,
        "temperature": float(temperature),
    }
    if max_tokens is not None and int(max_tokens) > 0:
        payload["max_tokens"] = int(max_tokens)
    return _json_request(chat_url(base_url), api_key, method="POST", payload=payload, timeout=timeout)


def stream_chat_completion(base_url: str, model: str, api_key: str | None, messages: list[dict[str, Any]], *, temperature: float = 0.15, timeout: int = 60, max_tokens: int | None = None, on_delta=None) -> dict:
    """OpenAI-compatible SSE streaming with a deterministic buffered result.

    ``on_delta`` receives only user-visible text chunks. Hidden reasoning fields are
    intentionally ignored. If a compatibility endpoint does not expose SSE in the
    OpenAI shape, the caller may explicitly fall back to the non-streaming request
    on the *same model*; this function never changes routing/model authority.
    """
    if not str(model or "").strip():
        raise ValueError("Model belum dipilih")
    payload={
        "model":str(model).strip(),
        "messages":messages,
        "temperature":float(temperature),
        "stream":True,
        "stream_options":{"include_usage":True},
    }
    if max_tokens is not None and int(max_tokens)>0:
        payload["max_tokens"]=int(max_tokens)
    req=urllib.request.Request(chat_url(base_url),data=json.dumps(payload).encode("utf-8"),headers=_headers(api_key),method="POST")
    text_parts=[]; usage={}; saw_event=False
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            ctype=str(response.headers.get("Content-Type") or "").lower()
            # Some endpoints ignore stream=true and return one JSON body. Handle that
            # safely rather than pretending it was streamed.
            if "text/event-stream" not in ctype:
                raw=response.read().decode("utf-8")
                body=json.loads(raw)
                txt=extract_chat_text(body)
                if txt and on_delta: on_delta(txt)
                return body
            for raw_line in response:
                line=raw_line.decode("utf-8",errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                data=line[5:].strip()
                if data=="[DONE]":
                    break
                try:
                    event=json.loads(data)
                except Exception:
                    continue
                saw_event=True
                if isinstance(event.get("usage"),dict):
                    usage=dict(event.get("usage") or {})
                choices=event.get("choices") if isinstance(event,dict) else None
                if not isinstance(choices,list) or not choices:
                    continue
                delta=(choices[0] or {}).get("delta") if isinstance(choices[0],dict) else None
                content=(delta or {}).get("content") if isinstance(delta,dict) else None
                chunks=[]
                if isinstance(content,str):
                    chunks=[content]
                elif isinstance(content,list):
                    for part in content:
                        if isinstance(part,dict):
                            t=part.get("text") or part.get("content")
                            if t: chunks.append(str(t))
                        elif part is not None:
                            chunks.append(str(part))
                for chunk in chunks:
                    if not chunk: continue
                    text_parts.append(chunk)
                    if on_delta: on_delta(chunk)
    except urllib.error.HTTPError as exc:
        detail=exc.read().decode("utf-8",errors="replace")[:1600]
        raise ProviderRequestError(f"HTTP {exc.code}: {detail or exc.reason}",status_code=int(exc.code),category="HTTP") from exc
    except urllib.error.URLError as exc:
        raise ProviderRequestError(f"Connection failed: {exc.reason}",category="CONNECTION") from exc
    except ProviderRequestError:
        raise
    except Exception as exc:
        raise ProviderRequestError(f"Streaming request failed: {exc}",category="REQUEST") from exc
    if not saw_event:
        raise ProviderRequestError("Streaming endpoint returned no SSE events",category="STREAM_UNSUPPORTED")
    text="".join(text_parts)
    return {"choices":[{"message":{"content":text}}],"usage":usage}


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def estimate_token_count(text: str) -> int:
    """Tokenizer-agnostic fallback only. Provider-reported usage remains authority."""
    text=str(text or "")
    if not text:
        return 0
    # Four UTF-8 text characters/token is intentionally approximate and is always
    # labelled ESTIMATED in evidence/UI. It must never masquerade as provider usage.
    return max(1, (len(text) + 3) // 4)


def estimate_message_tokens(messages: list[dict[str, Any]]) -> int:
    chunks=[]
    for m in messages or []:
        if not isinstance(m,dict):
            chunks.append(str(m)); continue
        chunks.append(str(m.get("role") or ""))
        content=m.get("content")
        if isinstance(content,str): chunks.append(content)
        else: chunks.append(json.dumps(content,ensure_ascii=False,default=str))
    return estimate_token_count("\n".join(chunks))


def extract_token_usage(body: dict, *, messages: list[dict[str, Any]] | None = None, output_text: str = "") -> dict:
    """Normalize OpenAI-compatible/Gemini-style token telemetry.

    When the provider omits usage, return a clearly labelled tokenizer-agnostic
    estimate so the operator still has a planning signal. Cost calculations can
    therefore distinguish provider-reported from estimated token counts.
    """
    usage=body.get("usage") if isinstance(body,dict) and isinstance(body.get("usage"),dict) else {}
    input_tokens=_as_int(usage.get("prompt_tokens",usage.get("input_tokens")))
    output_tokens=_as_int(usage.get("completion_tokens",usage.get("output_tokens")))
    total_tokens=_as_int(usage.get("total_tokens"))
    pdet=usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"),dict) else {}
    cdet=usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"),dict) else {}
    cached_tokens=_as_int(pdet.get("cached_tokens",usage.get("cached_input_tokens")))
    reasoning_tokens=_as_int(cdet.get("reasoning_tokens",usage.get("reasoning_tokens")))
    reported=bool(usage and (input_tokens or output_tokens or total_tokens or "total_tokens" in usage))
    if not reported:
        input_tokens=estimate_message_tokens(messages or [])
        output_tokens=estimate_token_count(output_text)
        total_tokens=input_tokens+output_tokens
    elif total_tokens<=0:
        total_tokens=input_tokens+output_tokens
    return {
        "input_tokens":input_tokens,
        "output_tokens":output_tokens,
        "total_tokens":total_tokens,
        "cached_input_tokens":min(cached_tokens,input_tokens) if input_tokens else cached_tokens,
        "reasoning_tokens":reasoning_tokens,
        "source":"PROVIDER_REPORTED" if reported else "ESTIMATED",
    }


def estimate_api_cost_usd(usage: dict, pricing: dict | None) -> dict:
    """Estimate known successful-call API cost from configurable USD/1M rates."""
    pricing=pricing if isinstance(pricing,dict) else {}
    enabled=bool(pricing.get("enabled",False))
    if not enabled:
        return {"configured":False,"estimated_cost_usd":None,"currency":"USD"}
    inp=float(pricing.get("input",0.0) or 0.0)
    out=float(pricing.get("output",0.0) or 0.0)
    cached_rate=pricing.get("cached_input")
    cached_rate=inp if cached_rate is None else float(cached_rate or 0.0)
    in_tok=_as_int(usage.get("input_tokens")); out_tok=_as_int(usage.get("output_tokens")); cached=_as_int(usage.get("cached_input_tokens"))
    cached=min(cached,in_tok); uncached=max(0,in_tok-cached)
    cost=(uncached*inp + cached*cached_rate + out_tok*out)/1_000_000.0
    return {
        "configured":True,
        "estimated_cost_usd":float(cost),
        "currency":"USD",
        "rates_usd_per_1m":{"input":inp,"output":out,"cached_input":cached_rate},
    }


def extract_chat_text(body: dict) -> str:
    try:
        content = body["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError("Response tidak memiliki choices[0].message.content") from exc
    if isinstance(content, str):
        return content
    # Some compatibility layers may return structured content blocks.
    if isinstance(content, list):
        chunks = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if text:
                    chunks.append(str(text))
            elif part is not None:
                chunks.append(str(part))
        if chunks:
            return "\n".join(chunks)
    return str(content)
