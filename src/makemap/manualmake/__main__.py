"""手動マップ作成の簡易CLI。"""

from __future__ import annotations

import argparse
from pathlib import Path

from .manual import ManualMap, ManualNode, ManualEdge, build_manual_map, save_manual_map


def main() -> None:
    p = argparse.ArgumentParser(description="手動マップ作成")
    sub = p.add_subparsers(dest='cmd')
    p_draw = sub.add_parser('draw', help='マウスで描画')
    p_draw.add_argument('--out', required=True)
    p_tpl = sub.add_parser('template', help='テンプレート生成')
    p_tpl.add_argument('--out', required=True)
    p_tpl.add_argument('--map-id', default='map_manual')
    args = p.parse_args()

    if args.cmd == 'draw':
        try:
            from .draw_matplotlib import draw_and_save
            draw_and_save(args.out, headless=False)
        except Exception:
            from .draw import draw_and_save
            draw_and_save(args.out)
        return
    if args.cmd == 'template':
        mm = ManualMap(config={'map_id': args.map_id, 'source': 'manual'})
        mm.nodes.append(ManualNode('walk:0', 'walk', 0, 0, role='start'))
        mm.nodes.append(ManualNode('walk:1', 'walk', 100, 0))
        mm.nodes.append(ManualNode('walk:2', 'walk', 100, 100, role='destination'))
        mm.edges.append(ManualEdge('walk:0', 'walk:1', difficulty=0.1))
        mm.edges.append(ManualEdge('walk:1', 'walk:2', difficulty=0.1))
        G = build_manual_map(mm)
        if G.graph.get('map_id') is None:
            G.graph['map_id'] = args.map_id
        save_manual_map(mm, args.out)
        print(f'テンプレートを保存しました: {args.out}')
        return

    p.print_help()


if __name__ == '__main__':
    main()
