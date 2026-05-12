"""
Resol un puzzle trobant un camí mínim sobre el graf d'estats.

Ús:
    python src/solve.py <puzzle.json> [graph.graphml] [output.sol.json]

Comportament per defecte:
- Si no s'indica graph.graphml, fa servir <puzzle>.graphml
- Si no existeix, el construeix automàticament amb graph.py
- Si no s'indica output, desa a <puzzle>.sol.json
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportUnknownParameterType=false

from __future__ import annotations

import argparse
import importlib
import json
from collections import deque
from pathlib import Path
from typing import Any

from graph import StateKey, build_graph, state_key
from logic import DELTAS, Move, replay_moves
from puzzle import Puzzle, State


def key_from_vertex(state_prop: Any, vertex: Any, puzzle: Puzzle) -> StateKey:
    """Retorna la clau canònica d'estat per un vèrtex del graf."""
    return state_key(puzzle, state_prop[vertex])


def shortest_path_vertices(g: Any, start_v: Any, goals: set[int]) -> list[Any]:
    """BFS sobre el graf (no dirigit) i retorna el camí mínim a algun objectiu."""
    start_id = int(start_v)
    if start_id in goals:
        return [start_v]

    parent: dict[int, int] = {start_id: -1}
    queue: deque[int] = deque([start_id])
    found_goal: int | None = None

    while queue and found_goal is None:
        u = queue.popleft()
        u_v = g.vertex(u)
        for nb in u_v.all_neighbors():
            v = int(nb)
            if v in parent:
                continue
            parent[v] = u
            if v in goals:
                found_goal = v
                break
            queue.append(v)

    if found_goal is None:
        return []

    # Reconstrucció del camí (ids), de goal a start
    ids: list[int] = []
    cur = found_goal
    while cur != -1:
        ids.append(cur)
        cur = parent[cur]
    ids.reverse()
    return [g.vertex(i) for i in ids]


def infer_move(a: StateKey, b: StateKey) -> Move:
    """
Infereix el moviment que transforma l'estat a en l'estat b.

Assumeix que només una peça es mou i que el moviment és axial.
"""
    changed = [i for i, (pa, pb) in enumerate(zip(a, b)) if pa != pb]
    if len(changed) != 1:
        raise ValueError("No s'ha pogut inferir un moviment únic entre dos estats")

    i = changed[0]
    ax, ay = a[i]
    bx, by = b[i]
    dx, dy = bx - ax, by - ay

    if dx != 0 and dy != 0:
        raise ValueError("Moviment diagonal no vàlid")
    if dx == 0 and dy == 0:
        raise ValueError("No hi ha moviment entre estats")

    if dx > 0:
        direction = "E"
        dist = dx
    elif dx < 0:
        direction = "W"
        dist = -dx
    elif dy > 0:
        direction = "S"
        dist = dy
    else:
        direction = "N"
        dist = -dy

    # Coherència amb el mapa de direccions
    _ = DELTAS[direction]
    return (i, direction, int(dist))


def states_to_moves(path_keys: list[StateKey]) -> list[Move]:
    """Converteix una seqüència d'estats en seqüència de moviments."""
    moves: list[Move] = []
    for i in range(len(path_keys) - 1):
        moves.append(infer_move(path_keys[i], path_keys[i + 1]))
    return moves


def moves_to_solution_obj(moves: list[Move]) -> list[list[int | str]]:
    """Serialitza moviments al format de l'entrega: [peça, direcció]."""
    return [[piece_idx, direction] for piece_idx, direction, _dist in moves]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resol un puzzle trobant un camí mínim sobre el graf d'estats",
    )
    parser.add_argument("puzzle", help="Fitxer puzzle .json")
    parser.add_argument(
        "graphml",
        nargs="?",
        default=None,
        help="Fitxer .graphml (opcional, per defecte <puzzle>.graphml)",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Fitxer .sol.json de sortida (opcional)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    puzzle_path = Path(args.puzzle)
    graph_path = Path(args.graphml) if args.graphml else puzzle_path.with_suffix(".graphml")
    out_path = Path(args.output) if args.output else puzzle_path.with_suffix(".sol.json")

    puzzle = Puzzle.from_json(puzzle_path.read_text())

    gt = importlib.import_module("graph_tool.all")
    if graph_path.exists():
        print(f"Carregant graf: {graph_path}")
        g = gt.load_graph(str(graph_path))
    else:
        print(f"No existeix {graph_path}; construint graf...")
        g = build_graph(puzzle)
        g.save(str(graph_path))
        print(f"Graf guardat a: {graph_path}")

    state_prop = g.vp["state"]
    is_start_prop = g.vp["is_start"]
    is_goal_prop = g.vp["is_goal"]

    start_v = None
    goals: set[int] = set()
    for v in g.vertices():
        vid = int(v)
        if bool(is_start_prop[v]):
            start_v = v
        if bool(is_goal_prop[v]):
            goals.add(vid)

    if start_v is None:
        raise ValueError("El graf no conté node inicial (is_start)")
    if not goals:
        raise ValueError("El graf no conté cap node objectiu (is_goal)")

    v_path = shortest_path_vertices(g, start_v, goals)
    if len(v_path) == 0:
        raise ValueError("No hi ha cap camí des de l'inicial fins a un objectiu")

    key_path = [key_from_vertex(state_prop, v, puzzle) for v in v_path]
    moves = states_to_moves(key_path)

    # Verificació: reproduir la solució i comprovar que acaba al node final
    replayed = replay_moves(puzzle, moves)
    if state_key(puzzle, replayed[-1]) != key_path[-1]:
        raise ValueError("La solució reconstruïda no coincideix amb el camí del graf")

    out_path.write_text(json.dumps(moves_to_solution_obj(moves)))
    print(f"Solució: {len(moves)} moviments")
    print(f"Guardat: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
