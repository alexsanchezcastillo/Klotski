"""
Genera un puzzle Klotski aleatori de qualitat.

Ús:
    python src/generate.py [opcions]
    python src/generate.py --out puzzles/nou.json
    python src/generate.py --width 5 --height 5 --pieces 7 --min-stars 2.0
    python src/generate.py --candidates 20 --seed 42

Paràmetres principals:
    --width      Amplada del taulell (per defecte 5)
    --height     Alçada del taulell (per defecte 5)
    --pieces     Nombre de peces (per defecte 7)
    --min-stars  Puntuació mínima acceptable [0–5] (per defecte 1.5)
    --candidates Quants candidats generar i avaluar (per defecte 15)
    --seed       Llavor aleatòria per reproduir resultats
    --out        Fitxer de sortida (per defecte puzzles/generated_<hash>.json)

Estratègia de generació:
    1. Col·loca peces aleatòriament: configuració objectiu (goal state).
    2. BFS multi-font des del goal per explorar l'espai (màx. BFS_CAP nodes).
    3. Tria com a start un estat en el top 20% de profunditat (llunyà del goal).
    4. Avaluació ràpida sense graph-tool (BFS des del start, mètriques bàsiques).
    5. Es guarda el millor candidat (fast_score màxim).
    6. Construcció del graf complet (graph-tool, màx. BFS_WIN nodes) per al guanyador.
    7. Avaluació final amb eval.py i desada del JSON.

La separació entre avaluació ràpida (tots els candidats) i avaluació completa
(només el guanyador) garanteix que la generació no es pengi mai i és eficient.
Per a taulells grans (5×5 amb 7+ peces) s'obtenen espais d'estats de milers
de nodes i solucions de 20–60 moviments, que donen puntuacions de 2–4 estrelles.
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportUnknownParameterType=false

from __future__ import annotations

import argparse
import math
import random
import sys
from collections import deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from eval import compute_metrics, score_from_metrics
from graph import build_graph
from logic import possible_moves
from puzzle import Coord, Piece, Puzzle, State

# ---------------------------------------------------------------------------
# Constants de generació
# ---------------------------------------------------------------------------

# Límit d'estats en el BFS durant la fase d'avaluació ràpida (candidats).
# Prou gran per detectar puzzles interessants, prou petit per ser ràpid.
BFS_CAP: int = 30_000

# Límit d'estats per al graf graph-tool del guanyador final.
# Amb 15k nodes i grau ~3, la betweenness triga ~1-2 s en graph-tool (C++).
BFS_WIN: int = 15_000

# Cobertura mínima del taulell per considerar un candidat (fracció de caselles).
# ~80 % garanteix pocs espais lliures, branching baix i solucions llargues.
MIN_COVERAGE: float = 0.80

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
    # T
    [(0, 0), (1, 0), (2, 0), (1, 1)],
    # S
    [(1, 0), (2, 0), (0, 1), (1, 1)],
    # Z
    [(0, 0), (1, 0), (1, 1), (2, 1)],
]

_DELTAS: dict[str, tuple[int, int]] = {
    "N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)
}

# ---------------------------------------------------------------------------
# Utilitats de col·locació
# ---------------------------------------------------------------------------


def _bounding_box(coords: list[Coord]) -> tuple[int, int]:
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
    paired = sorted(zip(pieces, positions))
    if not paired:
        return [], []
    ps, pos = zip(*paired)
    return list(ps), list(pos)


# ---------------------------------------------------------------------------
# BFS
# ---------------------------------------------------------------------------


def _expand_state(
    puzzle: Puzzle, pos_key: tuple[Coord, ...]
) -> list[tuple[Coord, ...]]:
    """Retorna les claus de tots els estats veïns d'un estat donat."""
    state = State(pos_key)
    neighbors: list[tuple[Coord, ...]] = []
    for piece_idx, direction, _ in possible_moves(puzzle, state):
        new_positions = list(pos_key)
        px, py = new_positions[piece_idx]
        dx, dy = _DELTAS[direction]
        new_positions[piece_idx] = (px + dx, py + dy)
        neighbors.append(tuple(new_positions))
    return neighbors


def _multi_source_bfs(
    puzzle: Puzzle,
    goal_piece_idx: int,
    goal_pos: Coord,
    max_nodes: int = BFS_CAP,
) -> dict[tuple[Coord, ...], int]:
    """
    Calcula la distància mínima real de cada estat a qualsevol estat objectiu.

    Pas 1: BFS des del goal_state per descobrir l'espai accessible (màx. max_nodes).
    Pas 2: Identifica tots els estats objectiu dins l'espai descobert.
    Pas 3: BFS multi-font des de tots els estats objectiu.

    Retorna {positions_tuple -> min_moviments_per_resoldre}.
    """
    origin = puzzle.start.positions
    explored: set[tuple[Coord, ...]] = {origin}
    bfs_queue: deque[tuple[Coord, ...]] = deque([origin])

    while bfs_queue and len(explored) < max_nodes:
        pos_key = bfs_queue.popleft()
        for nb in _expand_state(puzzle, pos_key):
            if nb not in explored:
                explored.add(nb)
                bfs_queue.append(nb)

    goal_keys = [k for k in explored if k[goal_piece_idx] == goal_pos]
    if not goal_keys:
        return {}

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


def _fast_bfs(
    puzzle: Puzzle,
    max_nodes: int = BFS_CAP,
) -> tuple[dict[tuple[Coord, ...], int], dict[tuple[Coord, ...], int], bool]:
    """
    BFS des de puzzle.start, limitat a max_nodes estats.

    Retorna (dist_map, degree_map, truncated):
    - dist_map:   estat -> distància des del start
    - degree_map: estat -> nombre de moviments vàlids (grau)
    - truncated:  True si s'ha assolit el límit de nodes
    """
    start_key = puzzle.start.positions
    dist_map: dict[tuple[Coord, ...], int] = {start_key: 0}
    degree_map: dict[tuple[Coord, ...], int] = {}
    queue: deque[tuple[tuple[Coord, ...], int]] = deque([(start_key, 0)])

    while queue:
        pos_key, dist = queue.popleft()
        neighbors = _expand_state(puzzle, pos_key)
        degree_map[pos_key] = len(neighbors)
        for nb in neighbors:
            if nb not in dist_map:
                if len(dist_map) >= max_nodes:
                    return dist_map, degree_map, True
                dist_map[nb] = dist + 1
                queue.append((nb, dist + 1))

    return dist_map, degree_map, False


# ---------------------------------------------------------------------------
# Avaluació ràpida (sense graph-tool)
# ---------------------------------------------------------------------------


def fast_evaluate(
    puzzle: Puzzle,
    max_nodes: int = BFS_CAP,
) -> dict[str, Any] | None:
    """
    Mètriques bàsiques a partir d'un BFS pur des del start.
    No requereix graph-tool; és O(max_nodes × branching_factor).
    Retorna None si el puzzle no és resoluble dins del límit.
    """
    if not puzzle.goals:
        return None
    goal_piece_idx, goal_pos = puzzle.goals[0]

    dist_map, degree_map, truncated = _fast_bfs(puzzle, max_nodes)
    n = len(dist_map)
    if n == 0:
        return None

    goal_dists = [
        dist_map[k] for k in dist_map
        if k[goal_piece_idx] == goal_pos
    ]
    if not goal_dists:
        return None  # no resoluble dins l'espai explorat

    min_solution_len = min(goal_dists)

    n_proc = len(degree_map)
    if n_proc == 0:
        return None

    avg_degree = sum(degree_map.values()) / n_proc

    start_key = puzzle.start.positions
    dead_ends = sum(
        1 for k, deg in degree_map.items()
        if deg == 1 and k != start_key and k[goal_piece_idx] != goal_pos
    )
    dead_end_ratio = dead_ends / n_proc

    log_n = math.log10(n + 1)
    path_density = (min_solution_len / log_n) if log_n > 0 else 0.0

    return {
        "nodes": n,
        "min_solution_len": min_solution_len,
        "avg_degree": round(avg_degree, 4),
        "dead_end_ratio": round(dead_end_ratio, 4),
        "path_density": round(path_density, 4),
        "solvable": True,
        "truncated": truncated,
    }


def fast_score(metrics: dict[str, Any]) -> float:
    """
    Puntuació ràpida [0–5] sense betweenness ni clustering.
    Pesos reescalats respecte eval.py eliminant els termes K i C
    (la seva contribució és negligible per grafs grans, i és cara de computar).
    """
    if not metrics.get("solvable", True):
        return 0.0

    n = int(metrics["nodes"])
    min_len = int(metrics["min_solution_len"])
    avg_degree = float(metrics["avg_degree"])
    dead_end_ratio = float(metrics["dead_end_ratio"])
    path_density = float(metrics["path_density"])

    def clamp(x: float) -> float:
        return max(0.0, min(1.0, x))

    len_term    = clamp(min_len / 80.0) * clamp(min_len / 10.0)
    size_term   = clamp(math.log10(n + 1) / 5.0) * clamp(n / 50.0)
    path_term   = clamp(path_density / 8.0)
    branch_term = clamp(1.0 - abs(avg_degree - 2.8) / 2.8)

    dead_penalty    = clamp(dead_end_ratio / 0.60)
    t_len  = 0.0 if min_len >= 10 else (10 - min_len) / 10.0
    t_size = 0.0 if n >= 50 else (50 - n) / 50.0
    trivial_penalty = clamp(0.5 * t_len + 0.5 * t_size)

    # Pesos: L=40%, P=20%, R=20%, S=20% (reescalat de 35/15/15/15 sense K i C)
    raw = (
        0.40 * len_term
        + 0.20 * path_term
        + 0.20 * branch_term
        + 0.20 * size_term
        - 0.15 * dead_penalty
        - 0.10 * trivial_penalty
    )
    return round(clamp(raw) * 5.0, 3)


# ---------------------------------------------------------------------------
# Generació d'un puzzle candidat
# ---------------------------------------------------------------------------


def generate_candidate(
    rng: random.Random,
    W: int,
    H: int,
    n_pieces: int,
    bfs_max_nodes: int = BFS_CAP,
    min_depth: int = 12,
    min_coverage: float = MIN_COVERAGE,
) -> Puzzle | None:
    """
    Genera un puzzle vàlid amb l'estratègia de scramble des del goal:
    1. Omple el taulell fins a assolir min_coverage (màx. n_pieces peces).
       Quan queda poc espai s'escullen formes petites per aprofitar-lo.
    2. BFS multi-font per explorar l'espai d'estats (màx. bfs_max_nodes).
    3. Start = estat en el top 20% de profunditat respecte el goal.
    Retorna None si no es pot generar un puzzle vàlid o si és trivial.

    Usar min_coverage ≥ 0.78 garanteix branching baix (~2–4 moviments per estat)
    i solucions llargues (≥ 15–40 moviments), factors clau per a puntuacions ≥ 2 ★.
    """
    walls: set[Coord] = set()
    occupied: set[Coord] = set()
    pieces_raw: list[list[Coord]] = []
    positions: list[Coord] = []

    total_cells = W * H - len(walls)
    target_occupied = int(total_cells * min_coverage)

    stagnation = 0
    while len(pieces_raw) < n_pieces and stagnation < 120:
        remaining_space = target_occupied - len(occupied)

        if remaining_space <= 0 and len(pieces_raw) >= 2:
            break  # cobertura assolida

        # Quan queda poc espai, limitem les formes per evitar superposicions
        max_shape_size = max(remaining_space, 1) if remaining_space <= 2 else 4
        eligible = [s for s in PIECE_SHAPES if len(s) <= max_shape_size]
        if not eligible:
            break

        shape = rng.choice(eligible)
        bw, bh = _bounding_box(shape)
        if bw > W or bh > H:
            stagnation += 1
            continue

        pos = _try_place_piece(rng, W, H, shape, occupied, walls)
        if pos is None:
            stagnation += 1
            continue

        stagnation = 0
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
    goal_state = State(tuple(positions))

    # La peça objectiu és la més gran (més maniobra necessària)
    piece_sizes = [(sum(1 for _ in p.coords), i) for i, p in enumerate(pieces)]
    goal_piece_idx = max(piece_sizes)[1]
    goal_pos: Coord = positions[goal_piece_idx]
    goals = ((goal_piece_idx, goal_pos),)

    try:
        puzzle_from_goal = Puzzle(
            W=W, H=H,
            walls=tuple(sorted(walls)),
            pieces=tuple(pieces),
            start=goal_state,
            goals=goals,
        )
    except ValueError:
        return None

    dist_map = _multi_source_bfs(
        puzzle_from_goal, goal_piece_idx, goal_pos, max_nodes=bfs_max_nodes
    )
    if not dist_map:
        return None

    max_depth = max(dist_map.values())
    if max_depth < min_depth:
        return None

    threshold = max_depth * 0.8
    deep_states = [
        k for k, depth in dist_map.items()
        if depth >= threshold and depth > 0
    ]
    if not deep_states:
        return None

    start_positions = list(rng.choice(deep_states))

    # Re-canonicalitzar: (forma, posició_start) pot diferir de (forma, posició_goal)
    indexed = sorted(range(len(pieces)), key=lambda i: (pieces[i], start_positions[i]))
    sorted_pieces  = [pieces[i] for i in indexed]
    sorted_start   = [start_positions[i] for i in indexed]
    new_goal_idx   = indexed.index(goal_piece_idx)
    new_goals      = ((new_goal_idx, goal_pos),)

    try:
        return Puzzle(
            W=W, H=H,
            walls=tuple(sorted(walls)),
            pieces=tuple(sorted_pieces),
            start=State(tuple(sorted_start)),
            goals=new_goals,
        )
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Pipeline principal
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
    Genera fins a n_candidates puzzles i retorna el millor que superi min_stars.

    Fase 1 (ràpida, tots els candidats): fast_evaluate + fast_score, sense graph-tool.
    Fase 2 (una sola vegada, el guanyador): build_graph (cap BFS_WIN) + compute_metrics.
    """
    rng = random.Random(seed)

    best_puzzle: Puzzle | None = None
    best_fast_stars: float = -1.0

    evaluated = 0
    skipped = 0
    max_attempts = max(n_candidates * 20, 100)

    for _ in range(max_attempts):
        if evaluated >= n_candidates:
            break

        candidate = generate_candidate(rng, W, H, n_pieces)
        if candidate is None:
            skipped += 1
            continue

        metrics = fast_evaluate(candidate)
        if metrics is None:
            skipped += 1
            continue

        evaluated += 1
        stars = fast_score(metrics)
        sol_len  = metrics["min_solution_len"]
        n_nodes  = metrics["nodes"]
        trunc    = "+" if metrics["truncated"] else ""

        print(
            f"  [{evaluated}/{n_candidates}] "
            f"sol={sol_len} mov | nodes={n_nodes}{trunc} | "
            f"puntuació_ràpida={stars:.2f}/5",
            file=sys.stderr,
        )

        if stars > best_fast_stars:
            best_fast_stars = stars
            best_puzzle = candidate

    total_attempts = evaluated + skipped
    print(
        f"\nResum: {evaluated} candidats avaluats, {skipped} descartats "
        f"({total_attempts} intents totals, màxim {max_attempts}).",
        file=sys.stderr,
    )

    if best_puzzle is None:
        return None

    # Fase 2: avaluació completa del guanyador amb graph-tool
    print(
        f"\nConstruint graf complet del millor candidat "
        f"(màx. {BFS_WIN} nodes, sense betweenness de vèrtexs)...",
        file=sys.stderr,
    )
    try:
        g = build_graph(best_puzzle, max_nodes=BFS_WIN)
        # BFS_WIN=15k nodes → betweenness en graph-tool triga ~1-2 s (acceptable)
        final_metrics = compute_metrics(g)
        final_stars   = score_from_metrics(final_metrics)
        final_metrics["stars"] = final_stars
    except Exception as e:
        print(f"  Avís: error en la construcció del graf: {e}", file=sys.stderr)
        final_stars = best_fast_stars
        final_metrics = {"stars": final_stars, "error": str(e)}

    if final_stars < min_stars:
        print(
            f"El millor candidat no supera el llindar de {min_stars} estrelles "
            f"(millor: {final_stars:.2f}, puntuació ràpida: {best_fast_stars:.2f}).",
            file=sys.stderr,
        )
        return None

    return best_puzzle, final_metrics


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera un puzzle Klotski aleatori de qualitat",
    )
    parser.add_argument("--width",  type=int, default=4, help="Amplada del taulell (per defecte 4)")
    parser.add_argument("--height", type=int, default=5, help="Alçada del taulell (per defecte 5)")
    parser.add_argument("--pieces", type=int, default=12, help="Nombre màxim de peces (per defecte 12; la generació s'atura per cobertura)")
    parser.add_argument(
        "--min-stars", type=float, default=1.5,
        help="Puntuació mínima acceptable [0–5] (per defecte 1.5)",
    )
    parser.add_argument(
        "--candidates", type=int, default=15,
        help="Nombre de candidats a avaluar (per defecte 15)",
    )
    parser.add_argument("--seed", type=int, default=None, help="Llavor aleatòria per reproduir resultats")
    parser.add_argument("--out",  default=None, help="Fitxer de sortida (per defecte puzzles/generated_<hash>.json)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print(
        f"Generant puzzles: {args.width}×{args.height}, "
        f"màx {args.pieces} peces (cobertura ≥{int(MIN_COVERAGE*100)}%), "
        f"{args.candidates} candidats, llindar {args.min_stars} estrelles...",
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
    print(f"Dimensions: {puzzle.W}×{puzzle.H}")
    print(f"Peces: {len(puzzle.pieces)}")
    print(f"Nodes del graf: {metrics.get('nodes', '?')}")
    print(f"Longitud solució mínima: {metrics.get('min_solution_len', '?')}")
    print(f"Puntuació: {metrics['stars']:.3f} / 5")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
