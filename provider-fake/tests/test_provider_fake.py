"""Testes do provider-fake contra o container em execução.

Pré-requisito: `docker compose up -d` na raiz e `.env` copiado do `.env.example`.
Execução: pip install -r provider-fake/tests/requirements.txt && pytest provider-fake/tests -q
"""

import json
import os
import time

import anthropic
import httpx
import openai
import pytest

BASE = os.environ.get("FAKE_URL", "http://localhost:8090")
OPENAI_KEY = "sk-fake-openai-0001"
ANTHROPIC_KEY = "sk-ant-fake-0001"

TICKET = "Meu pedido #481516 não chegou e o prazo de entrega já passou. É urgente."
TICKET_TWO_NUMBERS = ("Tenho aqui a nota fiscal 530720. O mouse sem fio veio quebrado na caixa, "
                      "pedido #605065.")


def openai_client():
    return openai.OpenAI(base_url=f"{BASE}/openai/v1", api_key=OPENAI_KEY, max_retries=0)


def anthropic_client():
    return anthropic.Anthropic(base_url=f"{BASE}/anthropic", api_key=ANTHROPIC_KEY, max_retries=0)


def ask_openai(model, task, content, **kw):
    r = openai_client().chat.completions.create(
        model=model, messages=[{"role": "user", "content": f"TASK: {task}\n{content}"}], **kw)
    return r.choices[0].message.content, r


def ask_anthropic(model, task, content, max_tokens=2000, **kw):
    r = anthropic_client().messages.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": f"TASK: {task}\n{content}"}], **kw)
    return r.content[0].text, r


def admin(method, path, **kw):
    return httpx.request(method, f"{BASE}{path}", timeout=10, **kw)


def set_failure(**body):
    return admin("POST", "/admin/failures", json=body)


@pytest.fixture(autouse=True)
def reset():
    admin("POST", "/admin/reset")
    yield
    admin("POST", "/admin/reset")


# ---------- tarefas ----------

@pytest.mark.parametrize("model", ["gpt-fake-large", "gpt-fake-mini"])
def test_classify_openai(model):
    text, r = ask_openai(model, "classify", TICKET)
    assert json.loads(text) == {"category": "delivery", "priority": "high"}
    assert r.usage.prompt_tokens > 0 and r.usage.completion_tokens > 0


@pytest.mark.parametrize("model", ["claude-fake-large", "claude-fake-mini"])
def test_classify_anthropic(model):
    text, r = ask_anthropic(model, "classify", TICKET)
    assert json.loads(text) == {"category": "delivery", "priority": "high"}
    assert r.usage.input_tokens > 0 and r.usage.output_tokens > 0


def test_extract_large_is_right_and_mini_is_wrong():
    right, _ = ask_openai("gpt-fake-large", "extract", TICKET_TWO_NUMBERS)
    assert json.loads(right) == {"order_number": "#605065", "product": "mouse sem fio"}
    wrong, _ = ask_openai("gpt-fake-mini", "extract", TICKET_TWO_NUMBERS)
    assert json.loads(wrong) == {"order_number": "#530720", "product": None}
    wrong_a, _ = ask_anthropic("claude-fake-mini", "extract", TICKET_TWO_NUMBERS)
    assert json.loads(wrong_a) == {"order_number": "#530720", "product": None}


def test_extract_without_order():
    text, _ = ask_anthropic("claude-fake-large", "extract", "O cupom de desconto não funcionou.")
    assert json.loads(text) == {"order_number": None, "product": None}


def test_suggest_large_longer_than_mini():
    _, large = ask_anthropic("claude-fake-large", "suggest", TICKET)
    _, mini = ask_anthropic("claude-fake-mini", "suggest", TICKET)
    assert large.usage.output_tokens > 500
    assert 200 < mini.usage.output_tokens < 300


def test_topics_groups():
    lines = "\n".join([
        "[TK-00001] Meu pedido #111111 não chegou e a entrega está atrasada.",
        "[TK-00002] Fui cobrado duas vezes no cartão, cobrança duplicada.",
        "[TK-00003] A entrega do pedido 222222 está atrasada há vários dias.",
    ])
    text, _ = ask_openai("gpt-fake-large", "topics", lines)
    topics = json.loads(text)["topics"]
    assert topics[0] == {"topic": "Atraso na entrega", "count": 2, "examples": ["TK-00001", "TK-00003"]}
    assert {"topic": "Cobrança duplicada", "count": 1, "examples": ["TK-00002"]} in topics


def test_topics_whole_month_exceeds_context_and_batch_fits():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "tickets.jsonl")
    tickets = [json.loads(line) for line in open(path, encoding="utf-8")]
    everything = "\n".join(f"[{t['id']}] {t['text']}" for t in tickets)
    with pytest.raises(openai.BadRequestError) as error:
        ask_openai("gpt-fake-large", "topics", everything)
    assert error.value.code == "context_length_exceeded"
    with pytest.raises(anthropic.BadRequestError):
        ask_anthropic("claude-fake-large", "topics", everything)
    batch = "\n".join(f"[{t['id']}] {t['text']}" for t in tickets[:100])
    text, _ = ask_openai("gpt-fake-mini", "topics", batch)
    assert sum(t["count"] for t in json.loads(text)["topics"]) == 100


def test_without_task_answers_fallback_text():
    r = openai_client().chat.completions.create(
        model="gpt-fake-mini", messages=[{"role": "user", "content": "oi"}])
    assert "Tarefa não reconhecida" in r.choices[0].message.content


def test_anthropic_system_and_blocks():
    r = anthropic_client().messages.create(
        model="claude-fake-mini", max_tokens=100,
        system=[{"type": "text", "text": "Você é um classificador."}],
        messages=[{"role": "user", "content": [{"type": "text", "text": f"TASK: classify\n{TICKET}"}]}])
    assert json.loads(r.content[0].text)["category"] == "delivery"


def test_determinism():
    a, _ = ask_openai("gpt-fake-mini", "suggest", TICKET)
    b, _ = ask_openai("gpt-fake-mini", "suggest", TICKET)
    assert a == b


# ---------- streaming ----------

def test_stream_openai():
    stream = openai_client().chat.completions.create(
        model="gpt-fake-mini", stream=True, stream_options={"include_usage": True},
        messages=[{"role": "user", "content": f"TASK: suggest\n{TICKET}"}])
    parts, usage, finish = [], None, None
    for c in stream:
        if c.usage:
            usage = c.usage
        for choice in c.choices:
            if choice.delta.content:
                parts.append(choice.delta.content)
            if choice.finish_reason:
                finish = choice.finish_reason
    full, _ = ask_openai("gpt-fake-mini", "suggest", TICKET)
    assert "".join(parts) == full
    assert finish == "stop" and usage.completion_tokens > 0


def test_stream_anthropic():
    with anthropic_client().messages.stream(
            model="claude-fake-mini", max_tokens=2000,
            messages=[{"role": "user", "content": f"TASK: suggest\n{TICKET}"}]) as s:
        text = "".join(s.text_stream)
        final = s.get_final_message()
    full, _ = ask_anthropic("claude-fake-mini", "suggest", TICKET)
    assert text == full
    assert final.stop_reason == "end_turn" and final.usage.output_tokens > 0


def test_stream_ttft_lower_than_total():
    start = time.monotonic()
    stream = anthropic_client().messages.create(
        model="claude-fake-large", max_tokens=2000, stream=True,
        messages=[{"role": "user", "content": f"TASK: suggest\n{TICKET}"}])
    ttft = None
    for event in stream:
        if event.type == "content_block_delta" and ttft is None:
            ttft = time.monotonic() - start
    total = time.monotonic() - start
    assert ttft < 1.5
    assert total > 10


# ---------- limites e erros ----------

def test_max_tokens_truncates():
    _, r = ask_openai("gpt-fake-mini", "suggest", TICKET, max_tokens=20)
    assert r.choices[0].finish_reason == "length" and r.usage.completion_tokens <= 20
    _, ra = ask_anthropic("claude-fake-mini", "suggest", TICKET, max_tokens=20)
    assert ra.stop_reason == "max_tokens"


def test_invalid_key():
    with pytest.raises(openai.AuthenticationError):
        openai.OpenAI(base_url=f"{BASE}/openai/v1", api_key="wrong", max_retries=0) \
            .chat.completions.create(model="gpt-fake-mini", messages=[{"role": "user", "content": "x"}])
    with pytest.raises(anthropic.AuthenticationError):
        anthropic.Anthropic(base_url=f"{BASE}/anthropic", api_key="wrong", max_retries=0) \
            .messages.create(model="claude-fake-mini", max_tokens=10, messages=[{"role": "user", "content": "x"}])


def test_model_from_other_provider():
    with pytest.raises(openai.NotFoundError):
        ask_openai("claude-fake-large", "classify", TICKET)


def test_anthropic_requires_max_tokens():
    r = httpx.post(f"{BASE}/anthropic/v1/messages", headers={"x-api-key": ANTHROPIC_KEY},
                   json={"model": "claude-fake-mini", "messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 400


# ---------- modos de falha e registro ----------

def test_error_500_on_model_does_not_affect_the_other():
    set_failure(provider="openai", model="gpt-fake-large", mode="error_500")
    with pytest.raises(openai.InternalServerError):
        ask_openai("gpt-fake-large", "classify", TICKET)
    text, _ = ask_openai("gpt-fake-mini", "classify", TICKET)
    assert json.loads(text)["category"] == "delivery"


def test_error_500_whole_provider_and_model_override():
    set_failure(provider="anthropic", mode="error_500")
    with pytest.raises(anthropic.InternalServerError):
        ask_anthropic("claude-fake-mini", "classify", TICKET)
    set_failure(provider="anthropic", model="claude-fake-mini", mode="normal")
    text, _ = ask_anthropic("claude-fake-mini", "classify", TICKET)
    assert json.loads(text)["category"] == "delivery"


def test_error_429_with_retry_after():
    set_failure(provider="openai", mode="error_429")
    r = httpx.post(f"{BASE}/openai/v1/chat/completions", headers={"Authorization": f"Bearer {OPENAI_KEY}"},
                   json={"model": "gpt-fake-mini", "messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 429 and r.headers["retry-after"] == "2"


def test_timeout_holds_the_connection():
    set_failure(provider="openai", mode="timeout")
    start = time.monotonic()
    with pytest.raises(httpx.ReadTimeout):
        httpx.post(f"{BASE}/openai/v1/chat/completions", headers={"Authorization": f"Bearer {OPENAI_KEY}"},
                   json={"model": "gpt-fake-mini", "messages": [{"role": "user", "content": "x"}]}, timeout=3)
    assert time.monotonic() - start >= 3
    entry = admin("GET", "/admin/calls").json()[0]
    assert entry["status"] == 504 and entry["duration_ms"] is None


def test_midstream_error_openai():
    set_failure(provider="openai", mode="midstream_error")
    stream = openai_client().chat.completions.create(
        model="gpt-fake-mini", stream=True, messages=[{"role": "user", "content": f"TASK: suggest\n{TICKET}"}])
    received = []
    with pytest.raises(openai.APIError):
        for c in stream:
            if c.choices and c.choices[0].delta.content:
                received.append(c.choices[0].delta.content)
    assert received
    assert admin("GET", "/admin/calls").json()[0]["status"] == 500
    with pytest.raises(openai.InternalServerError):
        ask_openai("gpt-fake-mini", "classify", TICKET)


def test_midstream_error_anthropic():
    set_failure(provider="anthropic", mode="midstream_error")
    received = []
    with pytest.raises(anthropic.APIError):
        with anthropic_client().messages.stream(
                model="claude-fake-mini", max_tokens=2000,
                messages=[{"role": "user", "content": f"TASK: suggest\n{TICKET}"}]) as s:
            for text in s.text_stream:
                received.append(text)
    assert received
    assert admin("GET", "/admin/calls").json()[0]["status"] == 500


def test_slow_multiplies_latency():
    start = time.monotonic()
    ask_openai("gpt-fake-mini", "classify", TICKET)
    normal_time = time.monotonic() - start
    set_failure(provider="openai", mode="slow")
    start = time.monotonic()
    ask_openai("gpt-fake-mini", "classify", TICKET)
    slow_time = time.monotonic() - start
    assert slow_time > normal_time * 5


def test_call_log():
    ask_openai("gpt-fake-mini", "classify", TICKET)
    set_failure(provider="anthropic", mode="error_500")
    with pytest.raises(anthropic.InternalServerError):
        ask_anthropic("claude-fake-large", "extract", TICKET)
    entries = admin("GET", "/admin/calls").json()
    assert len(entries) == 2
    last, first = entries
    assert last["provider"] == "anthropic" and last["model"] == "claude-fake-large"
    assert last["task"] == "extract" and last["status"] == 500
    assert first["provider"] == "openai" and first["status"] == 200
    assert first["task"] == "classify" and first["output_tokens"] > 0
    assert first["duration_ms"] >= 300


def test_admin_validates_input():
    assert set_failure(provider="x", mode="error_500").status_code == 400
    assert set_failure(provider="openai", mode="break").status_code == 400
    assert set_failure(provider="openai", model="claude-fake-mini", mode="error_500").status_code == 400
