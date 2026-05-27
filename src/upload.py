"""
Puja un puzzle nou al repositori col·laboratiu.

Ús:
    python src/upload.py <puzzle.json> --token <TOKEN>
    python src/upload.py puzzles/generated_abc.json --token <TOKEN> --dry-run

Flux recomanat:
    generate.py → eval.py (comprovar qualitat) → upload.py → rate.py (opcional)

L'ID al repositori és el SHA-256 del JSON canònic en forma compacta
(mateix criteri que download.py / rate.py amb fitxers descarregats).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from puzzle import Puzzle

API_BASE = "https://klotski.pauek.dev"
UPLOAD_ROUTE = "/api/puzzles"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Puja un puzzle .json al repositori Klotski",
    )
    parser.add_argument("puzzle", help="Fitxer puzzle .json")
    parser.add_argument(
        "--token",
        required=True,
        help="Token d'autenticació (correu UPC)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida i mostra la petició però no l'envia",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Després del POST, comprova GET /api/puzzles/<id>",
    )
    return parser.parse_args()


def server_puzzle_id(puzzle_obj: dict[str, Any]) -> str:
    """ID que usa el servidor (SHA-256 del JSON compacte)."""
    payload = json.dumps(puzzle_obj, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_canonical_puzzle(path: Path) -> tuple[Puzzle, dict[str, Any]]:
    """Llegeix el fitxer, valida i retorna el puzzle i el dict JSON canònic."""
    text = path.read_text(encoding="utf-8")
    puzzle = Puzzle.from_json(text)
    obj = json.loads(puzzle.to_json())
    if not isinstance(obj, dict):
        raise ValueError("El JSON del puzzle no és un objecte")
    return puzzle, obj


def post_puzzle(puzzle_obj: dict[str, Any], token: str, dry_run: bool) -> None:
    url = f"{API_BASE}{UPLOAD_ROUTE}"
    body = json.dumps(puzzle_obj).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    if dry_run:
        print(f"[dry-run] POST {url}")
        print(f"[dry-run] Authorization: Bearer ***")
        print(f"[dry-run] Body: puzzle JSON ({len(body)} bytes)")
        return

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            print(f"Resposta {resp.status}: {raw}")
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode()
        print(f"Error HTTP {exc.code}: {err_body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Error de connexió: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def verify_upload(puzzle_id: str) -> bool:
    """Comprova que el puzzle es pot llegir des del repositori."""
    url = f"{API_BASE}{UPLOAD_ROUTE}/{puzzle_id}"
    try:
        with urllib.request.urlopen(url) as resp:
            raw = resp.read().decode()
            print(f"Verificació GET {resp.status}: puzzle accessible ({len(raw)} bytes)")
            return True
    except urllib.error.HTTPError as exc:
        print(f"Verificació fallida HTTP {exc.code}", file=sys.stderr)
        return False
    except urllib.error.URLError as exc:
        print(f"Verificació: error de connexió: {exc.reason}", file=sys.stderr)
        return False


def main() -> int:
    args = parse_args()
    puzzle_path = Path(args.puzzle)

    if not puzzle_path.exists():
        print(f"Error: fitxer no trobat: {puzzle_path}", file=sys.stderr)
        return 1

    try:
        puzzle, puzzle_obj = load_canonical_puzzle(puzzle_path)
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        print(f"Error de validació del puzzle: {exc}", file=sys.stderr)
        return 1

    puzzle_id = server_puzzle_id(puzzle_obj)
    print(f"Fitxer: {puzzle_path}")
    print(f"ID al repositori (SHA-256 JSON compacte): {puzzle_id}")
    print(f"Dimensions: {puzzle.W}x{puzzle.H}, peces: {len(puzzle.pieces)}")

    post_puzzle(puzzle_obj, args.token, dry_run=args.dry_run)

    if args.dry_run:
        return 0

    if args.verify:
        if not verify_upload(puzzle_id):
            return 1

    print()
    suggested = puzzle_path.parent / f"{puzzle_id}.json"
    if puzzle_path.name != f"{puzzle_id}.json":
        print(f"Consell: renombra una còpia a {suggested} per a rate.py")
    print("Valorar amb:")
    print(f"  pixi run python src/rate.py {suggested} --token <TOKEN>")
    print(f"  (o --id {puzzle_id} amb el fitxer actual)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
