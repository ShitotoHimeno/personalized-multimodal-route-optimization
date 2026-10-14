"""CLI for drawing map"""

from __future__ import annotations

import argparse
from .draw import draw_and_save


def main() -> None:
    p = argparse.ArgumentParser(description="マウスでノード・エッジを描画してマップ作成")
    p.add_argument("--out", required=True, help="出力先（manual_map.pkl）")
    args = p.parse_args()
    draw_and_save(args.out)


if __name__ == "__main__":
    main()
