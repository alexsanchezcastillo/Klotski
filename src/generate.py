"""
Genera un puzzle Klotski aleatori de qualitat.

Ús:
    python src/generate.py [opcions]
    python src/generate.py --out puzzles/nou.json
    python src/generate.py --width 4 --height 5 --pieces 8 --min-stars 2.0
    python src/generate.py --candidates 20 --seed 42

Paràmetres principals:
    --width      Amplada del taulell (per defecte 4)
    --height     Alçada del taulell (per defecte 5)
    --pieces     Nombre de peces (per defecte 6)
    --min-stars  Puntuació mínima acceptable [0–5] (per defecte 1.5)
    --candidates Quants candidats generar i avaluar (per defecte 10)
    --seed       Llavor aleatòria per reproduir resultats
    --out        Fitxer de sortida (per defecte puzzles/generated_<hash>.json)

Heurística aplicada:
    1. Genera `candidates` puzzles aleatoris amb peces de formes variades.
    2. Avalua cadascun amb les mètriques de eval.py (sense construir el graf
       complet: fa un BFS limitat per filtrar ràpidament els insolubles).
    3. Construeix el graf complet dels candidats que superen el filtre.
    4. Retorna el que obté la millor puntuació, sempre que superi min-stars.
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportUnknownParameterType=false

from __future__ import annotations

import argparse
import random
import sys
from collections import deque
from pathlib import Path
from typing import Any

# Afegim src/ al path per a importacions relatives
sys.path.insert(0, str(Path(__file__).parent))

from eval import compute_metrics, score_from_metrics
from graph import build_graph
from logic import possible_moves
from puzzle import Coord, Piece, Puzzle, State

# ---------------------------------------------------------------------------
# Catàleg de formes de peces (coordenades relatives normalitzades)
# ---------------------------------------------------------------------------

PIECE_SHAPES: list[list[Coord]] = [
    # 1×1
    [(0, 0)],
    # 1×2 horitzontal
    [(0, 0), (1, 0)],
    # 1×2 vertical
    [(0, 0), (0, 1)],
    # 1×3 horitzontal
    [(0, 0), (1, 0), (2, 0)],
    # 1×3 vertical
    [(0, 0), (0, 1), (0, 2)],
    # 2×2
    [(0, 0), (1, 0), (0, 1), (1, 1)],
    # L dreta
    [(0, 0), (0, 1), (0, 2), (1, 2)],
    # L esquerra
    [(0, 0), (1, 0), (1, 1), (1, 2)],
    # L invertida dreta
    [(0, 0), (1, 0), (0, 1), (0, 2)],
    # L invertida esquerra
    [(0, 0), (1, 0), (1, 1), (1, 2)],
    # T
    [(0, 0), (1, 0), (2, 0), (1, 1)],
    # S
    [(1, 0), (2, 0), (0, 1), (1, 1)],
    # Z
    [(0, 0), (1, 0), (1, 1), (2, 1)],
]


# ---------------------------------------------------------------------------
# Utilitats de generació
# ---------------------------------------------------------------------------


def _bounding_box(coords: list[Coord]) -> tuple[int, int]:
    """Retorna (amplada, alçada) de la bounding box d'un conjunt de coordenades."""
    w = max(x for x, _ in coords) + 1
    h = max(y for _, y in coords) + 1
    return w, h


def _try_place_piece(
    rng: random.Random,
    W: int,
    H: int,
    shape: list[Coord],
    occupied: set[Coord],
    walls: set[Coord],
    max_attempts: int = 200,
) -> Coord | None:
    """
    Intenta col·locar una peça en una posició aleatòria lliure.
    Retorna la posició (px, py) si ho aconsegueix, o None si no.
    """
    bw, bh = _bounding_box(shape)
    if bw > W or bh > H:
        return None

    for _ in range(max_attempts):
        px = rng.randint(0, W - bw)
        py = rng.randint(0, H - bh)
        cells = {(px + dx, py + dy) for dx, dy in shape}
        if cells & occupied or cells & walls:
            continue
        return (px, py)
    return None


def _canonicalize(
    pieces: list[Piece], positions: list[Coord]
) -> tuple[list[Piece], list[Coord]]:
    """
    Ordena peces i posicions en ordre canònic: (forma, posició_inicial).
    """
    paired = sorted(zip(pieces, positions))
    if not paired:
        return [], []
    ps, pos = zip(*paired)
    return list(ps), list(pos)


def _goal_for_piece(
    rng: random.Random,
    puzzle: Puzzle,
    piece_idx: int,
    max_attempts: int = 100,
) -> Coord | None:
    """
    Tria una posició objectiu per a la peça donada, diferent de la inicial.
    La posició ha de fer que la peça no surti del taulell i no col·lideixi
    amb les parets (però sí pot coincidir amb altres peces perquè l'objectiu
    no implica que el taulell estigui buit allà).
    """
    shape = puzzle.pieces[piece_idx].coords
    bw = max(x for x, _ in shape) + 1
    bh = max(y for _, y in shape) + 1
    current = puzzle.start.positions[piece_idx]

    blocked: set[Coord] = set(puzzle.walls)

    for _ in range(max_attempts):
        gx = rng.randint(0, puzzle.W - bw)
        gy = rng.randint(0, puzzle.H - bh)
        if (gx, gy) == current:
            continue
        cells = {(gx + dx, gy + dy) for dx, dy in shape}
        if cells & blocked:
            continue
        return (gx, gy)
    return None


# ---------------------------------------------------------------------------
# BFS limitat per detectar si el puzzle és soluble (ràpid)
# ---------------------------------------------------------------------------


def _bfs_limited(puzzle: Puzzle, max_nodes: int = 5000) -> int | None:
    """
    BFS des de l'estat inicial. Retorna la longitud de la solució mínima
    si es troba dins dels primers max_nodes nodes explorats, o None si no.
    """
    def is_goal(state: State) -> bool:
        return all(state.positions[i] == pos for i, pos in puzzle.goals)

    start = puzzle.start
    visited: dict[tuple[Coord, ...], int] = {start.positions: 0}
    queue: deque[tuple[State, int]] = deque([(start, 0)])

    while queue and len(visited) < max_nodes:
        state, dist = queue.popleft()
        if is_goal(state):
            return dist
        for piece_idx, direction, _ in possible_moves(puzzle, state):
            new_positions = list(state.positions)
            px, py = new_positions[piece_idx]
            if direction == "N":
                py -= 1
            elif direction == "S":
                py += 1
            elif direction == "E":
                px += 1
            elif direction == "W":
                px -= 1
            new_positions[piece_idx] = (px, py)
            key = tuple(new_positions)
            if key not in visited:
                visited[key] = dist + 1
                queue.append((State(tuple(new_positions)), dist + 1))

    return None


# ---------------------------------------------------------------------------
# Generació d'un puzzle candidat
# ---------------------------------------------------------------------------


def generate_candidate(
    rng: random.Random,
    W: int,
    H: int,
    n_pieces: int,
) -> Puzzle | None:
    """
    Genera un puzzle aleatori amb n_pieces peces i almenys un objectiu.
    Retorna None si no es pot generar un puzzle vàlid.
    """
    occupied: set[Coord] = set()
    walls: set[Coord] = set()

    pieces_raw: list[list[Coord]] = []
    positions: list[Coord] = []

    # Triar i col·locar peces aleatòries
    for _ in range(n_pieces):
        shape = rng.choice(PIECE_SHAPES)
        bw, bh = _bounding_box(shape)
        # Descartar formes massa grans per al taulell
        if bw > W or bh > H:
            continue
        pos = _try_place_piece(rng, W, H, shape, occupied, walls)
        if pos is None:
            continue
        pieces_raw.append(shape)
        positions.append(pos)
        px, py = pos
        for dx, dy in shape:
            occupied.add((px + dx, py + dy))

    if len(pieces_raw) < 2:
        return None

    # Construir objectes Piece
    try:
        pieces = [Piece(*shape) for shape in pieces_raw]
    except ValueError:
        return None

    # Canonicalitzar ordre
    pieces, positions = _canonicalize(pieces, positions)

    try:
        state = State(tuple(positions))
        puzzle = Puzzle(
            W=W,
            H=H,
            walls=tuple(sorted(walls)),
            pieces=tuple(pieces),
            start=state,
            goals=(),  # temporal, sense objectiu encara
        )
    except ValueError:
        return None

    # Triar un objectiu: la peça amb forma més gran (que requerirà més maniobra)
    # i una posició objectiu diferent de l'actual
    piece_sizes = [(sum(1 for _ in p.coords), i) for i, p in enumerate(pieces)]
    piece_sizes.sort(reverse=True)

    goal_piece_idx: int | None = None
    goal_pos: Coord | None = None

    for _, idx in piece_sizes:
        goal_pos = _goal_for_piece(rng, puzzle, idx)
        if goal_pos is not None:
            goal_piece_idx = idx
            break

    if goal_piece_idx is None or goal_pos is None:
        return None

    goals = tuple(sorted([(goal_piece_idx, goal_pos)]))

    try:
        return Puzzle(
            W=W,
            H=H,
            walls=tuple(sorted(walls)),
            pieces=tuple(pieces),
            start=state,
            goals=goals,
        )
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Pipeline principal: generar, avaluar i seleccionar el millor
# ---------------------------------------------------------------------------


def generate_best(
    W: int,
    H: int,
    n_pieces: int,
    min_stars: float,
    n_candidates: int,
    seed: int | None,
) -> tuple[Puzzle, dict[str, Any]] | None:
    """
    Genera fins a n_candidates puzzles candidats i retorna el millor
    que superi min_stars. Retorna None si cap candidat supera el llindar.
    """
    rng = random.Random(seed)

    best_puzzle: Puzzle | None = None
    best_metrics: dict[str, Any] | None = None
    best_stars: float = -1.0

    evaluated = 0
    skipped_unsolvable = 0
    skipped_trivial = 0

    for _ in range(n_candidates * 5):  # marge ampli d'intents
        if evaluated >= n_candidates:
            break

        candidate = generate_candidate(rng, W, H, n_pieces)
        if candidate is None:
            continue

        # Filtre ràpid: BFS limitat per descartar no solubles o trivials
        sol_len = _bfs_limited(candidate, max_nodes=8000)
        if sol_len is None:
            skipped_unsolvable += 1
            continue
        if sol_len < 3:
            skipped_trivial += 1
            continue

        evaluated += 1
        print(
            f"  Candidat {evaluated}/{n_candidates}: "
            f"solució mínima BFS={sol_len} moviments",
            file=sys.stderr,
        )

        # Construir el graf complet per obtenir mètriques precises
        try:
            g = build_graph(candidate)
        except Exception as e:
            print(f"    Error construint graf: {e}", file=sys.stderr)
            continue

        try:
            metrics = compute_metrics(g, with_betweenness=False)
        except Exception as e:
            print(f"    Error calculant mètriques: {e}", file=sys.stderr)
            continue

        stars = score_from_metrics(metrics)
        metrics["stars"] = stars
        print(f"    Puntuació: {stars:.2f} / 5", file=sys.stderr)

        if stars > best_stars:
            best_stars = stars
            best_puzzle = candidate
            best_metrics = metrics

    print(
        f"\nResum: {evaluated} candidats avaluats, "
        f"{skipped_unsolvable} insolubles descartats, "
        f"{skipped_trivial} trivials descartats.",
        file=sys.stderr,
    )

    if best_puzzle is None or best_metrics is None:
        return None

    if best_stars < min_stars:
        print(
            f"Cap candidat supera el llindar de {min_stars} estrelles "
            f"(millor: {best_stars:.2f}).",
            file=sys.stderr,
        )
        return None

    return best_puzzle, best_metrics


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera un puzzle Klotski aleatori de qualitat",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=4,
        help="Amplada del taulell (per defecte 4)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=5,
        help="Alçada del taulell (per defecte 5)",
    )
    parser.add_argument(
        "--pieces",
        type=int,
        default=6,
        help="Nombre de peces (per defecte 6)",
    )
    parser.add_argument(
        "--min-stars",
        type=float,
        default=1.5,
        help="Puntuació mínima acceptable [0–5] (per defecte 1.5)",
    )
    parser.add_argument(
        "--candidates",
        type=int,
        default=10,
        help="Nombre de candidats a avaluar (per defecte 10)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Llavor aleatòria per reproduir resultats",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Fitxer de sortida (per defecte puzzles/generated_<hash>.json)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print(
        f"Generant puzzles: {args.width}x{args.height}, "
        f"{args.pieces} peces, {args.candidates} candidats, "
        f"llindar {args.min_stars} estrelles...",
        file=sys.stderr,
    )

    result = generate_best(
        W=args.width,
        H=args.height,
        n_pieces=args.pieces,
        min_stars=args.min_stars,
        n_candidates=args.candidates,
        seed=args.seed,
    )

    if result is None:
        print(
            "No s'ha pogut generar cap puzzle que compleixi els criteris.",
            file=sys.stderr,
        )
        return 1

    puzzle, metrics = result

    if args.out:
        out_path = Path(args.out)
    else:
        puzzle_hash = puzzle.hash()[:16]
        out_path = Path("puzzles") / f"generated_{puzzle_hash}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(puzzle.to_json(indent=2))

    print(f"\nPuzzle desat a: {out_path}")
    print(f"Dimensions: {puzzle.W}x{puzzle.H}")
    print(f"Peces: {len(puzzle.pieces)}")
    print(f"Nodes del graf: {metrics['nodes']}")
    print(f"Longitud solució mínima: {metrics['min_solution_len']}")
    print(f"Puntuació: {metrics['stars']:.3f} / 5")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
