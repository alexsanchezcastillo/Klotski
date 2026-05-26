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
    1. Col·loca peces aleatòriament: aquesta és la configuració objectiu (goal state).
    2. Fa BFS des del goal state fins a max_nodes nodes per explorar l'espai d'estats.
    3. Tria com a estat inicial un estat en el top 20% de profunditat (molt llunyà del goal).
    4. Avalua amb eval.py i retorna el millor candidat que superi min-stars.
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


# ---------------------------------------------------------------------------
# BFS multi-font per trobar la distància real mínima al goal
# ---------------------------------------------------------------------------

_DELTAS: dict[str, tuple[int, int]] = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}


def _expand_state(
    puzzle: Puzzle, pos_key: tuple[Coord, ...]
) -> list[tuple[Coord, ...]]:
    """Retorna les claus de tots els estats veïns d'un estat donat."""
    state = State(pos_key)
    neighbours = []
    for piece_idx, direction, _ in possible_moves(puzzle, state):
        new_positions = list(pos_key)
        px, py = new_positions[piece_idx]
        dx, dy = _DELTAS[direction]
        new_positions[piece_idx] = (px + dx, py + dy)
        neighbours.append(tuple(new_positions))
    return neighbours


def _multi_source_bfs(
    puzzle: Puzzle,
    goal_piece_idx: int,
    goal_pos: Coord,
    max_nodes: int = 8000,
) -> dict[tuple[Coord, ...], int]:
    """
    Calcula la distància mínima real de cada estat a qualsevol estat objectiu.

    Pas 1: BFS des del goal_state per descobrir l'espai d'estats accessible.
    Pas 2: Identifica tots els estats objectiu dins l'espai descobert.
    Pas 3: BFS multi-font des de tots els estats objectiu simultàniament.

    Retorna {positions_tuple -> min_moviments_per_resoldre}.
    """
    # Pas 1: descobrir l'espai d'estats des del goal_state (puzzle.start = goal_state)
    origin = puzzle.start.positions
    explored: set[tuple[Coord, ...]] = {origin}
    bfs_queue: deque[tuple[Coord, ...]] = deque([origin])

    while bfs_queue and len(explored) < max_nodes:
        pos_key = bfs_queue.popleft()
        for nb in _expand_state(puzzle, pos_key):
            if nb not in explored:
                explored.add(nb)
                bfs_queue.append(nb)

    # Pas 2: tots els estats objectiu dins l'espai descobert
    goal_keys = [k for k in explored if k[goal_piece_idx] == goal_pos]
    if not goal_keys:
        return {}

    # Pas 3: BFS multi-font des de tots els estats objectiu
    dist_map: dict[tuple[Coord, ...], int] = {g: 0 for g in goal_keys}
    ms_queue: deque[tuple[tuple[Coord, ...], int]] = deque(
        (g, 0) for g in goal_keys
    )

    while ms_queue:
        pos_key, dist = ms_queue.popleft()
        for nb in _expand_state(puzzle, pos_key):
            if nb in explored and nb not in dist_map:
                dist_map[nb] = dist + 1
                ms_queue.append((nb, dist + 1))

    return dist_map


# ---------------------------------------------------------------------------
# Generació d'un puzzle candidat
# ---------------------------------------------------------------------------


def generate_candidate(
    rng: random.Random,
    W: int,
    H: int,
    n_pieces: int,
    bfs_max_nodes: int = 8000,
    min_depth: int = 3,
) -> Puzzle | None:
    """
    Genera un puzzle aleatori usant l'estratègia de scramble des del goal:
    1. Col·loca peces aleatòriament → configuració objectiu (goal state).
    2. Defineix el goal com la posició de la peça més gran en aquesta configuració.
    3. BFS des del goal state per explorar estats accessibles.
    4. Tria un estat en el top 20% de profunditat com a start (llunyà del goal).
    Retorna None si no es pot generar un puzzle vàlid o si és trivial.
    """
    occupied: set[Coord] = set()
    walls: set[Coord] = set()
    pieces_raw: list[list[Coord]] = []
    positions: list[Coord] = []

    for _ in range(n_pieces):
        shape = rng.choice(PIECE_SHAPES)
        bw, bh = _bounding_box(shape)
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

    try:
        pieces = [Piece(*shape) for shape in pieces_raw]
    except ValueError:
        return None

    pieces, positions = _canonicalize(pieces, positions)

    # La disposició aleatòria és el goal state
    goal_state = State(tuple(positions))

    # La peça objectiu és la més gran (més maniobra necessària)
    piece_sizes = [(sum(1 for _ in p.coords), i) for i, p in enumerate(pieces)]
    goal_piece_idx = max(piece_sizes)[1]
    goal_pos: Coord = positions[goal_piece_idx]
    goals = ((goal_piece_idx, goal_pos),)

    try:
        puzzle_from_goal = Puzzle(
            W=W,
            H=H,
            walls=tuple(sorted(walls)),
            pieces=tuple(pieces),
            start=goal_state,
            goals=goals,
        )
    except ValueError:
        return None

    # BFS multi-font: distància real mínima al goal per a cada estat
    dist_map = _multi_source_bfs(
        puzzle_from_goal, goal_piece_idx, goal_pos, max_nodes=bfs_max_nodes
    )
    if not dist_map:
        return None

    # Excloem els propis estats objectiu (dist=0) i triem del top 20% de profunditat
    max_depth = max(dist_map.values())
    if max_depth < min_depth:
        return None

    threshold = max_depth * 0.8
    deep_states = [
        positions_key
        for positions_key, depth in dist_map.items()
        if depth >= threshold and depth > 0
    ]
    if not deep_states:
        return None
    start_positions = list(rng.choice(deep_states))

    # Re-canonicalitzar: (forma, posició_start) pot diferir de (forma, posició_goal)
    # Necessitem reordenar peces i posicions perquè Puzzle.__post_init__ ho accepti.
    indexed = sorted(range(len(pieces)), key=lambda i: (pieces[i], start_positions[i]))
    sorted_pieces = [pieces[i] for i in indexed]
    sorted_start = [start_positions[i] for i in indexed]
    new_goal_idx = indexed.index(goal_piece_idx)
    new_goals = ((new_goal_idx, goal_pos),)

    try:
        return Puzzle(
            W=W,
            H=H,
            walls=tuple(sorted(walls)),
            pieces=tuple(sorted_pieces),
            start=State(tuple(sorted_start)),
            goals=new_goals,
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
    skipped = 0

    max_attempts = max(n_candidates * 50, 200)
    for attempt in range(max_attempts):
        if evaluated >= n_candidates:
            break

        candidate = generate_candidate(rng, W, H, n_pieces)
        if candidate is None:
            skipped += 1
            continue

        evaluated += 1

        # Construir el graf complet per obtenir mètriques precises
        try:
            g = build_graph(candidate)
        except Exception as e:
            print(f"    Error construint graf: {e}", file=sys.stderr)
            skipped += 1
            evaluated -= 1
            continue

        try:
            metrics = compute_metrics(g, with_betweenness=False)
        except Exception as e:
            print(f"    Error calculant mètriques: {e}", file=sys.stderr)
            skipped += 1
            evaluated -= 1
            continue

        stars = score_from_metrics(metrics)
        metrics["stars"] = stars
        sol_len = metrics.get("min_solution_len", "?")
        print(
            f"  Candidat {evaluated}/{n_candidates}: "
            f"solució mínima={sol_len} moviments | puntuació={stars:.2f}/5",
            file=sys.stderr,
        )

        if stars > best_stars:
            best_stars = stars
            best_puzzle = candidate
            best_metrics = metrics

    total_attempts = evaluated + skipped
    print(
        f"\nResum: {evaluated} candidats avaluats, {skipped} descartats "
        f"({total_attempts} intents totals, màxim {max_attempts}).",
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
