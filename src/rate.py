"""
Envia una valoració (estrelles) d'un puzzle al repositori.

Ús:
    python src/rate.py <puzzle.json> --token <TOKEN>

Calcula la puntuació automàticament amb eval.py i l'envia a l'API.
L'ID del puzzle és el nom del fitxer sense extensió.
  - Si el fitxer ve de download.py, el nom és el hash SHA-256 directament.
  - Si es vol indicar un ID explícit, usa --id.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

API_BASE = "https://klotski.pauek.dev"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Envia una valoració d'un puzzle al repositori",
    )
    parser.add_argument("puzzle", help="Fitxer puzzle .json")
    parser.add_argument(
        "--id",
        dest="puzzle_id",
        default=None,
        help="ID del puzzle (per defecte: nom del fitxer sense extensió)",
    )
    parser.add_argument(
        "--token",
        required=True,
        help="Token d'autenticació",
    )
    parser.add_argument(
        "--graphml",
        default=None,
        help="Fitxer .graphml per a eval.py (opcional)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra la petició però no l'envia",
    )
    return parser.parse_args()



def compute_stars(puzzle_path: Path, graphml_path: str | None) -> float:
    """Calcula la puntuació del puzzle usant eval.py."""
    import importlib
    import importlib.util

    eval_path = Path(__file__).parent / "eval.py"
    spec = importlib.util.spec_from_file_location("eval", eval_path)
    if spec is None or spec.loader is None:
        raise ImportError("No s'ha pogut carregar eval.py")
    eval_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eval_mod)  # type: ignore[union-attr]

    gt = importlib.import_module("graph_tool.all")
    from graph import build_graph
    from puzzle import Puzzle

    puzzle = Puzzle.from_json(puzzle_path.read_text())
    graph_path = Path(graphml_path) if graphml_path else puzzle_path.with_suffix(".graphml")

    if graph_path.exists():
        g = gt.load_graph(str(graph_path))
    else:
        print(f"Construint graf {graph_path} ...", file=sys.stderr)
        g = build_graph(puzzle)
        g.save(str(graph_path))

    metrics = eval_mod.compute_metrics(g, with_betweenness=False)
    return float(eval_mod.score_from_metrics(metrics))


def post_vote(puzzle_id: str, stars: float, token: str, dry_run: bool) -> None:
    url = f"{API_BASE}/api/puzzles/{puzzle_id}/votes"
    payload = json.dumps({"stars": stars}).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    if dry_run:
        print(f"[dry-run] POST {url}")
        print(f"[dry-run] Body: {{\"stars\": {stars}}}")
        return

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
            print(f"Resposta {resp.status}: {body}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Error HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error de connexió: {e.reason}", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    args = parse_args()

    puzzle_path = Path(args.puzzle)
    if not puzzle_path.exists():
        print(f"Error: fitxer no trobat: {puzzle_path}", file=sys.stderr)
        return 1

    puzzle_id = args.puzzle_id or puzzle_path.stem
    token = args.token

    print("Calculant puntuació amb eval.py ...", file=sys.stderr)
    stars = round(compute_stars(puzzle_path, args.graphml))

    print(f"Puzzle ID: {puzzle_id}")
    print(f"Estrelles: {stars:.2f} / 5.00")

    post_vote(puzzle_id, stars, token, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
