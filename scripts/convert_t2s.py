"""繁转简：corpus/zh_TW/*.md → corpus/zh_CN/*.md（OpenCC t2s 逐字转换）。

用法: python3 scripts/convert_t2s.py
说明: 简体版同时把底本注记改为简体；繁体原文件保持不动。
     VARIANTS 处理 OpenCC t2s 漏转的异体字（遇到新的随时补充）。
"""
from pathlib import Path

from opencc import OpenCC

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "corpus" / "zh_TW"
DST = ROOT / "corpus" / "zh_CN"

# OpenCC t2s 漏转的异体字映射（例：鴈 是 雁 的异体，第35回「雁行」全靠它定位）
VARIANTS = {"鴈": "雁"}


def convert(cc: OpenCC, text: str) -> str:
    text = cc.convert(text)
    for k, v in VARIANTS.items():
        text = text.replace(k, v)
    return text


def main() -> None:
    cc = OpenCC("t2s")
    DST.mkdir(parents=True, exist_ok=True)
    files = sorted(SRC.glob("*.md"))
    if not files:
        raise SystemExit("corpus/zh_TW/ 为空，先跑 fetch_corpus.py")
    for f in files:
        text = f.read_text(encoding="utf-8")
        (DST / f.name).write_text(convert(cc, text), encoding="utf-8")
    print(f"转换完成: {len(files)} 个文件 → {DST}")


if __name__ == "__main__":
    main()
