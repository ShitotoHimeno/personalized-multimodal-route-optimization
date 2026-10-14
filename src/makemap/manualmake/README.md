# manualmake

白紙から手動でノード・エッジを作成するモジュール。

## 概要
- walkノードだけでなく、任意のノード（facility等）を自分で配置できます
- 徒歩エッジを自分で繋げてネットワークを作成します
- 作成したグラフは既存の simulate/visualize と互換です

## Python で作成

```python
from src.makemap.manualmake import ManualMap, ManualNode, ManualEdge, build_manual_map, save_manual_map

mm = ManualMap(
    config={"map_id": "my_map", "source": "manual"},
    nodes=[
        ManualNode("walk:0", "walk", 0, 0, role="start"),
        ManualNode("facility:hospital", "facility", 50, 0, role="hospital"),
        ManualNode("walk:1", "walk", 100, 0, role="goal"),
    ],
    edges=[
        ManualEdge("walk:0", "facility:hospital", difficulty=0.1),
        ManualEdge("facility:hospital", "walk:1", difficulty=0.1),
    ],
)
G = build_manual_map(mm)
save_manual_map(mm, "data/my_manual.pkl")
```

## シミュレーションで使う

```bash
python3 -m src.simulate --manual-graph data/my_manual.pkl --scenario SC005 --no-capacity-check
```

## CLI

```bash
# テンプレート生成
python3 -m src.makemap.manualmake template --out data/manual_template.pkl

# 描画（GUI環境用）
python3 -m src.makemap.manualmake draw --out data/drawn.pkl
```

## 補足
- manual_map.pkl（ManualMapオブジェクト）と gpickle（NetworkXグラフ）どちらも使えます
- simulateの `--manual-graph` はpickle化された NetworkX グラフを想定しています

## 操作方法（draw）
- 左クリック: ノード追加（nodeモード時）
- 右クリック: ノード選択 / エッジ接続（edgeモード時）
- 'n': ノードモード切替
- 'e': エッジモード切替
- 's': 保存して終了
