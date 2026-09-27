"""Critérios de aceite da main, medidos pela borda e conferidos no /admin/calls.

Os números (tentativas por destino, status, prazos) são os declarados no README
(tabelas de capacidades e de fallback) e nos ADRs 0005 e 0008.
"""
import time

import pytest

from support import read_sse, run_report

TICKET = {"ticket_id": "TK-00042", "text": "Meu pedido #481516 não chegou e já passou do prazo, urgente"}
ONE_DAY = {"start": "2026-08-01", "end": "2026-08-01"}
MAX_ATTEMPTS = 3  # por destino: 1 tentativa + 2 retries (README, tabela de capacidades)


def down_both_large(fail):
    fail("openai", "error_500", "gpt-fake-large")
    fail("anthropic", "error_500", "claude-fake-large")


# Fluxos no modo normal

def test_f1_responde_em_ate_3s(client):
    started = time.perf_counter()
    response = client.post("/tickets/classification", json=TICKET)
    assert response.status_code == 200
    assert time.perf_counter() - started < 3


def test_f2_primeiro_trecho_em_ate_1s5_e_antes_da_metade(client):
    started = time.perf_counter()
    first = None
    with client.stream("POST", "/tickets/reply-suggestion", json=TICKET) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if first is None and line.startswith("data:") and '"chunk"' in line:
                first = time.perf_counter() - started
    total = time.perf_counter() - started
    assert first < 1.5
    assert first < total / 2


def test_f3_aceita_mes_em_ate_1s_e_entrega_5000(client, calls):
    started = time.perf_counter()
    accepted = client.post("/reports/topics", json={"start": "2026-08-01", "end": "2026-08-31"})
    assert time.perf_counter() - started < 1
    assert accepted.status_code == 202
    assert {"location", "retry-after"} <= set(accepted.headers)

    status = client.get(accepted.headers["location"], follow_redirects=False)
    assert status.status_code == 200 and status.json()["state"] in {"pending", "running"}

    deadline = time.monotonic() + 300
    while status.status_code == 200 and time.monotonic() < deadline:
        assert status.json()["state"] != "failed", status.json()
        time.sleep(2)
        status = client.get(accepted.headers["location"], follow_redirects=False)
    assert status.status_code == 303
    report = client.get(status.headers["location"]).json()
    assert report["total_tickets"] == 5000
    assert len(calls("topics")) == 34  # 5000 tickets em lotes de 150


# Fallback técnico: primário em error_500

@pytest.mark.parametrize("path, task, primary, alternative", [
    ("/tickets/classification", "classify", ("openai", "gpt-fake-large"), ("anthropic", "claude-fake-large")),
    ("/tickets/extraction", "extract", ("openai", "gpt-fake-large"), ("anthropic", "claude-fake-large")),
])
def test_primario_em_500_cai_no_outro_provider(client, fail, calls, path, task, primary, alternative):
    fail(primary[0], "error_500", primary[1])
    assert client.post(path, json=TICKET).status_code == 200
    made = calls(task)
    assert 1 <= len(made) - 1 <= MAX_ATTEMPTS
    assert all(c == (*primary, 500) for c in made[:-1])
    assert made[-1] == (*alternative, 200)


def test_f2_primario_em_500_cai_no_outro_provider(client, fail, calls):
    fail("anthropic", "error_500", "claude-fake-large")
    response, events = read_sse(client, "/tickets/reply-suggestion", TICKET)
    assert events[-1][0] == "end"
    made = calls("suggest")
    assert made[-1] == ("openai", "gpt-fake-large", 200)
    assert len(made) - 1 <= MAX_ATTEMPTS


def test_f3_primario_em_500_cai_no_outro_provider(client, fail, calls):
    fail("anthropic", "error_500", "claude-fake-large")
    accepted, final = run_report(client, ONE_DAY)
    assert final.status_code == 200
    made = calls("topics")
    assert made[-1] == ("openai", "gpt-fake-large", 200)
    assert len(made) - 1 <= MAX_ATTEMPTS


# Os dois large fora: tabela de fallback do README

def test_sem_large_f1_responde_com_mini(client, fail, calls):
    down_both_large(fail)
    response = client.post("/tickets/classification", json=TICKET)
    assert response.status_code == 200
    assert calls("classify")[-1] == ("openai", "gpt-fake-mini", 200)


def test_sem_large_f2_responde_com_mini(client, fail, calls):
    down_both_large(fail)
    response, events = read_sse(client, "/tickets/reply-suggestion", TICKET)
    assert response.status_code == 200 and events[-1][0] == "end"
    assert calls("suggest")[-1] == ("anthropic", "claude-fake-mini", 200)


def test_sem_large_f3_responde_com_mini(client, fail, calls):
    down_both_large(fail)
    accepted, final = run_report(client, ONE_DAY)
    assert final.status_code == 200 and final.json()["total_tickets"] == 137
    assert calls("topics")[-1] == ("anthropic", "claude-fake-mini", 200)


def test_sem_large_f4_falha_explicitamente_sem_tocar_no_mini(client, fail, calls):
    down_both_large(fail)
    response = client.post("/tickets/extraction", json=TICKET)
    assert response.status_code == 503
    assert response.json() == {"detail": "Modelo indisponível no momento; tente novamente."}
    assert all("mini" not in model for _, model, _ in calls("extract"))


# Falhas que travam ou interrompem

def test_f1_com_primario_travado_responde_em_ate_15s(client, fail):
    fail("openai", "timeout")
    started = time.perf_counter()
    response = client.post("/tickets/classification", json=TICKET)
    assert response.status_code in {200, 503}
    assert time.perf_counter() - started < 15


def test_f2_erro_no_meio_do_stream_vira_evento_error(client, fail):
    fail("anthropic", "midstream_error", "claude-fake-large")
    response, events = read_sse(client, "/tickets/reply-suggestion", TICKET)
    assert response.status_code == 200
    assert events[0][0] == "message"  # parte do texto chegou antes da falha
    assert events[-1] == ("error", {"ticket_id": "TK-00042", "message": "A geração foi interrompida"})


def test_f3_com_os_dois_providers_fora_falha_com_motivo_em_ate_60s(client, fail):
    fail("openai", "error_500")
    fail("anthropic", "error_500")
    started = time.perf_counter()
    accepted, final = run_report(client, {"start": "2026-08-01", "end": "2026-08-31"}, deadline=60)
    assert time.perf_counter() - started < 60
    assert final.status_code == 200
    assert final.json()["state"] == "failed"
    assert final.json()["reason"]
