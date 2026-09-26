"""Confere o script de métrica contra valores calculados à mão pela régua."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "metrics"))
import coupling  # noqa: E402

FILES = {
    "__init__.py": "",
    "ports.py": (
        "from typing import Protocol\n"
        "import abc\n"
        "class Model(Protocol):\n    def run(self) -> str: ...\n"
        "class Base(abc.ABC):\n    pass\n"
        "class Erro(Exception):\n    pass\n"
    ),
    "schemas.py": "from pydantic import BaseModel\nclass T(BaseModel):\n    x: int\n",
    "feature.py": "import json\nfrom .ports import Model\nfrom . import schemas\n",
    "adapters/__init__.py": "",
    "adapters/gateway.py": "from openai import OpenAI\nfrom ..ports import Erro\nfrom helpdesk import schemas\n",
    "main.py": "from helpdesk.adapters import gateway\nimport helpdesk.feature\n",
}


def test_regua(tmp_path):
    root = tmp_path / "helpdesk"
    for name, content in FILES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content, encoding="utf-8")

    rows = {r["component"]: r for r in coupling.measure(root)}

    assert set(rows) == {"ports", "schemas", "feature", "adapters.gateway", "main"}
    # ports: importado por feature e adapters.gateway; 2 de 3 classes abstratas
    assert rows["ports"] == {"component": "ports", "ca": 2, "ce": 0, "i": 0.0, "a": 0.67, "d": 0.33}
    assert rows["schemas"] == {"component": "schemas", "ca": 2, "ce": 0, "i": 0.0, "a": 0.0, "d": 1.0}
    assert rows["feature"] == {"component": "feature", "ca": 1, "ce": 2, "i": 0.67, "a": 0.0, "d": 0.33}
    assert rows["adapters.gateway"] == {"component": "adapters.gateway", "ca": 1, "ce": 2, "i": 0.67,
                                        "a": 0.0, "d": 0.33}
    assert rows["main"] == {"component": "main", "ca": 0, "ce": 2, "i": 1.0, "a": 0.0, "d": 0.0}
