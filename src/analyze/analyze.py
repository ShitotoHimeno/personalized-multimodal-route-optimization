"""シミュレーションログ（``simulation/SIMxxx.json``）を CSV に集計するモジュール。

全実行の JSON ログを走査し、Excel 等で確認しやすい 2 種類の派生 CSV を出力する。

- ``simulations.csv``: 1 実行 = 1 行（概要。scenario_id・feasible・選択解など）
- ``solutions.csv``: 1 パレート解 = 1 行（詳細。各解の目的関数値・rank・経路）

元の ``SIMxxx.json`` は真実のソースとしてそのまま保持し、CSV は毎回生成し直せる
派生ビューとして扱う。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

_DEFAULT_INPUT = "simulation"
_DEFAULT_OUTPUT = "data/summary"
_PATH_SEP = " > "

_SIM_FIELDS = [
    "simulation_id",
    "timestamp",
    "map_id",
    "scenario_id",
    "departure",
    "arrival",
    "feasible",
    "removed_walk_edges",
    "n_pareto",
    "selected_id",
    "selected_f1_sec",
    "selected_f2",
    "selected_d_sec",
    "selected_u",
    "compute_sec",
]

_SOL_FIELDS = [
    "simulation_id",
    "map_id",
    "scenario_id",
    "solution_id",
    "f1_sec",
    "f2",
    "d_sec",
    "u",
    "rank",
    "is_selected",
    "path",
]


def load_logs(input_dir: str | Path = _DEFAULT_INPUT) -> list[dict[str, Any]]:
    """``input_dir`` 内の ``SIM*.json`` を番号順に読み込んで返す。"""
    paths = sorted(Path(input_dir).glob("SIM*.json"), key=_sim_sort_key)
    logs: list[dict[str, Any]] = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            logs.append(json.load(f))
    return logs


def _sim_sort_key(path: Path) -> tuple[int, int | str]:
    stem = path.stem
    try:
        return (0, int(stem[len("SIM"):]))
    except ValueError:
        return (1, stem)


def _as_flag(value: Any) -> int | str:
    if value is None:
        return ""
    return 1 if value else 0


def _selected_solution(result: dict[str, Any]) -> dict[str, Any] | None:
    selected_id = result.get("selected")
    if selected_id is None:
        return None
    for sol in result.get("pareto_front", []):
        if sol.get("solution_id") == selected_id:
            return sol
    return None


def _format_path(path: Any) -> str:
    if not path:
        return ""
    return _PATH_SEP.join(str(node) for node in path)


def flatten_simulation(log: dict[str, Any]) -> dict[str, Any]:
    """1 実行のログを概要 1 行へ平坦化する。"""
    result = log.get("result", {})
    pareto = result.get("pareto_front", [])
    selected = _selected_solution(result)
    od = log.get("od", {})
    return {
        "simulation_id": log.get("simulation_id"),
        "timestamp": log.get("timestamp"),
        "map_id": log.get("map_id"),
        "scenario_id": log.get("scenario_id"),
        "departure": od.get("departure"),
        "arrival": od.get("arrival"),
        "feasible": _as_flag(log.get("feasible")),
        "removed_walk_edges": log.get("removed_walk_edges"),
        "n_pareto": len(pareto),
        "selected_id": result.get("selected"),
        "selected_f1_sec": selected.get("f1_sec") if selected else None,
        "selected_f2": selected.get("f2") if selected else None,
        "selected_d_sec": selected.get("d_sec") if selected else None,
        "selected_u": selected.get("u") if selected else None,
        "compute_sec": log.get("timing", {}).get("compute_sec"),
    }


def flatten_solutions(log: dict[str, Any]) -> list[dict[str, Any]]:
    """1 実行のログを解ごとの複数行へ平坦化する。"""
    result = log.get("result", {})
    selected_id = result.get("selected")
    rows: list[dict[str, Any]] = []
    for sol in result.get("pareto_front", []):
        rows.append(
            {
                "simulation_id": log.get("simulation_id"),
                "map_id": log.get("map_id"),
                "scenario_id": log.get("scenario_id"),
                "solution_id": sol.get("solution_id"),
                "f1_sec": sol.get("f1_sec"),
                "f2": sol.get("f2"),
                "d_sec": sol.get("d_sec"),
                "u": sol.get("u"),
                "rank": sol.get("rank"),
                "is_selected": 1 if sol.get("solution_id") == selected_id else 0,
                "path": _format_path(sol.get("path")),
            }
        )
    return rows


def _write_csv(rows: list[dict[str, Any]], path: str | Path, fieldnames: list[str]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Excel での文字化けを避けるため BOM 付き UTF-8 で出力する。
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_csv(
    input_dir: str | Path = _DEFAULT_INPUT,
    output_dir: str | Path = _DEFAULT_OUTPUT,
) -> dict[str, int]:
    """``SIM*.json`` を集計して ``simulations.csv`` と ``solutions.csv`` を出力する。"""
    logs = load_logs(input_dir)
    sim_rows = [flatten_simulation(log) for log in logs]
    sol_rows = [row for log in logs for row in flatten_solutions(log)]

    _write_csv(sim_rows, Path(output_dir) / "simulations.csv", _SIM_FIELDS)
    _write_csv(sol_rows, Path(output_dir) / "solutions.csv", _SOL_FIELDS)

    return {"n_simulations": len(sim_rows), "n_solutions": len(sol_rows)}
