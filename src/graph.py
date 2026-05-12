"""
Construeix el graf d'estats d'un puzzle i el desa en format GraphML.

Cada node del graf és un estat accessible des de l'estat inicial.
Cada aresta connecta dos estats separats per un sol moviment vàlid.

Ús:
    python src/graph.py <puzzle.json> [output.graphml]
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportUnknownParameterType=false, reportUnnecessaryIsInstance=false

from __future__ import annotations

import argparse
import importlib
import json
from collections import deque
from pathlib import Path
from typing import Any

from logic import apply_move, is_goal, possible_moves
from puzzle import Coord, Puzzle, State

StateKey = tuple[Coord, ...]


def state_key(
    _puzzle: Puzzle,
    state_like: State | str | list[object] | tuple[object, ...],
) -> StateKey:
    """
Retorna una clau hashable canònica d'un estat.

Accepta:
- `State`
- string JSON amb format `[[x,y], ...]`
- llista/tupla de posicions
"""
    if isinstance(state_like, State):
        return state_like.positions

    if isinstance(state_like, str):
        parsed = json.loads(state_like)
        return tuple((int(p[0]), int(p[1])) for p in parsed)

    if isinstance(state_like, (list, tuple)):
        result: list[Coord] = []
        for p in state_like:
            if not isinstance(p, (list, tuple)) or len(p) != 2:
                raise TypeError("Posicio d'estat invalida; s'esperava [x, y]")
            result.append((int(p[0]), int(p[1])))
        return tuple(result)

    raise TypeError(f"Tipus d'estat no suportat: {type(state_like)!r}")


def key_to_state(key: StateKey) -> State:
    """Converteix la clau canònica a objecte `State`."""
    return State(key)


def build_graph(puzzle: Puzzle) -> Any:
    """
Construeix el graf d'estats accessibles des de `puzzle.start` amb BFS.

El graf inclou metadades:
- `g.gp["puzzle"]`: JSON del puzzle
- `g.vp["state"]`: estat serialitzat en JSON
- `g.vp["is_start"]`: node inicial
- `g.vp["is_goal"]`: node objectiu
"""
    gt = importlib.import_module("graph_tool.all")
    g = gt.Graph(directed=False)

    state_prop = g.new_vertex_property("string")
    is_start_prop = g.new_vertex_property("bool")
    is_goal_prop = g.new_vertex_property("bool")

    g.vp["state"] = state_prop
    g.vp["is_start"] = is_start_prop
    g.vp["is_goal"] = is_goal_prop

    puzzle_prop = g.new_graph_property("string")
    puzzle_prop.set_value(puzzle.to_json())
    g.gp["puzzle"] = puzzle_prop

    start_key = state_key(puzzle, puzzle.start)
    start_v = g.add_vertex()
    state_prop[start_v] = json.dumps([list(p) for p in start_key])
    is_start_prop[start_v] = True
    is_goal_prop[start_v] = is_goal(puzzle, key_to_state(start_key))

    key_to_vertex: dict[StateKey, Any] = {start_key: start_v}
    queue: deque[StateKey] = deque([start_key])

    while queue:
        current_key = queue.popleft()
        current_state = key_to_state(current_key)
        current_v = key_to_vertex[current_key]

        for move in possible_moves(puzzle, current_state):
            next_state = apply_move(puzzle, current_state, move)
            next_key = state_key(puzzle, next_state)

            if next_key not in key_to_vertex:
                next_v = g.add_vertex()
                key_to_vertex[next_key] = next_v
                queue.append(next_key)

                state_prop[next_v] = json.dumps([list(p) for p in next_key])
                is_start_prop[next_v] = False
                is_goal_prop[next_v] = is_goal(puzzle, next_state)

            next_v = key_to_vertex[next_key]
            if g.edge(current_v, next_v) is None:
                g.add_edge(current_v, next_v)

    return g


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Construeix el graf d'estats d'un puzzle i el desa en GraphML",
    )
    parser.add_argument("puzzle", help="Fitxer puzzle .json")
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Fitxer de sortida .graphml (opcional)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    puzzle_path = Path(args.puzzle)
    out_path = Path(args.output) if args.output else puzzle_path.with_suffix(".graphml")

    puzzle = Puzzle.from_json(puzzle_path.read_text())

    print(f"Construint graf per: {puzzle_path}")
    g = build_graph(puzzle)
    print(f"Nodes: {g.num_vertices()}  Arestes: {g.num_edges()}")

    g.save(str(out_path))
    print(f"Guardat: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
