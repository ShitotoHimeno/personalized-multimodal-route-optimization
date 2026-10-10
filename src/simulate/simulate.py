"""シミュレーション実行（オーケストレーション）モジュール。

makemap / plan_route / scoring / visualize を組み合わせて 1 回のシミュレーションを実行し、
ログ（``simulation/SIMxxx.json``）と図（``data/figures/``）を出力する。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from src.makemap import build_map
from src.plan_route import find_pareto_solutions, weighted_scalarization
from src.scoring import score_solutions, select_recommended
from src.visualize import plot_node_map, plot_pareto_front

_DEFAULT_CONFIG = "config/map_config/map_config.json"
_DEFAULT_SCENARIOS = "config/scenarios/scenarios.json"
_DEFAULT_OUTPUT = "simulation"
_DEFAULT_FIGURES = "data/figures"
_OD_SEED = 20261010


def _load_json(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _next_simulation_id(output_dir: str | Path) -> str:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    idx = 0
    for p in output.glob("SIM*.json"):
        try:
            idx = max(idx, int(p.stem[len("SIM"):]))
        except ValueError:
            continue
    return f"SIM{idx + 1:03d}"


def _choose_od(nodes: dict[str, dict[str, Any]], seed: int) -> tuple[str, str]:
    walk_ids = [nid for nid, n in nodes.items() if n["type"] == "walk"]
    rng = np.random.default_rng(seed)
    a, b = rng.choice(len(walk_ids), size=2, replace=False)
    return walk_ids[int(a)], walk_ids[int(b)]


def _count_removed_walk_edges(G, g_max: float) -> int:
    return sum(
        1 for _, _, d in G.edges(data=True)
        if d.get("kind") == "walk" and d["difficulty"] > g_max + 1e-12
    )


def run_simulation(
    config_path: str | Path = _DEFAULT_CONFIG,
    scenario_path: str | Path = _DEFAULT_SCENARIOS,
    scenario_id: str = "SC005",
    depart_time: float = 28800.0,
    od_seed: int = _OD_SEED,
    allowed_modes: Iterable[str] = ("walk", "taxi", "bus"),
    output_dir: str | Path = _DEFAULT_OUTPUT,
    figure_dir: str | Path = _DEFAULT_FIGURES,
) -> dict[str, Any]:
    """シミュレーションを 1 回実行してログを返す。"""
    t0 = time.perf_counter()

    # 1. 環境情報（ノードマップ）
    G = build_map(config_path)
    map_id = G.graph["map_id"]

    # 2. 個人・オーダー情報（シナリオ）
    scenarios = _load_json(scenario_path)["scenarios"]
    scenario = next(s for s in scenarios if s["scenario_id"] == scenario_id)
    profile = scenario["profile"]
    tc = scenario["time_constraint"]

    # 3. OD 決定（徒歩ノードからランダム2点、シード固定）
    source, target = _choose_od(G.nodes(), od_seed)
    if source == target:
        raise ValueError("OD が同一ノードになりました。od_seed を変えてください。")

    removed_walk_edges = _count_removed_walk_edges(G, profile["walking_ability_g_max"])

    # 4. 多目的経路計画（分解法でパレート解を導出, 決定 #16, #17）
    solutions = find_pareto_solutions(
        G,
        source=source,
        target=target,
        depart_time=depart_time,
        g_max=profile["walking_ability_g_max"],
        walk_speed_mps=profile["walking_speed_mps"],
        t_max=tc.get("t_max_budget_sec"),
        time_type=tc["type"],
        allowed_modes=allowed_modes,
    )
    feasible = len(solutions) > 0

    # 5. スコアリング（正規化・重み付け・推奨順位）
    ranked = score_solutions(
        solutions,
        w_t=profile["arrival_weight_w_t"],
        w_e=profile["walking_motivation_w_e"],
        s=profile["effort_direction_s"],
        lambda_=tc.get("delay_penalty_lambda") or 1.0,
        time_type=tc["type"],
    )
    selected = select_recommended(ranked)

    # 重み付きスカラー化（決定 #5）の参照結果
    scalar = (
        {str(round(a, 3)): s["solution_id"] for a, s in weighted_scalarization(solutions).items()}
        if solutions else {}
    )

    t1 = time.perf_counter()

    # 6. ログ作成
    sim_id = _next_simulation_id(output_dir)
    log = {
        "simulation_id": sim_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "map_id": map_id,
        "scenario_id": scenario_id,
        "od": {"departure": source, "arrival": target},
        "profile": profile,
        "time_constraint": tc,
        "depart_time_sec": depart_time,
        "allowed_modes": list(allowed_modes),
        "od_seed": od_seed,
        "feasible": feasible,
        "removed_walk_edges": removed_walk_edges,
        "result": {
            "pareto_front": [
                {
                    "solution_id": s["solution_id"],
                    "f1_sec": s["f1_sec"],
                    "f2": s["f2"],
                    "d_sec": s["d_sec"],
                    "u": s["u"],
                    "rank": s.get("rank"),
                    "path": s["path"],
                }
                for s in ranked
            ],
            "selected": selected["solution_id"] if selected else None,
            "weighted_scalarization": scalar,
        },
        "timing": {"compute_sec": round(t1 - t0, 4)},
    }

    # 7. 出力（ログ + 図）
    out_path = Path(output_dir) / f"{sim_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"saved: {out_path}")

    if feasible:
        fig_map = Path(figure_dir) / f"{sim_id}_map.png"
        fig_pareto = Path(figure_dir) / f"{sim_id}_pareto.png"
        selected_path = selected["path"] if selected else None
        plot_node_map(G, fig_map, highlight_path=selected_path)
        plot_pareto_front(ranked, fig_pareto, selected=selected)

    return log