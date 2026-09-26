"""Cria (ou atualiza) as chaves virtuais do gateway, sem passo manual.

Roda uma vez por subida do compose, no serviço gateway-init, depois que o
gateway fica saudável. É idempotente: se a chave já existe no banco, ela é
atualizada para o estado declarado em keys.json.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

GATEWAY = os.environ.get("GATEWAY_URL", "http://gateway:4000")
MASTER_KEY = os.environ["LITELLM_MASTER_KEY"]
KEYS_FILE = os.path.join(os.path.dirname(__file__), "keys.json")


def request(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{GATEWAY}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {MASTER_KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def wait_gateway() -> None:
    for _ in range(90):
        try:
            with urllib.request.urlopen(f"{GATEWAY}/health/liveliness", timeout=5):
                return
        except OSError:
            time.sleep(2)
    sys.exit("gateway não respondeu")


def main() -> None:
    wait_gateway()
    keys = json.load(open(KEYS_FILE, encoding="utf-8"))
    for spec in keys:
        # O valor da chave vem do ambiente (.env); o resto da política, do keys.json.
        body = {k: v for k, v in spec.items() if k != "key_env"}
        body["key"] = os.environ[spec["key_env"]]
        status, _ = request("GET", "/key/info?key=" + body["key"])
        if status == 200:
            status, answer = request("POST", "/key/update", body)
            action = "atualizada"
        else:
            status, answer = request("POST", "/key/generate", body)
            action = "criada"
        if status != 200:
            sys.exit(f"falha na chave {body.get('key_alias')}: {status} {answer}")
        print(f"chave {body['key_alias']} {action}", flush=True)


if __name__ == "__main__":
    main()
