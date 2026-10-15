"""``python -m src.analyze`` でシミュレーションログを CSV に集計する CLI。"""

from __future__ import annotations

import argparse

from .analyze import export_csv


def main() -> None:
    p = argparse.ArgumentParser(description="シミュレーションログを CSV に集計する")
    p.add_argument("--input", default="simulation", help="SIMxxx.json のあるディレクトリ")
    p.add_argument("--out", default="data/summary", help="CSV の出力先ディレクトリ")
    argv = p.parse_args()

    counts = export_csv(input_dir=argv.input, output_dir=argv.out)
    print(f"saved: {argv.out}/simulations.csv ({counts['n_simulations']} 行)")
    print(f"saved: {argv.out}/solutions.csv ({counts['n_solutions']} 行)")


if __name__ == "__main__":
    main()
