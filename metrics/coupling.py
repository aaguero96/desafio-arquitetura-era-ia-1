"""Mede acoplamento (Ca, Ce, I, A, D) por componente e desenha a Main Sequence.

Uso:
    python metrics/coupling.py <pasta app/helpdesk> <nome>

Grava metrics/results/<nome>.csv e metrics/results/<nome>.png.

Régua (requisito 3 do enunciado, fixa):
- componente: cada módulo .py da pasta, incluindo subpastas, exceto __init__.py,
  identificado pelo caminho com pontos (ex.: adapters.gateway);
- dependência: import, relativo ou absoluto, que resolve para outro componente;
  bibliotecas externas e da biblioteca padrão não contam;
- Ca: quantos componentes importam este; Ce: quantos este importa;
- I = Ce / (Ce + Ca), ou 0 quando os dois são zero;
- A = classes abstratas (herdam de typing.Protocol ou abc.ABC) / total de classes,
  ou 0 sem classes;
- D = |A + I - 1|; tudo arredondado para 2 casas.
"""
import ast
import csv
import sys
from pathlib import Path

RESULTS = Path(__file__).parent / "results"
ABSTRACT_BASES = {"Protocol", "ABC"}


def components(root: Path) -> dict[str, Path]:
    found = {}
    for path in sorted(root.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        name = ".".join(path.relative_to(root).with_suffix("").parts)
        found[name] = path
    return found


def module_package(root: Path, path: Path) -> list[str]:
    """Pacote do módulo, relativo à raiz medida (lista vazia = raiz)."""
    return list(path.relative_to(root).parent.parts)


def resolve(target: str, known: set[str]) -> str | None:
    return target if target in known else None


def dependencies(root: Path, name: str, path: Path, known: set[str]) -> set[str]:
    package_name = root.name  # ex.: "helpdesk", para imports absolutos
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = module_package(root, path)
    deps = set()

    def absolute(parts: list[str]) -> list[str] | None:
        # "helpdesk.x.y" -> ["x", "y"]; qualquer outro prefixo é externo
        if parts and parts[0] == package_name:
            return parts[1:]
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = absolute(alias.name.split("."))
                if parts:
                    # "import helpdesk.a.b" depende de a.b (ou de a, se b não for módulo)
                    for size in range(len(parts), 0, -1):
                        hit = resolve(".".join(parts[:size]), known)
                        if hit:
                            deps.add(hit)
                            break
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[:len(package) - (node.level - 1)] if node.level > 1 else list(package)
                if node.level - 1 > len(package):
                    continue
                parts = base + (node.module.split(".") if node.module else [])
            else:
                parts = absolute(node.module.split(".")) if node.module else None
                if parts is None:
                    continue
            for alias in node.names:
                # "from pacote import modulo" -> o próprio módulo; senão, o módulo de origem
                hit = resolve(".".join(parts + [alias.name]), known) or resolve(".".join(parts), known)
                if hit:
                    deps.add(hit)
    deps.discard(name)
    return deps


def abstractness(path: Path) -> float:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    if not classes:
        return 0.0

    def base_name(base: ast.expr) -> str:
        if isinstance(base, ast.Subscript):  # Protocol[T]
            base = base.value
        if isinstance(base, ast.Attribute):  # typing.Protocol, abc.ABC
            return base.attr
        if isinstance(base, ast.Name):
            return base.id
        return ""

    abstract = [c for c in classes if any(base_name(b) in ABSTRACT_BASES for b in c.bases)]
    return len(abstract) / len(classes)


def measure(root: Path) -> list[dict]:
    found = components(root)
    known = set(found)
    efferent = {name: dependencies(root, name, path, known) for name, path in found.items()}
    rows = []
    for name, path in found.items():
        ce = len(efferent[name])
        ca = sum(1 for other, deps in efferent.items() if other != name and name in deps)
        i = ce / (ce + ca) if ce + ca else 0.0
        a = abstractness(path)
        d = abs(a + i - 1)
        rows.append({"component": name, "ca": ca, "ce": ce,
                     "i": round(i, 2), "a": round(a, 2), "d": round(d, 2)})
    return rows


def write_csv(rows: list[dict], target: Path) -> None:
    with target.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["component", "ca", "ce", "i", "a", "d"])
        writer.writeheader()
        writer.writerows(rows)


def plot(rows: list[dict], title: str, target: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot([0, 1], [1, 0], color="#2a7", linewidth=1.5, label="Main Sequence (A + I = 1)")
    ax.fill([0, 0.5, 0], [0, 0, 0.5], color="#d33", alpha=0.08, label="Zona de dor")
    ax.fill([1, 0.5, 1], [1, 1, 0.5], color="#36c", alpha=0.08, label="Zona de inutilidade")
    # Componentes no mesmo ponto ganham um rótulo só, um nome por linha.
    points: dict[tuple, list[str]] = {}
    for row in rows:
        points.setdefault((row["i"], row["a"], row["d"]), []).append(row["component"])
    # Rótulos alternam acima e abaixo do ponto para não se sobreporem.
    for n, ((i, a, d), names) in enumerate(sorted(points.items())):
        above = n % 2 == 0
        ax.scatter(i, a, color="#333", zorder=3)
        ax.annotate("\n".join(names) + f"\n(D={d})", (i, a), textcoords="offset points",
                    xytext=(5, 6 if above else -6), fontsize=8, va="bottom" if above else "top")
    ax.set_xlim(-0.05, 1.1)
    ax.set_ylim(-0.25, 1.1)
    ax.set_xlabel("Instabilidade (I)")
    ax.set_ylabel("Abstração (A)")
    ax.set_title(f"A × I — {title}")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(target, dpi=120)


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    root, name = Path(sys.argv[1]).resolve(), sys.argv[2]
    rows = measure(root)
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_csv(rows, RESULTS / f"{name}.csv")
    plot(rows, name, RESULTS / f"{name}.png")
    for row in rows:
        print(f"{row['component']:28} ca={row['ca']} ce={row['ce']} i={row['i']} a={row['a']} d={row['d']}")


if __name__ == "__main__":
    main()
