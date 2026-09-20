#!/usr/bin/env python3
"""站内链接体检：验证每个 href/src 的目标文件与锚点是否真实存在。

用法：
    $PY scripts/check_links.py

两条经验（HANDOFF §8）：
  #13  必须先剥掉 `?query`——`../search.html?q=名字` 若不剥会被误报成 159 条断链（真实为 0）。
  #8   计数不要用 `grep -c`（按行计数，卡片 join 到一行会被骗），本脚本用 Python 统计。

除文件存在性外，还校验 `#anchor` 是否在目标页有对应 id/name，
因为图鉴锚点（endings.html#catN / places.html#realN）是手工拼接的字符串，
最容易在改名后静默失效。
"""

import pathlib
import re
import sys
from collections import defaultdict

SITE = pathlib.Path(__file__).resolve().parent.parent / "site"
LINK_RE = re.compile(r'(?:href|src)="([^"]+)"')
SKIP_SCHEMES = ("http://", "https://", "//", "mailto:", "data:", "javascript:")

_cache: dict[pathlib.Path, str] = {}


def ids_of(path: pathlib.Path) -> set[str] | None:
    """惰性读取目标页，取出全部 id / name 锚点；非 HTML 返回 None（跳过锚点校验）。"""
    if path.suffix not in (".html", ".htm"):
        return None
    if path not in _cache:
        try:
            _cache[path] = path.read_text(encoding="utf-8")
        except OSError:
            return None
    html = _cache[path]
    return set(re.findall(r'(?:id|name)="([^"]+)"', html))


def main() -> int:
    if not SITE.exists():
        print(f"✗ 找不到 {SITE}，先跑 scripts/render_site.py", file=sys.stderr)
        return 1

    files = sorted(SITE.rglob("*.html"))
    missing_file: dict[str, list[str]] = defaultdict(list)
    missing_anchor: dict[str, list[str]] = defaultdict(list)
    checked = anchors = 0

    for page in files:
        rel = page.relative_to(SITE).as_posix()
        for raw in LINK_RE.findall(page.read_text(encoding="utf-8")):
            if raw.startswith(SKIP_SCHEMES):
                continue
            target, _, frag = raw.partition("#")
            if not target:
                dest = page  # 纯 #anchor，指向本页
            else:
                dest = (page.parent / target.split("?")[0]).resolve()
                if not dest.exists():
                    missing_file[rel].append(raw)
                    continue
            checked += 1
            if frag:
                anchors += 1
                known = ids_of(dest)
                if known is not None and frag not in known:
                    missing_anchor[rel].append(raw)

    bad_pages = len(set(missing_file) | set(missing_anchor))
    print(f"检查 {len(files)} 个页面 · {checked} 条站内链接（其中带锚点 {anchors} 条）")
    print(f"断链 {sum(len(v) for v in missing_file.values())} 条 · 锚点失效 {sum(len(v) for v in missing_anchor.values())} 条"
          f" · 涉及页面 {bad_pages}")

    for label, bucket in (("断链", missing_file), ("锚点失效", missing_anchor)):
        for rel, links in list(bucket.items())[:20]:
            uniq = sorted(set(links))
            print(f"  [{label}] {rel} → {uniq[:6]}{' …' if len(uniq) > 6 else ''}")

    return 1 if bad_pages else 0


if __name__ == "__main__":
    sys.exit(main())
