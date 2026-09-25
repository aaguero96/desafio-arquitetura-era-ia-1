"""Provider simulado: imita a API Chat Completions (OpenAI) e a API Messages (Anthropic)."""

import asyncio
import json
import math
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import tasks

MODELS = {
    "gpt-fake-large": {"provider": "openai", "size": "large", "context": 8000,
                       "ttft": 0.8, "tokens_per_s": 40, "input_price": 2.50, "output_price": 10.00},
    "gpt-fake-mini": {"provider": "openai", "size": "mini", "context": 8000,
                      "ttft": 0.3, "tokens_per_s": 150, "input_price": 0.15, "output_price": 0.60},
    "claude-fake-large": {"provider": "anthropic", "size": "large", "context": 8000,
                          "ttft": 0.8, "tokens_per_s": 40, "input_price": 3.00, "output_price": 15.00},
    "claude-fake-mini": {"provider": "anthropic", "size": "mini", "context": 8000,
                         "ttft": 0.3, "tokens_per_s": 150, "input_price": 0.80, "output_price": 4.00},
}
PROVIDERS = ("openai", "anthropic")
MODES = ("normal", "error_500", "error_429", "timeout", "slow", "midstream_error")
ERROR_STATUS = {"error_500": 500, "error_429": 429, "timeout": 504}
# Em streaming, envia só esta fração da resposta e interrompe com um evento de erro.
MIDSTREAM_FRACTION = 0.25
SLOW_FACTOR = 10
TIMEOUT_SECONDS = 300

KEYS = {
    "openai": os.environ.get("FAKE_OPENAI_KEY", ""),
    "anthropic": os.environ.get("FAKE_ANTHROPIC_KEY", ""),
}

provider_failures: dict[str, str] = {}
model_failures: dict[str, str] = {}
calls: deque = deque(maxlen=5000)

app = FastAPI(title="provider-fake", docs_url=None, redoc_url=None)


# ---------- utilidades ----------

def count_tokens(text: str) -> int:
    return math.ceil(len(text) / 4) if text else 0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def mode_for(provider: str, model: str) -> str:
    if model in model_failures:
        return model_failures[model]
    return provider_failures.get(provider, "normal")


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def record_call(provider: str, model: str | None, stream: bool) -> dict:
    entry = {
        "id": uuid.uuid4().hex[:12],
        "ts": now_iso(),
        "provider": provider,
        "model": model,
        "task": None,
        "stream": stream,
        "status": None,
        "input_tokens": None,
        "output_tokens": None,
        "duration_ms": None,
    }
    entry["_start"] = time.monotonic()
    calls.append(entry)
    return entry


def finish_call(entry: dict, status: int | None = None) -> None:
    if status is not None:
        entry["status"] = status
    entry["duration_ms"] = round((time.monotonic() - entry["_start"]) * 1000)


def chunks_of(text: str) -> list[str]:
    """Quebra o texto em pedaços de até ~4 caracteres, preservando espaços."""
    return [text[i:i + 4] for i in range(0, len(text), 4)]


def truncate(text: str, limit: int | None) -> tuple[str, bool]:
    if limit is not None and count_tokens(text) > limit:
        return text[: limit * 4], True
    return text, False


# ---------- erros no formato de cada provider ----------

def openai_error(status: int, message: str, kind: str, code: str | None = None, headers=None):
    body = {"error": {"message": message, "type": kind, "param": None, "code": code}}
    return JSONResponse(body, status_code=status, headers=headers)


def anthropic_error(status: int, message: str, kind: str, headers=None):
    body = {"type": "error", "error": {"type": kind, "message": message}}
    return JSONResponse(body, status_code=status, headers=headers)


async def apply_failure(mode: str, api: str):
    """Devolve uma resposta de erro se o modo configurado exigir, ou None."""
    if mode in ("error_500", "midstream_error"):
        if api == "openai":
            return openai_error(500, "Falha simulada no provider.", "server_error")
        return anthropic_error(500, "Falha simulada no provider.", "api_error")
    if mode == "error_429":
        headers = {"Retry-After": "2"}
        if api == "openai":
            return openai_error(429, "Limite de requisições simulado.", "requests", "rate_limit_exceeded", headers)
        return anthropic_error(429, "Limite de requisições simulado.", "rate_limit_error", headers)
    if mode == "timeout":
        await asyncio.sleep(TIMEOUT_SECONDS)
        if api == "openai":
            return openai_error(504, "Timeout simulado no provider.", "server_error")
        return anthropic_error(504, "Timeout simulado no provider.", "api_error")
    return None


# ---------- geração comum ----------

class Generation:
    def __init__(self, model: str, input_text: str, user_text: str, max_tokens: int | None, mode: str):
        self.profile = MODELS[model]
        self.task, content = tasks.detect(user_text)
        full = tasks.generate(self.task, content, self.profile["size"])
        self.text, self.truncated = truncate(full, max_tokens)
        self.input_tokens = count_tokens(input_text)
        self.output_tokens = count_tokens(self.text)
        factor = SLOW_FACTOR if mode == "slow" else 1
        self.ttft = self.profile["ttft"] * factor
        self.token_interval = factor / self.profile["tokens_per_s"]

    def exceeds_context(self) -> bool:
        return self.input_tokens > self.profile["context"]

    async def wait_full(self) -> None:
        await asyncio.sleep(self.ttft + self.output_tokens * self.token_interval)

    async def stream(self, fraction: float = 1.0):
        await asyncio.sleep(self.ttft)
        pieces = chunks_of(self.text)
        for chunk in pieces[: max(1, int(len(pieces) * fraction))]:
            yield chunk
            await asyncio.sleep(count_tokens(chunk) * self.token_interval)


# ---------- saúde ----------

@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------- OpenAI: Chat Completions ----------

def openai_authorized(request: Request) -> bool:
    auth = request.headers.get("authorization", "")
    return bool(KEYS["openai"]) and auth == f"Bearer {KEYS['openai']}"


@app.get("/openai/v1/models")
async def openai_models(request: Request):
    if not openai_authorized(request):
        return openai_error(401, "Chave de API inválida.", "invalid_request_error", "invalid_api_key")
    data = [{"id": m, "object": "model", "created": 0, "owned_by": "provider-fake"}
            for m, p in MODELS.items() if p["provider"] == "openai"]
    return {"object": "list", "data": data}


@app.post("/openai/v1/chat/completions")
async def openai_chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    model = body.get("model")
    stream = bool(body.get("stream"))
    entry = record_call("openai", model, stream)

    if not openai_authorized(request):
        finish_call(entry, 401)
        return openai_error(401, "Chave de API inválida.", "invalid_request_error", "invalid_api_key")
    if model not in MODELS or MODELS[model]["provider"] != "openai":
        finish_call(entry, 404)
        return openai_error(404, f"O modelo '{model}' não existe.", "invalid_request_error", "model_not_found")

    messages = body.get("messages") or []
    texts = [text_of(m.get("content")) for m in messages]
    user_text = next((text_of(m.get("content")) for m in reversed(messages) if m.get("role") == "user"), "")
    max_tokens = body.get("max_completion_tokens") or body.get("max_tokens")
    mode = mode_for("openai", model)
    gen = Generation(model, "\n".join(texts), user_text, max_tokens, mode)
    entry["task"] = gen.task
    entry["input_tokens"] = gen.input_tokens

    midstream = mode == "midstream_error" and stream
    if mode in ERROR_STATUS or (mode == "midstream_error" and not stream):
        entry["status"] = ERROR_STATUS.get(mode, 500)
        response = await apply_failure(mode, "openai")
        finish_call(entry)
        return response

    if gen.exceeds_context():
        finish_call(entry, 400)
        return openai_error(
            400,
            f"A entrada tem {gen.input_tokens} tokens e o contexto máximo do modelo é "
            f"{gen.profile['context']} tokens.",
            "invalid_request_error", "context_length_exceeded",
        )

    ident = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    finish_reason = "length" if gen.truncated else "stop"
    usage = {"prompt_tokens": gen.input_tokens, "completion_tokens": gen.output_tokens,
             "total_tokens": gen.input_tokens + gen.output_tokens}

    if not stream:
        await gen.wait_full()
        entry["output_tokens"] = gen.output_tokens
        finish_call(entry, 200)
        return {
            "id": ident, "object": "chat.completion", "created": created, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": gen.text, "refusal": None},
                         "logprobs": None, "finish_reason": finish_reason}],
            "usage": usage,
        }

    include_usage = bool((body.get("stream_options") or {}).get("include_usage"))
    entry["status"] = 200

    def chunk(delta: dict, reason: str | None = None) -> str:
        data = {"id": ident, "object": "chat.completion.chunk", "created": created, "model": model,
                "choices": [{"index": 0, "delta": delta, "logprobs": None, "finish_reason": reason}]}
        if include_usage:
            data["usage"] = None
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def events():
        try:
            first = True
            async for piece in gen.stream(MIDSTREAM_FRACTION if midstream else 1.0):
                if first:
                    yield chunk({"role": "assistant", "content": ""})
                    first = False
                yield chunk({"content": piece})
            if midstream:
                entry["status"] = 500
                error = {"error": {"message": "Falha simulada no meio do stream.", "type": "server_error",
                                   "param": None, "code": None}}
                yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
                return
            if first:
                yield chunk({"role": "assistant", "content": ""})
            yield chunk({}, finish_reason)
            if include_usage:
                data = {"id": ident, "object": "chat.completion.chunk", "created": created,
                        "model": model, "choices": [], "usage": usage}
                yield f"data: {json.dumps(data)}\n\n"
            yield "data: [DONE]\n\n"
            entry["output_tokens"] = gen.output_tokens
        finally:
            finish_call(entry)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---------- Anthropic: Messages ----------

def anthropic_authorized(request: Request) -> bool:
    key = request.headers.get("x-api-key") or ""
    auth = request.headers.get("authorization", "")
    if not key and auth.lower().startswith("bearer "):
        key = auth[7:]
    return bool(KEYS["anthropic"]) and key == KEYS["anthropic"]


@app.get("/anthropic/v1/models")
async def anthropic_models(request: Request):
    if not anthropic_authorized(request):
        return anthropic_error(401, "Chave de API inválida.", "authentication_error")
    data = [{"type": "model", "id": m, "display_name": m, "created_at": "2026-01-01T00:00:00Z"}
            for m, p in MODELS.items() if p["provider"] == "anthropic"]
    return {"data": data, "has_more": False, "first_id": data[0]["id"], "last_id": data[-1]["id"]}


def anthropic_sse(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/anthropic/v1/messages")
async def anthropic_messages(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    model = body.get("model")
    stream = bool(body.get("stream"))
    entry = record_call("anthropic", model, stream)

    if not anthropic_authorized(request):
        finish_call(entry, 401)
        return anthropic_error(401, "Chave de API inválida.", "authentication_error")
    if model not in MODELS or MODELS[model]["provider"] != "anthropic":
        finish_call(entry, 404)
        return anthropic_error(404, f"model: {model}", "not_found_error")
    max_tokens = body.get("max_tokens")
    if not isinstance(max_tokens, int) or max_tokens < 1:
        finish_call(entry, 400)
        return anthropic_error(400, "max_tokens: campo obrigatório.", "invalid_request_error")

    messages = body.get("messages") or []
    system = text_of(body.get("system") or "")
    texts = [system] + [text_of(m.get("content")) for m in messages]
    user_text = next((text_of(m.get("content")) for m in reversed(messages) if m.get("role") == "user"), "")
    mode = mode_for("anthropic", model)
    gen = Generation(model, "\n".join(t for t in texts if t), user_text, max_tokens, mode)
    entry["task"] = gen.task
    entry["input_tokens"] = gen.input_tokens

    midstream = mode == "midstream_error" and stream
    if mode in ERROR_STATUS or (mode == "midstream_error" and not stream):
        entry["status"] = ERROR_STATUS.get(mode, 500)
        response = await apply_failure(mode, "anthropic")
        finish_call(entry)
        return response

    if gen.exceeds_context():
        finish_call(entry, 400)
        return anthropic_error(
            400,
            f"prompt is too long: {gen.input_tokens} tokens > {gen.profile['context']} maximum",
            "invalid_request_error",
        )

    ident = f"msg_{uuid.uuid4().hex[:24]}"
    stop_reason = "max_tokens" if gen.truncated else "end_turn"

    if not stream:
        await gen.wait_full()
        entry["output_tokens"] = gen.output_tokens
        finish_call(entry, 200)
        return {
            "id": ident, "type": "message", "role": "assistant", "model": model,
            "content": [{"type": "text", "text": gen.text}],
            "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": gen.input_tokens, "output_tokens": gen.output_tokens},
        }

    entry["status"] = 200

    async def events():
        try:
            yield anthropic_sse("message_start", {
                "type": "message_start",
                "message": {"id": ident, "type": "message", "role": "assistant", "model": model,
                            "content": [], "stop_reason": None, "stop_sequence": None,
                            "usage": {"input_tokens": gen.input_tokens, "output_tokens": 1}},
            })
            yield anthropic_sse("content_block_start", {
                "type": "content_block_start", "index": 0,
                "content_block": {"type": "text", "text": ""},
            })
            async for piece in gen.stream(MIDSTREAM_FRACTION if midstream else 1.0):
                yield anthropic_sse("content_block_delta", {
                    "type": "content_block_delta", "index": 0,
                    "delta": {"type": "text_delta", "text": piece},
                })
            if midstream:
                entry["status"] = 500
                yield anthropic_sse("error", {"type": "error", "error": {
                    "type": "api_error", "message": "Falha simulada no meio do stream."}})
                return
            yield anthropic_sse("content_block_stop", {"type": "content_block_stop", "index": 0})
            yield anthropic_sse("message_delta", {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": gen.output_tokens},
            })
            yield anthropic_sse("message_stop", {"type": "message_stop"})
            entry["output_tokens"] = gen.output_tokens
        finally:
            finish_call(entry)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---------- administração ----------

@app.post("/admin/failures")
async def admin_set_failure(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "corpo JSON inválido"}, status_code=400)
    provider = body.get("provider")
    model = body.get("model")
    mode = body.get("mode")
    if provider not in PROVIDERS:
        return JSONResponse({"error": f"provider deve ser um de {list(PROVIDERS)}"}, status_code=400)
    if mode not in MODES:
        return JSONResponse({"error": f"mode deve ser um de {list(MODES)}"}, status_code=400)
    if model is not None:
        if model not in MODELS or MODELS[model]["provider"] != provider:
            return JSONResponse({"error": f"o modelo '{model}' não pertence ao provider '{provider}'"},
                                status_code=400)
        model_failures[model] = mode
    else:
        provider_failures[provider] = mode
    return await admin_get_failures()


@app.get("/admin/failures")
async def admin_get_failures():
    effective = {m: mode_for(p["provider"], m) for m, p in MODELS.items()}
    return {"providers": {p: provider_failures.get(p, "normal") for p in PROVIDERS},
            "models": dict(model_failures), "effective_by_model": effective}


@app.get("/admin/calls")
async def admin_calls(last: int = 50):
    last = max(1, min(last, calls.maxlen))
    recent = list(calls)[-last:]
    recent.reverse()
    return [{k: v for k, v in e.items() if not k.startswith("_")} for e in recent]


@app.post("/admin/reset")
async def admin_reset():
    provider_failures.clear()
    model_failures.clear()
    calls.clear()
    return {"status": "ok"}
