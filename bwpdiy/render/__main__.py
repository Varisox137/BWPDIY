"""CLI：渲染单张卡面 PNG。用法：python -m bwpdiy.render card.json [--assets assets] [--out out.png]"""

import argparse
import json
import sys
from pathlib import Path

from bwpdiy.render.pipeline import render_card


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m bwpdiy.render")
    ap.add_argument("card", help="卡牌 dict 的 json 文件")
    ap.add_argument("--assets", default="assets", help="美术资源目录")
    ap.add_argument("--out", default=None, help="输出 png 路径（默认 examples/<name>.png）")
    args = ap.parse_args()

    card_path = Path(args.card)
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card.setdefault("_base_dir", str(card_path.parent))
    base = Path(card["_base_dir"])
    if not base.is_absolute():
        card["_base_dir"] = str(card_path.parent / base)
    out = Path(args.out) if args.out else Path("examples") / f"{card['name']}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = render_card(card, Path(args.assets))
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"渲染失败: {e}", file=sys.stderr)
        return 1
    img.save(out)
    print(f"已输出: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
