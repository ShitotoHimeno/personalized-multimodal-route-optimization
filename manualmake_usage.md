# manualmake の使い方

## 1. テンプレートを作る（簡単）
```bash
cd /work
python3 -m src.makemap.manualmake template --out data/my_manual.pkl
```

## 2. GUIで描く（マウス操作）
```bash
cd /work
python3 -m src.makemap.manualmake draw --out data/drawn_map.pkl
```

操作方法:
- 左クリック: ノードを追加
- 右クリック: ノードを選択
- 'e'キー: エッジモード（選択した2つのノードを繋げる）
- 'n'キー: ノードモード
- 's'キー: 保存して終了

## 3. 作ったマップでシミュレーションする
手動マップは NetworkX グラフ形式（gpickle）で渡すのが簡単です。

```bash
cd /work
python3 -m src.simulate --manual-graph data/drawn_map.gpickle --scenario SC005 --no-capacity-check
```

gpickle 形式にする場合:
```bash
python3 << 'PY'
import pickle
from src.makemap.manualmake import load_manual_map, build_manual_map
mm = load_manual_map('data/drawn_map.pkl')
G = build_manual_map(mm)
if G.graph.get('map_id') is None: G.graph['map_id']='map_manual'
with open('data/drawn_map.gpickle','wb') as f:
    pickle.dump(G,f)
PY
```

## 4. Pythonで直接作る
```python
from src.makemap.manualmake import ManualMap, ManualNode, ManualEdge, build_manual_map, save_manual_map
mm = ManualMap(config={'map_id':'test','source':'manual'})
mm.nodes.append(ManualNode('walk:0','walk',0,0,role='start'))
mm.nodes.append(ManualNode('facility:hospital','facility',100,50,role='hospital'))
mm.edges.append(ManualEdge('walk:0','facility:hospital',difficulty=0.1))
G = build_manual_map(mm)
save_manual_map(mm,'data/test.pkl')
```
