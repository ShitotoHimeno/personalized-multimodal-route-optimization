"""``python -m src.simulate`` でシミュレーションを実行する CLI。"""

from __future__ import annotations

import argparse
import sys

from .simulate import run_simulation
from src.util import InsufficientResourcesError


def main() -> None:
    p = argparse.ArgumentParser(description="シミュレーションを 1 回実行する")
    p.add_argument("--scenario", default="SC005", help="シナリオID（デフォルト: SC005）")
    p.add_argument("--depart", type=float, default=28800.0, help="出発時刻（秒）")
    p.add_argument("--od-seed", type=int, default=20261010, help="OD 選定用シード")
    p.add_argument("--config", default="config/map_config/map_config.json")
    p.add_argument("--scenarios", default="config/scenarios/scenarios.json")
    p.add_argument("--output", default="simulation")
    p.add_argument("--figures", default="data/figures")
    p.add_argument(
        "--no-capacity-check",
        action="store_true",
        help="計算能力の事前見積り・実行中監視を無効化する",
    )
    p.add_argument(
        "--time-budget",
        type=float,
        default=None,
        help="許容する計算時間 [秒]。見積り/実行がこれを超えそうなら早期に中断する",
    )
    p.add_argument(
        "--mem-fraction",
        type=float,
        default=0.8,
        help="メモリ上限の割合（総メモリに対する割合, 既定 0.8）",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="事前見積りで critical でも中断せず実行する",
    )
    p.add_argument(
        "--manual-graph",
        default=None,
        help="手動作成したグラフ（pickle）を読み込む",
    )
    argv = p.parse_args()

    mg = None
    if argv.manual_graph:
        import pickle
        from pathlib import Path
        with open(argv.manual_graph, "rb") as f:
            mg = pickle.load(f)

    try:
        log = run_simulation(
            config_path=argv.config,
            scenario_path=argv.scenarios,
            scenario_id=argv.scenario,
            depart_time=argv.depart,
            od_seed=argv.od_seed,
            output_dir=argv.output,
            figure_dir=argv.figures,
            capacity_check=not argv.no_capacity_check,
            time_budget_sec=argv.time_budget,
            mem_fraction_limit=argv.mem_fraction,
            force=argv.force,
            manual_graph=mg,
        )
    except InsufficientResourcesError as e:
        print(f"[error] {e}", file=sys.stderr)
        print(
            "ヒント: --force で強制実行 / --time-budget・--mem-fraction で上限を調整",
            file=sys.stderr,
        )
        raise SystemExit(2)
    selected = log["result"]["selected"]
    print(
        f"{log['simulation_id']}: {log['scenario_id']} "
        f"feasible={log['feasible']} パレート解={len(log['result']['pareto_front'])} "
        f"selected={selected} 計算時間={log['timing']['compute_sec']}s"
    )


if __name__ == "__main__":
    main()