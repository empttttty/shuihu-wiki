#!/usr/bin/env python3
"""抓取维基文库《水滸傳 (120回本)》序 + 引首 + 第001-120回，输出繁体 Markdown 到 corpus/zh_TW/。

用法: python3 scripts/fetch_corpus.py
- 通过 MediaWiki API (action=parse) 获取解析后的 HTML
- 剥离开头/结尾导航表 (table.ws-header)、编辑按钮等非正文元素
- 正文段落: <p>；韵文: div.poem（<br> 换行拆为独立行）
- 限速 1s/页，失败重试 2 次，缺页记录到 corpus/fetch_report.json
"""
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

API = "https://zh.wikisource.org/w/api.php"
BASE_PAGE = "水滸傳 (120回本)"
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "corpus" / "zh_TW"
REPORT = ROOT / "corpus" / "fetch_report.json"
UA = "shuihu-wiki/0.1 (personal study project; https://github.com/baojie/shiji-kb inspired)"

PAGES = [("序", "序.md"), ("引首", "引首.md")] + [
    (f"第{i:03d}回", f"{i:03d}.md") for i in range(1, 121)
]
TITLE_RE = re.compile(r"(第[一二三四五六七八九十百零〇两]+回)\s*[　 ]*(.+)")


def fetch_page(sub: str) -> dict:
    params = {"action": "parse", "page": f"{BASE_PAGE}/{sub}", "format": "json", "prop": "text"}
    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(API, params=params, timeout=30, headers={"User-Agent": UA})
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"fetch failed after 3 attempts: {sub}: {last_err}")


def extract_ordered(html: str, sub: str) -> tuple[str, list[str]]:
    """按文档顺序提取段落与韵文行。返回 (回目标题, 段落列表)。"""
    soup = BeautifulSoup(html, "html.parser")

    title = sub
    for td in soup.select("table.ws-header td"):
        m = TITLE_RE.match(td.get_text(strip=True))
        if m:
            title = f"{m.group(1)}　{m.group(2).strip()}"
            break

    for sel in ["table.ws-header", "table.ws-footer", "meta", "style", "script",
                "span.mw-editsection", "div.mw-warning", "table.licensebox",
                "div.licensetpl", "div.licenseContainer", "div.licenseBanner"]:
        for tag in soup.select(sel):
            tag.decompose()

    for br in soup.find_all("br"):
        br.replace_with("\n")

    paras: list[str] = []
    for el in soup.select("p, div.poem"):
        if el.name == "p" and el.find_parent("div", class_="poem"):
            continue  # poem 整体处理
        text = el.get_text()
        for line in text.split("\n"):
            line = line.strip(" \t\r\n")
            if line and "Public domain" not in line:
                paras.append(line)
    return title, paras


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {"ok": [], "missing": [], "failed": []}

    for sub, fname in PAGES:
        out_path = OUT_DIR / fname
        if out_path.exists() and out_path.stat().st_size > 200:
            print(f"skip {sub} (exists)")
            report["ok"].append(sub)
            continue
        try:
            data = fetch_page(sub)
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {sub}: {e}")
            report["failed"].append({"page": sub, "error": str(e)})
            continue

        if "error" in data:
            print(f"MISSING {sub}: {data['error'].get('code')}")
            report["missing"].append(sub)
            continue

        html = data["parse"]["text"]["*"]
        title, paras = extract_ordered(html, sub)
        body = "\n\n".join(paras)
        md = f"# {title}\n\n> 底本：维基文库《水滸傳 (120回本)》· {sub}（公有領域）\n\n{body}\n"
        out_path.write_text(md, encoding="utf-8")
        print(f"ok   {sub}: {len(paras)} 段, {len(body)} 字")
        report["ok"].append(sub)
        time.sleep(1.0)

    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成: {len(report['ok'])} 成功, {len(report['missing'])} 缺页, {len(report['failed'])} 失败")


if __name__ == "__main__":
    main()
