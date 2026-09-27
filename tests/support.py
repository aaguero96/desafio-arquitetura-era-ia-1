"""Helpers dos contratos novos da main: streaming (SSE) e Asynchronous Request-Reply."""
import json
import time

import httpx


def read_sse(client: httpx.Client, path: str, body: dict) -> tuple[httpx.Response, list[tuple[str, dict]]]:
    """Consome um stream SSE e devolve a resposta e os eventos (nome, dados)."""
    events, name = [], "message"
    with client.stream("POST", path, json=body) as response:
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            for line in response.iter_lines():
                if line.startswith("event:"):
                    name = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    events.append((name, json.loads(line[len("data:"):])))
                    name = "message"
        else:
            response.read()
    return response, events


def run_report(client: httpx.Client, period: dict, deadline: float = 240) -> tuple[httpx.Response, httpx.Response]:
    """Pede o relatório (202), acompanha o status até o 303 ou `failed` e devolve (aceite, final)."""
    accepted = client.post("/reports/topics", json=period)
    if accepted.status_code != 202:
        return accepted, accepted
    started = time.monotonic()
    while time.monotonic() - started < deadline:
        status = client.get(accepted.headers["location"], follow_redirects=False)
        if status.status_code == 303:
            return accepted, client.get(status.headers["location"])
        if status.json()["state"] == "failed":
            return accepted, status
        time.sleep(1)
    raise AssertionError(f"relatório não terminou em {deadline}s")
