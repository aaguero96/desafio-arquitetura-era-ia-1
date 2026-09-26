import json
import os
from pathlib import Path

import httpx
import pytest

# A suíte fala com o helpdesk sempre pela borda, como o avaliador.
BASE_URL = os.environ.get("HELPDESK_URL", "http://localhost:8000")
PROVIDER_URL = os.environ.get("PROVIDER_URL", "http://localhost:8090")
SNAPSHOTS = Path(__file__).parent / "snapshots"


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=60) as http:
        yield http


@pytest.fixture(autouse=True)
def provider_normal():
    """Cada teste começa com o provider simulado no modo normal."""
    httpx.post(f"{PROVIDER_URL}/admin/reset", timeout=10).raise_for_status()


@pytest.fixture
def snapshot():
    def load(name: str):
        return json.loads((SNAPSHOTS / name).read_text(encoding="utf-8"))
    return load
