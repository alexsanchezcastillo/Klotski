"""
Descarrega tots els puzzles del repositori, els avalua i envia les valoracions.

Ús:
    python src/rate_all.py --token <TOKEN>
    python src/rate_all.py --token <TOKEN> --limit 10
    python src/rate_all.py --token <TOKEN> --puzzles-dir puzzles/ --dry-run

Flux:
    1. Obté la llista d'IDs del repositori (GET /api/puzzles).
    2. Per cada ID, usa el .json local si existeix; si no, el descarrega.
    3. Calcula les estrelles amb eval.py (construeix el .graphml si cal).
    4. Envia la valoració amb POST /api/puzzles/<id>/votes.

Útil per mantenir actualitzades totes les valoracions quan es canvia la
fórmula de eval.py, sense haver de cridar rate.py manualment per cada puzzle.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from download import fetch_top_ids, fetch_puzzle_payload
from rate import compute_stars, post_vote

API_BASE = "https://klotski.pauek.dev"


def ensure_puzzle(puzzle_id: str, puzzles_dir: Path) -> Path | None:
    """
    Retorna el path del .json local, descarregant-lo si no existeix.
    Retorna None si la descàrrega falla.
    """
    local_path = puzzles_dir / f"{puzzle_id}.json"
    if local_path.exists():
        return local_path

    try:
        payload = fetch_puzzle_payload(puzzle_id)
        puzzle_obj = payload["puzzle"]
        puzzles_dir.mkdir(parents=True, exist_ok=True)
        local_path.write_text(json.dumps(puzzle_obj, indent=2) + "\n")
        return local_path
    except Exception as exc:
        print(f"  Error descarregant {puzzle_id}: {exc}", file=sys.stderr)
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Avalua i valora tots els puzzles del repositori",
    )
    parser.add_argument(
        "--token",
        required=True,
        help="Token d'autenticació per enviar valoracions",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Nombre màxim de puzzles a processar (per defecte: tots)",
    )
    parser.add_argument(
        "--puzzles-dir",
        default="puzzles",
        help="Carpeta amb els .json locals (per defecte: puzzles)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calcula les puntuacions però no envia cap valoració",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    puzzles_dir = Path(args.puzzles_dir)

    print("Obtenint llista d'IDs del repositori...", file=sys.stderr)
    try:
        ids = fetch_top_ids(limit=args.limit)
    except urllib.error.URLError as exc:
        print(f"Error de xarxa: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error obtenint IDs: {exc}", file=sys.stderr)
        return 1

    if not ids:
        print("No hi ha puzzles al repositori.")
        return 0

    print(f"Processant {len(ids)} puzzle(s)...\n", file=sys.stderr)

    ok = 0
    errors = 0

    for i, puzzle_id in enumerate(ids, start=1):
        print(f"[{i}/{len(ids)}] {puzzle_id}")

        puzzle_path = ensure_puzzle(puzzle_id, puzzles_dir)
        if puzzle_path is None:
            print(f"  Saltat (no s'ha pogut obtenir el fitxer).")
            errors += 1
            continue

        try:
            stars = round(compute_stars(puzzle_path, graphml_path=None), 2)
        except Exception as exc:
            print(f"  Error avaluant: {exc}", file=sys.stderr)
            errors += 1
            continue

        print(f"  Estrelles: {stars:.2f} / 5.00")

        try:
            post_vote(puzzle_id, stars, args.token, dry_run=args.dry_run)
            ok += 1
        except SystemExit:
            errors += 1
            continue

    print(f"\nResum: {ok} valoracions enviades, {errors} errors.")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
