"""Testes de caracterização: fixam o comportamento observado na v1-coupled.

Não dizem o que o sistema deveria fazer; dizem o que ele faz. Qualquer mudança
aqui é mudança de comportamento, não refatoração.

Na main, F2 e F3 mudaram de modo de entrega (streaming e assíncrono, ADR 0008).
Os testes delas foram atualizados para o contrato novo, mas o resultado continua
fixado pelos mesmos snapshots da v1-coupled: o texto e o relatório não mudaram.
A versão antiga da suíte segue nas tags v1-coupled e v2-decoupled.
"""
import pytest

from support import read_sse, run_report

ATRASO = "Meu pedido #481516 não chegou e já passou do prazo, urgente"
NOTA_E_PEDIDO = ("Tenho aqui a nota fiscal 530720. O produto veio quebrado na caixa, "
                 "pedido #605065. Sou cliente da loja há bastante tempo.")
PRODUTO_SEM_PEDIDO = ("Não consigo acompanhar o rastreio da entrega de o notebook 14 polegadas. "
                      "Fico no aguardo de uma solução.")
PRODUTO_E_PEDIDO = ("Recebi a cortina blackout e o aparelho não liga, pedido 687783. "
                    "Gostaria de saber como funciona o processo.")
COBRANCA = "Fui cobrado duas vezes no cartão pela mesma compra."


# F1 Classificar ticket

@pytest.mark.parametrize("ticket_id, text, category, priority", [
    ("TK-00042", ATRASO, "delivery", "high"),
    ("TK-00002", NOTA_E_PEDIDO, "product_defect", "medium"),
    ("TK-00100", COBRANCA, "payment", "high"),
])
def test_f1_classifica_ticket(client, ticket_id, text, category, priority):
    response = client.post("/tickets/classification", json={"ticket_id": ticket_id, "text": text})
    assert response.status_code == 200
    assert response.json() == {"ticket_id": ticket_id, "category": category, "priority": priority}


def test_f1_rejeita_ticket_sem_texto(client):
    response = client.post("/tickets/classification", json={"ticket_id": "TK-1"})
    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["type"] == "missing"
    assert error["loc"] == ["body", "text"]


# F2 Sugerir resposta

def test_f2_sugere_resposta_em_stream(client, snapshot):
    response, events = read_sse(client, "/tickets/reply-suggestion", {"ticket_id": "TK-00042", "text": ATRASO})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    chunks = [data["chunk"] for name, data in events[:-1]]
    assert len(chunks) > 1
    assert events[-1] == ("end", {"ticket_id": "TK-00042"})
    assert {"ticket_id": "TK-00042", "suggestion": "".join(chunks)} == snapshot("f2_suggestion_TK-00042.json")


def test_f2_rejeita_ticket_sem_id(client):
    response = client.post("/tickets/reply-suggestion", json={"text": ATRASO})
    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["type"] == "missing"
    assert error["loc"] == ["body", "ticket_id"]


# F3 Relatório de temas

def test_f3_relatorio_de_um_dia(client, snapshot):
    accepted, final = run_report(client, {"start": "2026-08-01", "end": "2026-08-01"})
    assert accepted.status_code == 202
    assert accepted.headers["location"].startswith("/reports/topics/status/")
    assert accepted.headers["retry-after"] == "5"
    assert final.status_code == 200
    assert final.json() == snapshot("f3_report_2026-08-01.json")


def test_f3_periodo_sem_tickets(client):
    accepted, final = run_report(client, {"start": "2026-09-01", "end": "2026-09-30"})
    assert accepted.status_code == 202
    assert final.json() == {"start": "2026-09-01", "end": "2026-09-30", "total_tickets": 0, "topics": []}


def test_f3_rejeita_periodo_invertido(client):
    response = client.post("/reports/topics", json={"start": "2026-08-31", "end": "2026-08-01"})
    assert response.status_code == 422
    assert response.json() == {"detail": "A data inicial é posterior à data final"}


def test_f3_rejeita_data_invalida(client):
    response = client.post("/reports/topics", json={"start": "2026-13-01", "end": "2026-08-01"})
    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "start"]


# F4 Extrair dados do pedido

@pytest.mark.parametrize("ticket_id, text, order_number, product", [
    ("TK-00002", NOTA_E_PEDIDO, "#605065", None),
    ("TK-00007", PRODUTO_SEM_PEDIDO, None, "notebook 14 polegadas"),
    ("TK-00030", PRODUTO_E_PEDIDO, "#687783", "cortina blackout"),
])
def test_f4_extrai_dados_do_pedido(client, ticket_id, text, order_number, product):
    response = client.post("/tickets/extraction", json={"ticket_id": ticket_id, "text": text})
    assert response.status_code == 200
    assert response.json() == {"ticket_id": ticket_id, "order_number": order_number, "product": product}


def test_f4_rejeita_texto_vazio(client):
    response = client.post("/tickets/extraction", json={"ticket_id": "TK-1", "text": ""})
    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["type"] == "string_too_short"
    assert error["loc"] == ["body", "text"]


# Saúde

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
