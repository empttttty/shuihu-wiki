#!/usr/bin/env python3
"""语料校验 + 生成回目索引 index/回目索引.md。

用法: python3 scripts/validate_corpus.py
检查项:
- 122 个文件齐全（序.md 引首.md 001.md ... 120.md）
- 每回字数在合理区间（异常短 = 抓取可能漏内容）
- 简体/繁体文件数一致、总字数统计
输出: index/回目索引.md（回数 + 对仗回目 + 简体字数）
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CN = ROOT / "corpus" / "zh_CN"
TW = ROOT / "corpus" / "zh_TW"
IDX = ROOT / "index"


def count_chars(text: str) -> int:
    """统计汉字+标点字符数（去掉 markdown 标题行/注记行/空白）。"""
    body = "\n".join(
        ln for ln in text.split("\n")
        if ln.strip() and not ln.startswith("#") and not ln.startswith(">")
    )
    return len(re.sub(r"\s", "", body))


def main() -> None:
    expected = ["序.md", "引首.md"] + [f"{i:03d}.md" for i in range(1, 121)]
    missing = [f for f in expected if not (CN / f).exists()]
    if missing:
        print(f"!! 缺 {len(missing)} 个文件: {missing[:10]}")

    rows, total, short = [], 0, []
    for fname in expected:
        p = CN / fname
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        h1 = next((ln[2:].strip() for ln in text.split("\n") if ln.startswith("# ")), fname)
        n = count_chars(text)
        total += n
        if n < 2000:
            short.append((fname, n))
        rows.append((fname, h1, n))

    print(f"简体文件: {len(list(CN.glob('*.md')))}  繁体文件: {len(list(TW.glob('*.md')))}")
    print(f"总字数(简体): {total:,}")
    if short:
        print("!! 异常短的文件:")
        for f, n in short:
            print(f"   {f}: {n} 字")

    IDX.mkdir(exist_ok=True)
    lines = ["# 《水浒传》120回本 回目索引", "",
             f"> 底本：维基文库《水滸傳 (120回本)》（公有领域）· 简体版总字数 {total:,}", "",
             "| 文件 | 回目 | 字数 |", "|---|---|---|"]
    for fname, h1, n in rows:
        lines.append(f"| {fname} | {h1} | {n:,} |")
    (IDX / "回目索引.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"索引已生成: {IDX / '回目索引.md'}")


if __name__ == "__main__":
    main()
