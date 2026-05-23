"""
Avalua un puzzle a partir del seu graf d'estats.

Ús:
    python src/eval.py <puzzle.json> [graph.graphml]
    python src/eval.py <puzzle.json> [graph.graphml] --json
    python src/eval.py <puzzle.json> [graph.graphml] --with-betweenness

Comportament per defecte:
- Si no s'indica graph.graphml, fa servir <puzzle>.graphml
- Si no existeix, el construeix automàticament amb graph.py
- La betweenness de vèrtexs es calcula sempre (per a la puntuació)
- --with-betweenness afegeix la betweenness d'arestes (opcional, més detall)
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportUnknownParameterType=false

from __future__ import annotations

import argparse
import importlib
import json
import math
from pathlib import Path
from typing import Any

from graph import build_graph
from puzzle import Puzzle


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Avalua un puzzle a partir del graf d'estats",
    )
    parser.add_argument("puzzle", help="Fitxer puzzle .json")
    parser.add_argument(
        "graphml",
        nargs="?",
        default=None,
        help="Fitxer .graphml (opcional, per defecte <puzzle>.graphml)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Mostra la sortida en format JSON",
    )
    parser.add_argument(
        "--with-betweenness",
        action="store_true",
        help="Inclou max edge betweenness a la sortida (la de vèrtexs ja es calcula)",
    )
    return parser.parse_args()


# Llindars de la heurística de puntuació (veure score_from_metrics).
MIN_SOLUTION_SOFT = 10
MIN_NODES_SOFT = 50
OPTIMAL_AVG_DEGREE = 2.8
BETWEENNESS_NORM_FACTOR = 0.15


def _goal_distances(dist_map: Any, goal_vertices: list[Any], n: int) -> list[int]:
    """Distàncies start -> goal; graph-tool usa n per a inaccessibles."""
    return [int(dist_map[v]) for v in goal_vertices]


def compute_metrics(g: Any, with_betweenness: bool = False) -> dict[str, Any]:
    """Calcula mètriques del graf útils per avaluar un puzzle."""
    gt = importlib.import_module("graph_tool.all")

    n = int(g.num_vertices())
    m = int(g.num_edges())
    avg_degree = (2.0 * m / n) if n > 0 else 0.0

    is_start = g.vp["is_start"]
    is_goal = g.vp["is_goal"]

    start_v = None
    goal_vertices: list[Any] = []
    for v in g.vertices():
        if bool(is_start[v]):
            start_v = v
        if bool(is_goal[v]):
            goal_vertices.append(v)

    if start_v is None:
        raise ValueError("El graf no conté node inicial (is_start)")
    if not goal_vertices:
        raise ValueError("El graf no conté nodes objectiu (is_goal)")

    dist_map = gt.shortest_distance(g, source=start_v)
    goal_dists = _goal_distances(dist_map, goal_vertices, n)
    solvable = all(d < n for d in goal_dists)
    min_solution_len = min(goal_dists) if solvable else -1

    dead_ends = 0
    for v in g.vertices():
        d = int(v.out_degree())
        if d == 1 and (not bool(is_start[v])) and (not bool(is_goal[v])):
            dead_ends += 1
    dead_end_ratio = (dead_ends / n) if n > 0 else 0.0

    comp_map, hist = gt.label_components(g)
    _ = comp_map
    connected_components = int(len(hist))

    clustering_coeff, clustering_std = gt.global_clustering(g)

    log_nodes = math.log10(n + 1)
    path_density = (
        (min_solution_len / log_nodes) if solvable and log_nodes > 0 else 0.0
    )

    max_v_btw = 0.0
    if n > 0:
        v_btw, e_btw = gt.betweenness(g)
        max_v_btw = max(float(v_btw[v]) for v in g.vertices())
        if with_betweenness and m > 0:
            max_e_btw = max(float(e_btw[e]) for e in g.edges())
        else:
            max_e_btw = None
    else:
        max_e_btw = None

    metrics: dict[str, Any] = {
        "nodes": n,
        "edges": m,
        "goals": len(goal_vertices),
        "solvable": solvable,
        "min_solution_len": min_solution_len,
        "path_density": round(path_density, 6),
        "avg_degree": round(avg_degree, 6),
        "dead_ends": dead_ends,
        "dead_end_ratio": round(dead_end_ratio, 6),
        "connected_components": connected_components,
        "global_clustering": round(float(clustering_coeff), 6),
        "global_clustering_std": round(float(clustering_std), 6),
        "max_vertex_betweenness": round(max_v_btw, 6),
        "components_note": "Normalment 1 en grafs construits des de l'estat inicial",
    }

    if with_betweenness and max_e_btw is not None:
        metrics["max_edge_betweenness"] = round(max_e_btw, 6)

    return metrics


def compute_score_terms(metrics: dict[str, Any]) -> dict[str, float]:
    """
    Desglossa la puntuació en termes normalitzats [0, 1] i raw [0, 1].

    Heurística v2: dificultat, densitat del camí, colls d'ampolla,
    ramificació en banda mitjana, mida (amb sòls), clustering, penalitzacions.
    """
    if not metrics.get("solvable", True):
        return {
            "len_term": 0.0,
            "path_density_term": 0.0,
            "bottleneck_term": 0.0,
            "branch_term": 0.0,
            "size_term": 0.0,
            "clustering_term": 0.0,
            "dead_end_penalty": 0.0,
            "trivial_penalty": 1.0,
            "raw": 0.0,
        }

    n = int(metrics["nodes"])
    min_len = int(metrics["min_solution_len"])
    avg_degree = float(metrics["avg_degree"])
    dead_end_ratio = float(metrics["dead_end_ratio"])
    clustering = float(metrics["global_clustering"])
    path_density = float(metrics.get("path_density", 0.0))
    max_v_btw = float(metrics.get("max_vertex_betweenness", 0.0))

    log_nodes = math.log10(n + 1)
    len_term = clamp01(min_len / 80.0) * clamp01(min_len / MIN_SOLUTION_SOFT)
    size_term = clamp01(log_nodes / 5.0) * clamp01(n / MIN_NODES_SOFT)

    path_density_term = clamp01(path_density / 8.0)

    btw_denom = max(1.0, n * BETWEENNESS_NORM_FACTOR)
    bottleneck_term = clamp01(max_v_btw / btw_denom)

    branch_term = clamp01(1.0 - abs(avg_degree - OPTIMAL_AVG_DEGREE) / OPTIMAL_AVG_DEGREE)

    clustering_term = clamp01(clustering / 0.25)
    dead_end_penalty = clamp01(dead_end_ratio / 0.60)

    t_len = 0.0 if min_len >= MIN_SOLUTION_SOFT else (MIN_SOLUTION_SOFT - min_len) / MIN_SOLUTION_SOFT
    t_size = 0.0 if n >= MIN_NODES_SOFT else (MIN_NODES_SOFT - n) / MIN_NODES_SOFT
    trivial_penalty = clamp01(0.5 * t_len + 0.5 * t_size)

    raw = (
        0.35 * len_term
        + 0.15 * path_density_term
        + 0.15 * bottleneck_term
        + 0.15 * branch_term
        + 0.15 * size_term
        + 0.05 * clustering_term
        - 0.15 * dead_end_penalty
        - 0.10 * trivial_penalty
    )

    return {
        "len_term": round(len_term, 6),
        "path_density_term": round(path_density_term, 6),
        "bottleneck_term": round(bottleneck_term, 6),
        "branch_term": round(branch_term, 6),
        "size_term": round(size_term, 6),
        "clustering_term": round(clustering_term, 6),
        "dead_end_penalty": round(dead_end_penalty, 6),
        "trivial_penalty": round(trivial_penalty, 6),
        "raw": round(clamp01(raw), 6),
    }


def score_from_metrics(metrics: dict[str, Any]) -> float:
    """Combina mètriques en una puntuació [0, 5]."""
    terms = compute_score_terms(metrics)
    return round(terms["raw"] * 5.0, 3)


def main() -> int:
    args = parse_args()

    puzzle_path = Path(args.puzzle)
    graph_path = Path(args.graphml) if args.graphml else puzzle_path.with_suffix(".graphml")

    puzzle = Puzzle.from_json(puzzle_path.read_text())
    gt = importlib.import_module("graph_tool.all")

    if graph_path.exists():
        g = gt.load_graph(str(graph_path))
    else:
        g = build_graph(puzzle)
        g.save(str(graph_path))

    metrics = compute_metrics(g, with_betweenness=args.with_betweenness)
    score_terms = compute_score_terms(metrics)
    metrics["score_terms"] = score_terms
    metrics["stars"] = score_from_metrics(metrics)

    if args.json:
        print(json.dumps(metrics, indent=2))
        return 0

    print(f"Puzzle: {puzzle_path}")
    print(f"Graf: {graph_path}")
    print()
    print(f"Resoluble: {metrics['solvable']}")
    print(f"Nodes: {metrics['nodes']}")
    print(f"Arestes: {metrics['edges']}")
    print(f"Objectius: {metrics['goals']}")
    print(f"Longitud mínima solució: {metrics['min_solution_len']}")
    print(f"Densitat camí (len/log n): {metrics['path_density']}")
    print(f"Grau mitjà: {metrics['avg_degree']}")
    print(f"Dead-ends: {metrics['dead_ends']} ({metrics['dead_end_ratio']})")
    print(f"Components connexos: {metrics['connected_components']}")
    print(f"Clustering global: {metrics['global_clustering']}")
    print(f"Max vertex betweenness: {metrics['max_vertex_betweenness']}")
    if args.with_betweenness and "max_edge_betweenness" in metrics:
        print(f"Max edge betweenness: {metrics['max_edge_betweenness']}")
    print()
    print("Termes de puntuació (0-1):")
    for key, value in score_terms.items():
        print(f"  {key}: {value}")
    print(f"Puntuació estimada: {metrics['stars']} / 5")
    print(f"Nota: {metrics['components_note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
