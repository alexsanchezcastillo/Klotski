"""
Descarrega puzzles del repositori de Klotski.

Ús:
    python src/download.py
    python src/download.py --limit 10
    python src/download.py --id <puzzle_id>
    python src/download.py --id <puzzle_id1> --id <puzzle_id2>
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, cast

from puzzle import Puzzle

BASE_URL = "https://klotski.pauek.dev"
LIST_ROUTE = "/api/puzzles"

JsonObj = dict[str, Any]


def get_json(url: str) -> Any:
    """Fa un GET i retorna la resposta parsejada com a JSON."""
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def fetch_top_ids(limit: int | None = None) -> list[str]:
    """Obté la llista d'IDs del repositori (top 100)."""
    data = get_json(f"{BASE_URL}{LIST_ROUTE}")
    if not isinstance(data, list):
        raise ValueError("Resposta inesperada a /api/puzzles")
    ids_raw = cast(list[Any], data)
    ids = [str(x) for x in ids_raw]
    if limit is not None:
        ids = ids[:limit]
    return ids


def fetch_puzzle_payload(puzzle_id: str) -> JsonObj:
    """Obté el payload d'un puzzle concret per ID."""
    data = get_json(f"{BASE_URL}{LIST_ROUTE}/{puzzle_id}")
    if not isinstance(data, dict) or "puzzle" not in data:
        raise ValueError(f"Resposta inesperada per ID {puzzle_id}")
    return cast(JsonObj, data)


def save_puzzle(puzzle_id: str, out_dir: Path) -> Path:
    """Descarrega, valida i desa un puzzle en format .json."""
    payload = fetch_puzzle_payload(puzzle_id)
    puzzle_obj = payload["puzzle"]
    puzzle_json = json.dumps(puzzle_obj)

    # Validació de format canònic i coherència del puzzle
    Puzzle.from_json(puzzle_json)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{puzzle_id}.json"
    out_path.write_text(json.dumps(puzzle_obj, indent=2) + "\n")
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarrega puzzles del repositori de Klotski",
    )
    parser.add_argument(
        "--id",
        action="append",
        dest="ids",
        help="ID concret a descarregar (es pot repetir)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Nombre màxim d'IDs del top a descarregar",
    )
    parser.add_argument(
        "--out",
        default="puzzles",
        help="Carpeta de sortida (per defecte: puzzles)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out)

    try:
        ids: list[str]
        if args.ids:
            ids = args.ids
        else:
            ids = fetch_top_ids(args.limit)

        if len(ids) == 0:
            print("No hi ha IDs per descarregar")
            return 0

        print(f"Descarregant {len(ids)} puzzle(s)...")
        ok = 0
        for i, puzzle_id in enumerate(ids, start=1):
            try:
                path = save_puzzle(puzzle_id, out_dir)
                ok += 1
                print(f"[{i}/{len(ids)}] OK  {puzzle_id} -> {path}")
            except Exception as exc:
                print(f"[{i}/{len(ids)}] ERR {puzzle_id}: {exc}")

        print(f"Completat: {ok}/{len(ids)} descarregats")
        return 0 if ok == len(ids) else 2
    except urllib.error.URLError as exc:
        print(f"Error de xarxa: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
