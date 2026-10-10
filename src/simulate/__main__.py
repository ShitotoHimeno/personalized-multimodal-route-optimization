"""``python -m src.simulate`` でシミュレーションを実行する CLI。"""

from __future__ import annotations

import argparse

from .simulate import run_simulation


def main() -> None:
    p = argparse.ArgumentParser(description="シミュレーションを 1 回実行する")
    p.add_argument("--scenario", default="SC005", help="シナリオID（デフォルト: SC005）")
    p.add_argument("--depart", type=float, default=28800.0, help="出発時刻（秒）")
    p.add_argument("--od-seed", type=int, default=20261010, help="OD 選定用シード")
    p.add_argument("--config", default="config/map_config/map_config.json")
    p.add_argument("--scenarios", default="config/scenarios/scenarios.json")
    p.add_argument("--output", default="simulation")
    p.add_argument("--figures", default="data/figures")
    argv = p.parse_args()

    log = run_simulation(
        config_path=argv.config,
        scenario_path=argv.scenarios,
        scenario_id=argv.scenario,
        depart_time=argv.depart,
        od_seed=argv.od_seed,
        output_dir=argv.output,
        figure_dir=argv.figures,
    )
    selected = log["result"]["selected"]
    print(
        f"{log['simulation_id']}: {log['scenario_id']} "
        f"feasible={log['feasible']} パレート解={len(log['result']['pareto_front'])} "
        f"selected={selected} 計算時間={log['timing']['compute_sec']}s"
    )


if __name__ == "__main__":
    main()