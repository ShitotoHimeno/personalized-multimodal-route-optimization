"""簡易描画UI（matplotlibを使ってマウスでノード・エッジを作成）"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


@dataclass
class DrawState:
    nodes: list[dict[str, Any]]
    edges: list[tuple[int, int]]
    next_id: int
    selected: int | None
    mode: str  # 'add_node' or 'add_edge'
    last_click: tuple[float, float] | None


def draw_and_save(out_path: str | Path) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(0, 1000)
    ax.set_ylim(0, 1000)
    ax.set_title("Draw: left click=add node, right click/select for edge, 'e'=edge mode, 'n'=node mode, 's'=save")
    state = DrawState(nodes=[], edges=[], next_id=0, selected=None, mode='add_node', last_click=None)

    def redraw():
        ax.clear()
        ax.set_xlim(0, 1000)
        ax.set_ylim(0, 1000)
        ax.set_title("Draw: left click=add node, right click/select, 'e'=edge mode, 'n'=node mode, 's'=save")
        for i, j in state.edges:
            x1, y1 = state.nodes[i]['x'], state.nodes[i]['y']
            x2, y2 = state.nodes[j]['x'], state.nodes[j]['y']
            ax.plot([x1, x2], [y1, y2], 'k-', lw=1)
        for k, n in enumerate(state.nodes):
            c = 'red' if state.selected == k else 'blue'
            ax.plot(n['x'], n['y'], 'o', color=c, ms=8)
            ax.text(n['x']+5, n['y']+5, str(k), fontsize=8)
        fig.canvas.draw_idle()

    def on_press(event):
        if event.xdata is None or event.ydata is None:
            return
        if event.button == 1:  # left
            if state.mode == 'add_node':
                state.nodes.append({'x': event.xdata, 'y': event.ydata, 'type': 'walk', 'role': None})
                state.next_id += 1
                redraw()
        elif event.button == 3:  # right
            # select nearest
            best = None
            bestd = 1e18
            for k, n in enumerate(state.nodes):
                d = math.hypot(n['x']-event.xdata, n['y']-event.ydata)
                if d < bestd and d < 20:
                    bestd = d
                    best = k
            if best is not None:
                if state.mode == 'add_edge' and state.selected is not None:
                    if state.selected != best:
                        state.edges.append((state.selected, best))
                    state.selected = None
                else:
                    state.selected = best
                redraw()

    def on_key(event):
        if event.key == 'n':
            state.mode = 'add_node'
            state.selected = None
            redraw()
        elif event.key == 'e':
            state.mode = 'add_edge'
            redraw()
        elif event.key == 's':
            # save
            from .manual import ManualMap, ManualNode, ManualEdge, build_manual_map, save_manual_map
            mm = ManualMap(config={'map_id': 'map_drawn', 'source': 'manual'})
            for i, n in enumerate(state.nodes):
                nid = f'walk:{i}'
                mm.nodes.append(ManualNode(nid, n.get('type','walk'), n['x'], n['y'], role=n.get('role')))
            for i,j in state.edges:
                mm.edges.append(ManualEdge(f'walk:{i}', f'walk:{j}', difficulty=0.1))
            build_manual_map(mm)
            save_manual_map(mm, out_path)
            print(f'saved to {out_path}')
            plt.close()

    fig.canvas.mpl_connect('button_press_event', on_press)
    fig.canvas.mpl_connect('key_press_event', on_key)
    redraw()
    plt.show()
