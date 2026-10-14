"""matplotlibベースの描画（ヘッドレスでも保存処理は呼べる形に）"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


def draw_and_save(out_path: str | Path, headless: bool = True) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if headless:
        import matplotlib
        matplotlib.use('Agg')
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(0, 1000)
    ax.set_ylim(0, 1000)
    ax.set_title("Draw mode (see README for usage)")
    nodes: list[dict[str, Any]] = []
    edges: list[tuple[int, int]] = []
    selected: int | None = None
    mode = 'add_node'

    def redraw():
        ax.clear()
        ax.set_xlim(0, 1000)
        ax.set_ylim(0, 1000)
        ax.set_title("left:add node / right:select / 'e':edge / 'n':node / 's':save")
        for i, j in edges:
            x1, y1 = nodes[i]['x'], nodes[i]['y']
            x2, y2 = nodes[j]['x'], nodes[j]['y']
            ax.plot([x1, x2], [y1, y2], 'k-', lw=1)
        for k, n in enumerate(nodes):
            c = 'red' if selected == k else 'blue'
            ax.plot(n['x'], n['y'], 'o', color=c, ms=8)
            ax.text(n['x']+5, n['y']+5, str(k), fontsize=8)
        fig.canvas.draw_idle()

    def on_press(event):
        if event.xdata is None or event.ydata is None:
            return
        if event.button == 1:
            if mode == 'add_node':
                nodes.append({'x': event.xdata, 'y': event.ydata, 'type': 'walk', 'role': None})
                redraw()
        elif event.button == 3:
            best = None
            bestd = 1e18
            for k, n in enumerate(nodes):
                d = math.hypot(n['x']-event.xdata, n['y']-event.ydata)
                if d < bestd and d < 20:
                    bestd = d
                    best = k
            if best is not None:
                nonlocal selected
                if mode == 'add_edge' and selected is not None:
                    if selected != best:
                        edges.append((selected, best))
                    selected = None
                else:
                    selected = best
                redraw()

    def on_key(event):
        nonlocal mode, selected
        if event.key == 'n':
            mode = 'add_node'
            selected = None
            redraw()
        elif event.key == 'e':
            mode = 'add_edge'
            redraw()
        elif event.key == 's':
            from .manual import ManualMap, ManualNode, ManualEdge, build_manual_map, save_manual_map
            mm = ManualMap(config={'map_id': 'map_drawn', 'source': 'manual'})
            for i, n in enumerate(nodes):
                mm.nodes.append(ManualNode(f'walk:{i}', n.get('type','walk'), n['x'], n['y'], role=n.get('role')))
            for i,j in edges:
                mm.edges.append(ManualEdge(f'walk:{i}', f'walk:{j}', difficulty=0.1))
            G = build_manual_map(mm)
            if G.graph.get('map_id') is None:
                G.graph['map_id'] = 'map_drawn'
            save_manual_map(mm, out_path)
            print(f'saved: {out_path}')
            plt.close()

    fig.canvas.mpl_connect('button_press_event', on_press)
    fig.canvas.mpl_connect('key_press_event', on_key)
    redraw()
    try:
        plt.show()
    except Exception:
        pass
