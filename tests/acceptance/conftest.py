import os

import httpx
import pytest

BASE_URL = os.environ.get("HELPDESK_URL", "http://localhost:8000")
PROVIDER_URL = os.environ.get("PROVIDER_URL", "http://localhost:8090")


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=90) as http:
        http.get("/health")  # aquece a conexão: as medições de tempo não pagam o handshake
        yield http


@pytest.fixture(scope="session")
def admin():
    with httpx.Client(base_url=PROVIDER_URL, timeout=10) as http:
        yield http


@pytest.fixture(autouse=True)
def provider_normal(admin):
    admin.post("/admin/reset").raise_for_status()
    yield
    admin.post("/admin/reset").raise_for_status()


@pytest.fixture
def fail(admin):
    def set_mode(provider: str, mode: str, model: str | None = None) -> None:
        body = {"provider": provider, "mode": mode} | ({"model": model} if model else {})
        admin.post("/admin/failures", json=body).raise_for_status()
    return set_mode


@pytest.fixture
def calls(admin):
    """Chamadas registradas no provider, da mais antiga para a mais recente."""
    def read(task: str | None = None) -> list[tuple[str, str, int]]:
        items = reversed(admin.get("/admin/calls", params={"last": 5000}).json())
        return [(c["provider"], c["model"], c["status"]) for c in items if task in (None, c["task"])]
    return read
