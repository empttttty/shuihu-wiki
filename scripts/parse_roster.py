#!/usr/bin/env python3
"""从第071回石碣名单解析 108 将 → data/heroes.json。

用法: python3 scripts/parse_roster.py
原文格式（每行两员，全角空格分隔）:
    天魁星「呼保义」　宋江　　　　　天罡星「玉麒麟」　卢俊义
输出字段: rank(座次) / star(星号) / nickname(绰号) / name(姓名) / tier(天罡|地煞)
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "corpus" / "zh_CN" / "071.md"
OUT = ROOT / "data" / "heroes.json"
PAT = re.compile(r"([天地][一-鿿]{1,4}星)「([^」]+)」[　 ]*([一-鿿]{2,4})")


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    heroes: list[dict] = []
    seen: set[str] = set()
    for m in PAT.finditer(text):
        star, nick, name = m.groups()
        if name in seen:  # 章节内名单可能被复述，按姓名去重
            continue
        seen.add(name)
        heroes.append({"star": star, "nickname": nick, "name": name})

    assert len(heroes) == 108, f"解析出 {len(heroes)} 员，应为 108"
    for i, h in enumerate(heroes, 1):
        h["rank"] = i
        h["tier"] = "天罡" if i <= 36 else "地煞"

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(heroes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(heroes)} 将 → {OUT}")
    print("首位:    ", heroes[0])
    print("地煞之首:", heroes[36])
    print("末位:    ", heroes[-1])


if __name__ == "__main__":
    main()
