#!/usr/bin/env python3
"""水浒维基 · 静态站点渲染器（Phase 1 MVP）

用法: python3 scripts/render_site.py
输入:
  corpus/zh_CN/*.md        简体正文（序.md 引首.md 001.md ... 120.md）
  corpus/zh_TW/*.md        繁体正文
  data/heroes.json         108 将（parse_roster.py 生成）
  data/aliases_curated.json 手工别名表
  data/endings.json        108 将结局（手工维护，见文件内 _说明）
  data/places.json         地名（手工维护，实/存疑/虚 三分）
  data/causal.json         事件因果链（手工维护：chains 线索 + links 因果边）
输出 site/:
  index.html               首页（回目列表 + 统计）
  heroes.html              108 将图鉴
  endings.html             108 将结局总览（按结局大类分组）
  places.html              地名图志（按虚实分组）
  causal.html              因果链总览（按线索展开 + 跨线索因果）
  search.html              全文搜索
  chapters/*.html          简体阅读页（高亮 + Purple Numbers + 上下回导航）
  chapters_tw/*.html       繁体阅读页
  wiki/<姓名>.html         人物词条页（信息卡 + 出场回目索引 + 结局）
  wiki/<地名>.html         地名词条页（信息卡 + 虚实判定依据 + 出现回目）
  events/<事件>.html       事件详情页（含「因果」区：前因 / 后果）
  assets/                  style.css / search.js
  data/search-index.json   搜索索引
设计要点:
- 实体高亮单趟正则完成；「大刀/浪子/行者」等通用绰号只在「」引号内匹配，避免误伤正文
- 实体分两级着色：人物=朱砂，地名=黛蓝（design.md §5.5），保证朱砂占比不失控
- 因果链与线索分开：chains 是有序线索，links 才写「因为…所以」；渲染用**线型**区分（实线=因果，虚线=递进），不靠颜色
- 繁体页用 OpenCC(s2t) 把别名表转成繁体再匹配，链接仍指向简体词条页
- 全站除搜索页外零 JS，纯静态可直接部署
"""
import collections
import html
import json
import re
import shutil
from pathlib import Path

from opencc import OpenCC

ROOT = Path(__file__).resolve().parent.parent
CN_DIR = ROOT / "corpus" / "zh_CN"
TW_DIR = ROOT / "corpus" / "zh_TW"
DATA = ROOT / "data"
SITE = ROOT / "site"

CHAIN = ["序", "引首"] + [f"{i:03d}" for i in range(1, 121)]
GENERIC_NICKS = {"大刀", "浪子", "行者"}  # 通用词绰号，仅在「」内匹配

s2t = OpenCC("s2t")

HERO_INFO: dict = {}   # canonical -> {nick, star, rank}，108将悬浮卡用
EXTRA_INFO: dict = {}  # canonical -> {cat, blurb}，非108将人物悬浮卡用
END_CATS: list = []    # 结局大类 [{id, desc}]，顺序即展示顺序
ENDINGS: dict = {}     # canonical -> {cat, ch, place, detail}
PLACE_CATS: list = []  # 地名类别 [{id, desc}]
PLACE_REALS: list = [] # 虚实三档 [{id, desc}]
PLACE_INFO: dict = {}  # 地名 -> {cat, reality, modern, blurb, note, aliases}
CAUSAL_KINDS: list = []   # 因果边类型 [{id, desc}]，顺序即展示顺序
CAUSAL_CHAINS: list = []  # 线索 [{id, name, desc, events:[名]}]
CAUSAL_LINKS: list = []   # 因果边 [{from, to, kind, verb, note?}]
CAUSAL_UP: dict = {}      # 事件 -> [指向它的边]（前因反查）
CAUSAL_DOWN: dict = {}    # 事件 -> [它指向的边]（后果正查）
CHAIN_OF: dict = {}       # 事件 -> [{chain, idx, total}]（可能同属多条线索的交汇点）

# ---------------------------------------------------------------- 数据读取

def load_extra() -> list[dict]:
    d = json.loads((DATA / "people_extra.json").read_text(encoding="utf-8"))
    return [p for p in d["people"] if not p["name"].startswith("_")]


def load_endings() -> tuple[list, dict]:
    """结局表（手工数据）；命中数在 main() 里校验，缺项会告警。"""
    d = json.loads((DATA / "endings.json").read_text(encoding="utf-8"))
    return d["cats"], d["endings"]


def load_places() -> tuple[list, list, list[dict]]:
    """地名表（手工数据）。README 关键差异表：地名虚实混杂，必须标注。"""
    d = json.loads((DATA / "places.json").read_text(encoding="utf-8"))
    places = [p for p in d["places"] if not p["name"].startswith("_")]
    return d["cats"], d["realities"], places


def load_causal() -> dict:
    """因果链表（手工数据），并建好三个反查索引。

    两分法（design.md §5.17）：能说「接着发生了 B」只算线索（chains）；
    能说「因为 A 所以 B」才立因果边（links）。混用会让边界失控——
    时间顺序不等于因果，这是这个数据集唯一的质量红线。
    """
    d = json.loads((DATA / "causal.json").read_text(encoding="utf-8"))
    CAUSAL_KINDS.extend(d["kinds"])
    CAUSAL_CHAINS.extend(d["chains"])
    CAUSAL_LINKS.extend(d["links"])
    for link in d["links"]:
        CAUSAL_UP.setdefault(link["to"], []).append(link)
        CAUSAL_DOWN.setdefault(link["from"], []).append(link)
    for ch in d["chains"]:
        for i, name in enumerate(ch["events"]):
            CHAIN_OF.setdefault(name, []).append(
                {"chain": ch, "idx": i + 1, "total": len(ch["events"])})
    return d


def kind_cls(kind: str) -> str:
    """因果/递进 → CSS 类（用线型区分，不赋色）。"""
    return "k-cause" if kind == "因果" else "k-step"


def chain_anchor(chid: str) -> str:
    return f"chain-{chid}"


def edges_between(a: str, b: str) -> list[dict]:
    """取 a→b 的边（可能不存在 = 链上相邻但无因果）。"""
    return [l for l in CAUSAL_DOWN.get(a, []) if l["to"] == b]


def is_chain_neighbour(a: str, b: str) -> bool:
    """b 是否紧跟在 a 之后出现在同一条线索里（用于筛「跨线索因果」）。"""
    for info in CHAIN_OF.get(a, []):
        seq = info["chain"]["events"]
        i = seq.index(a)
        if i + 1 < len(seq) and seq[i + 1] == b:
            return True
    return False


# ---------------------------------------------------------------- 语料读取

def load_chapters(src: Path) -> list[dict]:
    """返回 [{id, title, paras:[(kind, text)]}]，kind: prose|poem"""
    chapters = []
    for cid in CHAIN:
        p = src / f"{cid}.md"
        lines = p.read_text(encoding="utf-8").split("\n")
        title = next(ln[2:].strip() for ln in lines if ln.startswith("# "))
        paras = []
        for ln in lines:
            if not ln.strip() or ln.startswith(("#", ">")):
                continue
            stripped = ln.lstrip("　")
            indent = len(ln) - len(stripped)
            paras.append(("poem" if indent >= 3 else "prose", stripped.strip()))
        chapters.append({"id": cid, "title": title, "paras": paras})
    return chapters


def chapter_label(cid: str) -> str:
    return cid if cid in ("序", "引首") else f"第{int(cid)}回"


# ---------------------------------------------------------------- 结局视图

def end_badge(name: str) -> str:
    """结局大类标签（design.md §5.15；类型不赋专属色，守朱砂唯一原则）。"""
    e = ENDINGS.get(name)
    if not e:
        return '<span class="end-tag end-none">未录</span>'
    return f'<span class="end-tag">{e["cat"]}</span>'


def end_ch_link(name: str, rel: str = "../") -> str:
    """结局出处回目链接。"""
    e = ENDINGS.get(name)
    if not e:
        return "—"
    return f'<a href="{rel}chapters/{e["ch"]}.html">{chapter_label(e["ch"])}</a>'


def cat_anchor(cat: str) -> str:
    for i, c in enumerate(END_CATS):
        if c["id"] == cat:
            return f"cat{i}"
    return "cat0"


# ---------------------------------------------------------------- 地名视图

def real_anchor(rid: str) -> str:
    for i, r in enumerate(PLACE_REALS):
        if r["id"] == rid:
            return f"real{i}"
    return "real0"


def real_badge(name: str) -> str:
    """虚实标签（design.md §5.16；三档不赋专属色，靠文字区分）。"""
    pl = PLACE_INFO.get(name)
    if not pl:
        return '<span class="real-tag">未录</span>'
    return f'<span class="real-tag">{pl["reality"]}</span>'


def match_place(text: str, exclude: str = "") -> str | None:
    """在自由文本（如事件地点「孟州十字坡」）中认领地名：命中别名最长者胜出。

    必须走 aliases——事件 loc 字段用的是简称（「郓城」「大名府」），
    只比对规范名（「郓城县」「北京大名府」）会漏掉 7 条事件地点链接。
    """
    best, best_len = None, 0
    for name, pl in PLACE_INFO.items():
        if name == exclude:
            continue
        for a in (name, *pl["aliases"]):
            if a and a in text and len(a) > best_len:
                best, best_len = name, len(a)
    return best

# ---------------------------------------------------------------- 别名体系

def build_entries() -> list[dict]:
    """[{alias, canonical, generic, kind}] —— 简体形式；kind: hero|person|place"""
    heroes = json.loads((DATA / "heroes.json").read_text(encoding="utf-8"))
    curated = json.loads((DATA / "aliases_curated.json").read_text(encoding="utf-8"))
    entries = []
    for h in heroes:
        entries.append({"alias": h["name"], "canonical": h["name"],
                        "generic": False, "kind": "hero"})
        entries.append({"alias": h["nickname"], "canonical": h["name"],
                        "generic": h["nickname"] in GENERIC_NICKS, "kind": "hero"})
    for name, aliases in curated.items():
        if name.startswith("_") or not isinstance(aliases, list):
            continue  # 跳过 _说明 等注释键
        for a in aliases:
            entries.append({"alias": a, "canonical": name,
                            "generic": False, "kind": "hero"})
    for p in load_extra():
        entries.append({"alias": p["name"], "canonical": p["name"],
                        "generic": False, "kind": "person"})
        for a in p.get("aliases", []):
            entries.append({"alias": a, "canonical": p["name"],
                            "generic": False, "kind": "person"})
    for pl in load_places()[2]:
        if pl["name"].startswith("_"):
            continue
        for a in pl["aliases"]:
            entries.append({"alias": a, "canonical": pl["name"],
                            "generic": False, "kind": "place"})
    return entries


def build_matcher(entries: list[dict], lang: str, rel: str, counts: dict | None):
    """编译单趟正则；返回 (highlight_func)。lang: cn|tw"""
    if lang == "tw":
        pairs = [(s2t.convert(e["alias"]), e["canonical"], e["generic"]) for e in entries]
    else:
        pairs = [(e["alias"], e["canonical"], e["generic"]) for e in entries]

    canon_of = {a: c for a, c, _ in pairs}
    generic = sorted((a for a, _, g in pairs if g), key=len, reverse=True)
    normal = sorted((a for a, _, g in pairs if not g), key=len, reverse=True)

    parts = []
    if generic:
        parts.append("「(" + "|".join(map(re.escape, generic)) + ")」")
    parts.append("(" + "|".join(map(re.escape, normal)) + ")")
    pat = re.compile("|".join(parts))

    def link(alias: str, canonical: str) -> str:
        info = HERO_INFO.get(canonical)
        cls = "ent"
        if info:
            nick = s2t.convert(info["nick"]) if lang == "tw" else info["nick"]
            star = s2t.convert(info["star"]) if lang == "tw" else info["star"]
            tip = f'<span class="ent-tip">「{nick}」 · {star} · 座次 {info["rank"]}</span>'
        elif canonical in EXTRA_INFO:
            ex = EXTRA_INFO[canonical]
            blurb = s2t.convert(ex["blurb"]) if lang == "tw" else ex["blurb"]
            cat = s2t.convert(ex["cat"]) if lang == "tw" else ex["cat"]
            tip = f'<span class="ent-tip">{cat} · {blurb}</span>'
        elif canonical in PLACE_INFO:
            pl = PLACE_INFO[canonical]
            cls = "ent ent-place"  # 地名走黛蓝，人物走朱砂（design.md §5.5）
            cat = s2t.convert(pl["cat"]) if lang == "tw" else pl["cat"]
            real = s2t.convert(pl["reality"]) if lang == "tw" else pl["reality"]
            modern = (s2t.convert(pl["modern"]) if lang == "tw" else pl["modern"]) or "无现实对应"
            tip = f'<span class="ent-tip">地名 · {cat} · {real} · 今 {modern}</span>'
        else:
            tip = ""
        return f'<a class="{cls}" href="{rel}wiki/{canonical}.html">{alias}{tip}</a>'

    def repl(m: re.Match) -> str:
        g1, g2 = m.group(1), m.group(2)
        if g1 is not None:
            canon = canon_of[g1]
            out = f"「{link(g1, canon)}」"
        else:
            canon = canon_of[g2]
            out = link(g2, canon)
        if counts is not None:
            counts[canon] = counts.get(canon, 0) + 1
        return out

    def highlight(text: str) -> str:
        return pat.sub(repl, html.escape(text))

    return highlight

# ---------------------------------------------------------------- 页面骨架

def page_shell(title: str, rel: str, body: str, wide: bool = False) -> str:
    main_cls = "wide" if wide else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · 水浒维基</title>
<link rel="stylesheet" href="{rel}assets/style.css">
</head>
<body>
<header class="topbar">
  <a class="brand" href="{rel}index.html"><span class="seal seal-sm">水<br>浒</span>水浒维基</a>
  <nav>
    <a href="{rel}index.html#toc">回目</a>
    <a href="{rel}heroes.html">108将图鉴</a>
    <a href="{rel}endings.html">结局</a>
    <a href="{rel}places.html">地名</a>
    <a href="{rel}events.html">名场面</a>
    <a href="{rel}causal.html">因果链</a>
    <a href="{rel}search.html">搜索</a>
  </nav>
</header>
<main class="{main_cls}">
{body}
</main>
<footer>
  底本：维基文库《水滸傳 (120回本)》（公有领域）<br>
  本站由 AI 辅助构建 · 标注数据 <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh">CC BY-NC-SA 4.0</a> · 方法论致敬 <a href="https://github.com/baojie/shiji-kb">shiji-kb</a>
</footer>
</body>
</html>
"""

def crumbs(rel: str, prev_c: dict | None, next_c: dict | None, twin: str, twin_label: str) -> str:
    prev_html = f'<a href="{rel}chapters/{prev_c["id"]}.html">← {prev_c["title"]}</a>' if prev_c else "<span></span>"
    next_html = f'<a href="{rel}chapters/{next_c["id"]}.html">{next_c["title"]} →</a>' if next_c else "<span></span>"
    return (f'<div class="crumbs">{prev_html}'
            f'<span class="crumbs-mid"><a href="{rel}index.html#toc">目录</a> · '
            f'<a href="{twin}">{twin_label}版</a></span>{next_html}</div>')

# ---------------------------------------------------------------- 渲染：章节

def chapter_head(title: str) -> str:
    """题区：回数小字 + 对仗双行 + 朱砂菱形（design.md §5.4）。"""
    parts = title.split("　")
    if len(parts) >= 3:  # 第X回 上句 下句
        cnum, lines = parts[0], parts[1:]
        h1 = "<br>".join(html.escape(x) for x in lines)
    else:  # 序 / 引首
        cnum, h1 = "　", html.escape(title)
    return (f'<header class="chead"><div class="cnum">{html.escape(cnum)}</div>'
            f'<h1>{h1}</h1><div class="cmark">◆</div></header>')


def render_chapters(chapters: list[dict], lang: str, outdir: Path, rel: str,
                    appearances: dict | None) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    twin_dir = "chapters_tw" if lang == "cn" else "chapters"
    twin_label = "繁体" if lang == "cn" else "简体"
    counts: dict = {}  # 简体渲染时按回统计别名命中，供词条页"出场索引"使用
    hl = build_matcher(ENTRIES, lang, rel, counts if appearances is not None else None)

    for idx, ch in enumerate(chapters):
        counts.clear()
        body_paras = []
        for n, (kind, text) in enumerate(ch["paras"], 1):
            cls = ' class="poem"' if kind == "poem" else ""
            body_paras.append(
                f'<p{cls} id="p{n}">{hl(text)}'
                f'<a class="pn" href="#p{n}" title="段落编号">[{n}]</a></p>')
        prev_c = chapters[idx - 1] if idx > 0 else None
        next_c = chapters[idx + 1] if idx < len(chapters) - 1 else None
        twin = f"{rel}{twin_dir}/{ch['id']}.html"
        crumbs_html = crumbs(rel, prev_c, next_c, twin, twin_label)
        # 上一页/下一页链接在繁体页应指向繁体
        if lang == "tw":
            crumbs_html = crumbs_html.replace(f'{rel}chapters/', f'{rel}chapters_tw/')
        body = (crumbs_html + chapter_head(ch["title"]) + "\n"
                + "<article>\n" + "\n".join(body_paras) + "\n</article>\n" + crumbs_html)
        (outdir / f"{ch['id']}.html").write_text(
            page_shell(ch["title"], rel, body), encoding="utf-8")

        if appearances is not None and counts:
            for canon, c in counts.items():
                ap = appearances.setdefault(canon, {"chapters": [], "mentions": 0})
                ap["chapters"].append(ch["id"])
                ap["mentions"] += c

# ---------------------------------------------------------------- 渲染：首页/图鉴/词条/搜索

def render_home(chapters: list[dict], stats: dict) -> None:
    items = "\n".join(
        f'<li{" class=no-num" if ch["id"] in ("序", "引首") else ""}>'
        f'<a href="chapters/{ch["id"]}.html">{html.escape(ch["title"])}</a></li>'
        for ch in chapters)
    body = f"""
<section class="hero">
  <span class="seal seal-lg">水<br>浒</span>
  <h1>水浒维基</h1>
  <p class="tagline">让《水浒传》像代码一样：语法高亮、跳转、搜索、推理</p>
  <p class="stats">120 回 · {stats['chars']:,} 字 · 108 将 · 结局 8 类 · {stats['places']} 处地名（实/存疑/虚）· {stats['events']} 幕名场面 · {stats['causal']} 条因果边</p>
  <p class="hero-links"><a class="btn btn-ink" href="chapters/001.html">开始阅读</a>
  <a class="btn" href="heroes.html">108将图鉴</a>
  <a class="btn" href="endings.html">108将结局</a>
  <a class="btn" href="places.html">地名图志</a>
  <a class="btn" href="events.html">名场面</a>
  <a class="btn" href="search.html">全文搜索</a></p>
</section>
<h2 id="toc">回目</h2>
<ol class="toc">
{items}
</ol>
"""
    (SITE / "index.html").write_text(page_shell("首页", "", body, wide=True), encoding="utf-8")


def render_heroes(heroes: list[dict], appearances: dict, extras: list[dict]) -> None:
    def card(h: dict) -> str:
        ap = appearances.get(h["name"], {})
        n_ch = len(ap.get("chapters", []))
        e = ENDINGS.get(h["name"])
        end_html = (f'<span class="end-tag" title="{e["detail"]}">{e["cat"]}</span>'
                    if e else '<span class="end-tag end-none">未录</span>')
        return (f'<a class="card" href="wiki/{h["name"]}.html">'
                f'<span class="rank">{h["rank"]}</span>'
                f'<span class="star">{h["star"]}</span>'
                f'<b>{h["name"]}</b>'
                f'<span class="nick">「{h["nickname"]}」</span>'
                f'{end_html}'
                f'<span class="app">出场 {n_ch} 回</span></a>')

    def xcard(p: dict) -> str:
        ap = appearances.get(p["name"], {})
        n_ch = len(ap.get("chapters", []))
        return (f'<a class="card" href="wiki/{p["name"]}.html">'
                f'<span class="rank">{p["cat"]}</span>'
                f'<b>{p["name"]}</b>'
                f'<span class="app">出场 {n_ch} 回</span></a>')

    tg = "\n".join(card(h) for h in heroes if h["tier"] == "天罡")
    ds = "\n".join(card(h) for h in heroes if h["tier"] == "地煞")
    stat_chips = " ".join(
        f'<a class="chip" href="endings.html#{cat_anchor(c["id"])}">{c["id"]} {END_COUNTS.get(c["id"], 0)}</a>'
        for c in END_CATS)
    CAT_ORDER = ["梁山前史", "朝廷官府", "市井江湖", "庄堡豪强",
                 "田虎·王庆", "方腊", "辽国", "神异"]
    extra_sections = []
    for cat in CAT_ORDER:
        group = [p for p in extras if p["cat"] == cat]
        if not group:
            continue
        cards = "\n".join(xcard(p) for p in group)
        extra_sections.append(
            f'<h2 class="tier-head">{cat} <small>{len(group)} 人</small></h2>\n'
            f'<div class="cards">{cards}</div>')
    body = f"""
<header class="chead"><div class="cnum">忠义堂石碣受天文 · 梁山泊英雄排座次</div>
<h1>108将图鉴</h1><div class="cmark">◆</div></header>
<p class="note">据第71回石碣名单 · 天罡星 36 员 · 地煞星 72 员 · 点击卡片进入词条</p>
<p class="note end-stats">结局分布：{stat_chips} · <a href="endings.html">查看全部 108 条结局 →</a></p>
<h2 class="tier-head">天罡星 <small>36 员</small></h2>
<div class="cards">{tg}</div>
<h2 class="tier-head">地煞星 <small>72 员</small></h2>
<div class="cards">{ds}</div>
<h2 class="tier-head">其他人物 <small>一百单八将之外的关键角色 · {len(extras)} 人</small></h2>
{"".join(extra_sections)}
"""
    (SITE / "heroes.html").write_text(page_shell("108将图鉴", "", body, wide=True), encoding="utf-8")


def render_people_extra(extras: list[dict], appearances: dict,
                        events: list[dict] | None) -> None:
    """非108将人物词条页（与108将同目录 wiki/）。"""
    wiki_dir = SITE / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    for p in extras:
        name = p["name"]
        ap = appearances.get(name, {"chapters": [], "mentions": 0})
        ch_ids = [c for c in CHAIN if c in set(ap["chapters"])]
        first = ch_ids[0] if ch_ids else None
        first_link = (f'<a href="../chapters/{first}.html">{chapter_label(first)}</a>'
                      if first else "—")
        chips = " ".join(
            f'<a class="chip" href="../chapters/{c}.html">{chapter_label(c)}</a>'
            for c in ch_ids)
        alias_row = (f'<tr><th>别名</th><td>{"、".join(p["aliases"])}</td></tr>'
                     if p.get("aliases") else "")
        ev_section = ""
        if events:
            related = hero_events(name, events)
            if related:
                ev_section = ('<h2>相关名场面</h2><p class="chips">' + "".join(
                    f'<a class="chip" href="../events/{ev["name"]}.html">{ev["name"]}</a>'
                    for ev in related) + "</p>")
        body = f"""
<header class="chead"><div class="cnum">{p["cat"]}</div>
<h1>{name}</h1><div class="cmark">◆</div></header>
<p class="note"><a href="../heroes.html">返回人物图鉴</a> · <a href="../search.html?q={name}">全文搜索</a></p>
<table class="infobox">
  <tr><th>类别</th><td>{p["cat"]}</td></tr>
  <tr><th>简介</th><td>{p["blurb"]}</td></tr>
  {alias_row}
  <tr><th>首登场</th><td>{first_link}</td></tr>
  <tr><th>出场</th><td>{len(ch_ids)} 回 · 正文提及 {ap["mentions"]} 次（按别名自动统计，含误差）</td></tr>
</table>
{ev_section}
<h2>出场回目</h2>
<p class="chips">{chips}</p>
"""
        (wiki_dir / f"{name}.html").write_text(
            page_shell(name, "../", body), encoding="utf-8")


def render_wiki(heroes: list[dict], appearances: dict, curated: dict,
                events: list[dict] | None = None) -> None:
    wiki_dir = SITE / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    for h in heroes:
        ap = appearances.get(h["name"], {"chapters": [], "mentions": 0})
        ch_ids = [c for c in CHAIN if c in set(ap["chapters"])]
        first = ch_ids[0] if ch_ids else None
        aliases = [h["nickname"]] + curated.get(h["name"], [])
        chips = " ".join(
            f'<a class="chip" href="../chapters/{c}.html">{chapter_label(c)}</a>'
            for c in ch_ids)
        first_link = (f'<a href="../chapters/{first}.html">{chapter_label(first)}</a>'
                      if first else "—")
        ev_chips = ""
        if events:
            related = hero_events(h["name"], events)
            if related:
                ev_chips = ('<h2>相关名场面</h2><p class="chips">' + "".join(
                    f'<a class="chip" href="../events/{ev["name"]}.html">{ev["name"]}</a>'
                    for ev in related) + "</p>")
        event_section = ev_chips
        e = ENDINGS.get(h["name"])
        if e:
            end_section = (
                f'<h2>结局 · {end_badge(h["name"])}</h2>\n'
                f'<div class="end-box"><p class="end-line">{e["detail"]}</p>'
                f'<p class="end-meta">{e["place"]} · 出处 {end_ch_link(h["name"])} · '
                f'<a href="../endings.html#{cat_anchor(e["cat"])}">同结局人物</a></p></div>')
            end_row = (f'<tr><th>结局</th><td>{end_badge(h["name"])}　{e["place"]}'
                       f'（{end_ch_link(h["name"])}）</td></tr>')
        else:
            end_section = ""
            end_row = '<tr><th>结局</th><td><span class="end-tag end-none">待补</span></td></tr>'
        body = f"""
<header class="chead"><div class="cnum">{h["star"]} · 座次第 {h["rank"]} 位</div>
<h1>{h["name"]}</h1><div class="cmark">◆</div></header>
<p class="note">「{h["nickname"]}」 · {h["tier"]} · <a href="../heroes.html">返回 108将图鉴</a> · <a href="../search.html?q={h["name"]}">全文搜索</a></p>
<table class="infobox">
  <tr><th>星号</th><td>{h["star"]}</td></tr>
  <tr><th>绰号</th><td>{h["nickname"]}</td></tr>
  <tr><th>座次</th><td>第 {h["rank"]} 位（{h["tier"]}）</td></tr>
  <tr><th>别名</th><td>{"、".join(aliases)}</td></tr>
  <tr><th>首登场</th><td>{first_link}</td></tr>
  <tr><th>出场</th><td>{len(ch_ids)} 回 · 正文提及 {ap["mentions"]} 次（按别名自动统计，含误差）</td></tr>
  {end_row}
</table>
{end_section}
<h2>出场回目</h2>
<p class="chips">{chips}</p>
{event_section}
"""
        (wiki_dir / f"{h['name']}.html").write_text(
            page_shell(h["name"], "../", body), encoding="utf-8")


def render_endings(heroes: list[dict]) -> None:
    """108将结局总览（design.md §5.15）：按结局大类分组，组内保持座次序。"""
    stat_chips = " ".join(
        f'<a class="chip" href="#{cat_anchor(c["id"])}">{c["id"]} {END_COUNTS.get(c["id"], 0)}</a>'
        for c in END_CATS)
    groups = []
    for i, c in enumerate(END_CATS):
        members = [h for h in heroes
                   if ENDINGS.get(h["name"], {}).get("cat") == c["id"]]
        items = "\n".join(
            f'<a class="end-item" href="wiki/{h["name"]}.html">'
            f'<span class="end-head"><span class="rank">{h["rank"]}</span>'
            f'<b>{h["name"]}</b><span class="nick">「{h["nickname"]}」</span></span>'
            f'<span class="end-d">{ENDINGS[h["name"]]["detail"]}</span>'
            f'<span class="end-m">{ENDINGS[h["name"]]["place"]} · '
            f'{chapter_label(ENDINGS[h["name"]]["ch"])}</span></a>'
            for h in members)
        groups.append(
            f'<div class="act-head" id="{cat_anchor(c["id"])}">'
            f'<small>{c["desc"]}</small><h2>{c["id"]} <span class="cnt">{len(members)} 员</span></h2></div>\n'
            f'<div class="end-list">{items}</div>')
    body = f"""
<header class="chead"><div class="cnum">自石碣受天文 · 至蓼儿洼神聚</div>
<h1>108将结局</h1><div class="cmark">◆</div></header>
<p class="note">据第110–120回正文逐人核对 · 与第119回宋江谢恩表所载存殁名册完全吻合 · 点击条目进入词条</p>
<p class="note end-stats">{stat_chips}</p>
<div class="end-quote"><p>昔日念臣共聚义兵一百八人，登五台发愿，谁想今日十损其八。</p>
<span class="end-m">—— 宋江谢恩表（第119回）</span></div>
{"".join(groups)}
"""
    (SITE / "endings.html").write_text(
        page_shell("108将结局", "", body, wide=True), encoding="utf-8")


def place_card(p: dict, place_ap: dict) -> str:
    ap = place_ap.get(p["name"], {})
    n_ch = len(ap.get("chapters", []))
    modern = p["modern"] or "无现实对应"
    return (f'<a class="place-item" href="wiki/{p["name"]}.html">'
            f'<span class="place-head"><b>{p["name"]}</b>'
            f'<span class="cat">{p["cat"]}</span></span>'
            f'<span class="place-modern">今地 · {modern}</span>'
            f'<span class="place-d">{p["blurb"]}</span>'
            f'<span class="place-m">出现 {n_ch} 回</span></a>')


def render_places(places: list[dict], place_ap: dict) -> None:
    """地名图志（design.md §5.16）：按虚实分组，组内按类别聚拢、类内按出现频次降序。"""
    counts = {r["id"]: sum(1 for p in places if p["reality"] == r["id"])
              for r in PLACE_REALS}
    cat_order = [c["id"] for c in PLACE_CATS]
    stat_chips = " ".join(
        f'<a class="chip" href="#{real_anchor(r["id"])}">{r["id"]} {counts[r["id"]]}</a>'
        for r in PLACE_REALS)
    cat_line = " · ".join(
        f'{c["id"]} {sum(1 for p in places if p["cat"] == c["id"])}' for c in PLACE_CATS)
    sections = []
    for r in PLACE_REALS:
        group = [p for p in places if p["reality"] == r["id"]]
        group.sort(key=lambda p: (cat_order.index(p["cat"]),
                                  -len(place_ap.get(p["name"], {}).get("chapters", []))))
        cards = "\n".join(place_card(p, place_ap) for p in group)
        sections.append(
            f'<div class="act-head" id="{real_anchor(r["id"])}">'
            f'<small>{r["desc"]}</small>'
            f'<h2>{r["id"]} <span class="cnt">{len(group)} 处</span></h2></div>\n'
            f'<div class="place-list">{cards}</div>')
    body = f"""
<header class="chead"><div class="cnum">九州四至 · 山川八方</div>
<h1>地名图志</h1><div class="cmark">◆</div></header>
<p class="note">{len(places)} 处地名 · 逐个核验正文用词后立目 · 虚实判定依据见各条目词条页</p>
<p class="note end-stats">虚实分布：{stat_chips}　·　类别：{cat_line}</p>
<div class="end-quote"><p>水浒地名虚实混杂：东京是真的，梁山泊的地形是文学化的。</p>
<span class="end-m">—— 本站设计前提（README · 史书与小说之别）</span></div>
{"".join(sections)}
"""
    (SITE / "places.html").write_text(
        page_shell("地名图志", "", body, wide=True), encoding="utf-8")


def render_place_wiki(places: list[dict], place_ap: dict,
                      events: list[dict] | None = None) -> None:
    """地名词条页（与人物词条页同目录 wiki/）。"""
    wiki_dir = SITE / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    for p in places:
        name = p["name"]
        ap = place_ap.get(name, {"chapters": [], "mentions": 0})
        ch_ids = [c for c in CHAIN if c in set(ap["chapters"])]
        first = ch_ids[0] if ch_ids else None
        first_link = (f'<a href="../chapters/{first}.html">{chapter_label(first)}</a>'
                      if first else "—")
        chips = " ".join(
            f'<a class="chip" href="../chapters/{c}.html">{chapter_label(c)}</a>'
            for c in ch_ids)
        alias_row = (f'<tr><th>别名</th><td>{"、".join(p["aliases"])}</td></tr>'
                     if p["aliases"] else "")
        note_block = ""
        if p.get("note"):
            note_block = ('<h2>虚实判定依据</h2>\n'
                          f'<div class="end-box"><p class="end-line">{p["note"]}</p></div>')
        ev_chips = ""
        if events:
            related = [ev for ev in events
                       if ev.get("loc") and match_place(ev["loc"]) == name]
            if related:
                ev_chips = ('<h2>相关名场面</h2><p class="chips">' + "".join(
                    f'<a class="chip" href="../events/{ev["name"]}.html">{ev["name"]}</a>'
                    for ev in related) + "</p>")
        body = f"""
<header class="chead"><div class="cnum">{p["cat"]} · {p["reality"]}</div>
<h1>{name}</h1><div class="cmark">◆</div></header>
<p class="note">{real_badge(name)} · {p["cat"]} · <a href="../places.html">返回地名图志</a> · <a href="../search.html?q={name}">全文搜索</a></p>
<table class="infobox">
  <tr><th>类别</th><td>{p["cat"]}</td></tr>
  <tr><th>虚实</th><td>{real_badge(name)}　<a href="../places.html#{real_anchor(p["reality"])}">同判定的地名</a></td></tr>
  <tr><th>今地</th><td>{p["modern"] or "无现实对应（小说创设）"}</td></tr>
  {alias_row}
  <tr><th>首见</th><td>{first_link}</td></tr>
  <tr><th>出现</th><td>{len(ch_ids)} 回 · 正文提及 {ap["mentions"]} 次（按别名自动统计，含误差）</td></tr>
</table>
<h2>简介</h2>
<p class="event-sum">{p["blurb"]}</p>
{note_block}
{ev_chips}
<h2>出现回目</h2>
<p class="chips">{chips}</p>
"""
        (wiki_dir / f"{name}.html").write_text(
            page_shell(name, "../", body), encoding="utf-8")


def render_search(chapters: list[dict]) -> None:
    idx = {"chapters": [
        {"i": ch["id"], "t": ch["title"],
         "p": [[n, text] for n, (_, text) in enumerate(ch["paras"], 1)]}
        for ch in chapters]}
    (SITE / "data").mkdir(exist_ok=True)
    (SITE / "data" / "search-index.json").write_text(
        json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    body = """
<header class="chead"><div class="cnum">89 万字全文检索</div>
<h1>全文搜索</h1><div class="cmark">◆</div></header>
<p class="note">覆盖 120 回 + 序 + 引首全部正文（简体）· 输入关键词即时检索</p>
<input id="q" type="search" placeholder="输入关键词，如：倒拔垂杨柳 / 蒙汗药 / 沧州" autofocus>
<div id="meta"></div>
<div id="results"></div>
<script src="assets/search.js"></script>
"""
    (SITE / "search.html").write_text(page_shell("全文搜索", "", body, wide=True), encoding="utf-8")

# ---------------------------------------------------------------- 静态资源




# ---------------------------------------------------------------- 渲染：名场面事件库

def render_notfound() -> None:
    """404 页（design.md §5.18）。

    Cloudflare Pages 在输出目录根发现 404.html 后，会用它响应未匹配的路径
    并返回真正的 404 状态码——此前是「200 + 首页内容」的软 404。

    页内链接一律写站点根绝对路径（rel="/"）：CF 返回本页时浏览器地址栏仍是
    原 URL（如 /wiki/nonexistent），相对路径会相对原路径解析而再次 404。
    """
    body = """<section class="hero">
  <span class="seal seal-lg">查<br>无</span>
  <h1>此路不通</h1>
  <p class="tagline">你要找的这一号，石碣上没有，聚义厅里也点不着名。</p>
  <p class="stats">404 · 许是路径写错了，许是撞见了李鬼——冒名顶替是他的拿手戏，真身却查不着</p>
  <p class="hero-links">
    <a class="btn btn-ink" href="/index.html">回聚义厅</a>
    <a class="btn" href="/heroes.html">一百单八将</a>
    <a class="btn" href="/events.html">名场面</a>
    <a class="btn" href="/search.html">全文搜索</a>
  </p>
</section>
<p class="note">若你是顺着本站某条链接来的，那是条断线，烦请把它的来处记下。</p>
"""
    (SITE / "404.html").write_text(page_shell("此路不通", "/", body, wide=True),
                                   encoding="utf-8")


def parse_ch_range(ch: str) -> list[str]:
    """'003' → ['003']；'047-050' → ['047','048','049','050']"""
    if "-" in ch:
        a, b = ch.split("-")
        return [f"{i:03d}" for i in range(int(a), int(b) + 1)]
    return [ch]


def ch_display(ch: str) -> str:
    if "-" in ch:
        a, b = ch.split("-")
        return f"第{int(a)}–{int(b)}回"
    return f"第{int(ch)}回"


def find_excerpt(chapters_by_id: dict, ch: str, kw: str) -> dict | None:
    """在回目范围内按关键词定位原文段落，返回摘录+锚点。"""
    for cid in parse_ch_range(ch):
        chapter = chapters_by_id.get(cid)
        if not chapter:
            continue
        for n, (_, text) in enumerate(chapter["paras"], 1):
            pos = text.find(kw)
            if pos >= 0:
                start = max(0, pos - 45)
                snip = text[start:pos + len(kw) + 75]
                return {"cid": cid, "n": n, "snip": snip.strip()}
    return None


def event_url(name: str, rel: str) -> str:
    return f"{rel}events/{name}.html"


def chain_row(name: str) -> str:
    """事件页信息表的「线索」行；事件跨线索（交汇点）时全部列出。"""
    infos = CHAIN_OF.get(name, [])
    if not infos:
        return ""
    parts = "".join(
        f'<a href="../causal.html#{chain_anchor(i["chain"]["id"])}">{i["chain"]["name"]}</a>'
        f'<span class="chain-pos">第 {i["idx"]}/{i["total"]} 环</span>'
        for i in infos)
    return f'  <tr><th>线索</th><td class="chain-cell">{parts}</td></tr>\n'


def causal_block(name: str) -> str:
    """事件页「因果」区：左列前因、右列后果（design.md §5.17）。无边则整块不出现。"""
    ups, downs = CAUSAL_UP.get(name, []), CAUSAL_DOWN.get(name, [])

    def col(title: str, links: list, key: str) -> str:
        if not links:
            return ""
        items = []
        for l in links:
            note = (f'<span class="causal-note">{l["note"]}</span>'
                    if l.get("note") else "")
            items.append(
                f'<a class="causal-item" href="{l[key]}.html">'
                f'<span class="causal-head"><span class="kind {kind_cls(l["kind"])}">'
                f'{l["kind"]}</span><b>{l[key]}</b></span>'
                f'<span class="causal-verb">{l["verb"]}</span>{note}</a>')
        return (f'<div class="causal-col"><div class="causal-h">{title}'
                f'<span class="cnt">{len(links)}</span></div>{"".join(items)}</div>')

    cols = col("前因", ups, "from") + col("后果", downs, "to")
    if not cols:
        return ""
    return f'<h2>因果</h2>\n<div class="causal">{cols}</div>'


def render_causal(events_data: dict) -> None:
    """因果链总览（design.md §5.17）。

    三段结构：判断标准 → 逐条线索的纵向链条 → 跨线索因果。
    第三段是重点：单个线索视角看不到的连接（如一套生辰纲如何把宋江牵进来）。
    链上相邻两事件若无因果边，渲染成虚线"无直接因果"，让时序与因果的差别肉眼可辨。
    """
    events = {e["name"]: e for e in events_data["events"]}
    n_cause = sum(1 for l in CAUSAL_LINKS if l["kind"] == "因果")
    n_step = len(CAUSAL_LINKS) - n_cause

    legend = "".join(
        f'<div class="kind-item"><span class="kind-line {kind_cls(k["id"])}"></span>'
        f'<b>{k["id"]}</b><span>{k["desc"]}</span></div>'
        for k in CAUSAL_KINDS)

    sections = []
    for ch in CAUSAL_CHAINS:
        seq = ch["events"]
        rows = []
        for i, name in enumerate(seq):
            ev = events[name]
            rows.append(
                f'<li class="chain-node"><a href="events/{name}.html">'
                f'<span class="ch">{ch_display(ev["ch"])}</span>'
                f'<b>{name}</b><span class="sum">{ev["sum"]}</span></a></li>')
            if i + 1 < len(seq):
                nxt = seq[i + 1]
                es = edges_between(name, nxt)
                if es:
                    e = es[0]
                    rows.append(
                        f'<li class="chain-edge {kind_cls(e["kind"])}">'
                        f'<span class="kind">{e["kind"]}</span>'
                        f'<span class="verb">{e["verb"]}</span></li>')
                else:
                    rows.append('<li class="chain-edge k-none">'
                                '<span class="verb">（同一线索的下一步，无直接因果）</span></li>')
        sections.append(
            f'<div class="act-head" id="{chain_anchor(ch["id"])}">'
            f'<small>{len(seq)} 环 · {ch_display(events[seq[0]]["ch"])}–'
            f'{ch_display(events[seq[-1]]["ch"])}</small>'
            f'<h2>{ch["name"]}</h2></div>\n'
            f'<p class="chain-desc">{ch["desc"]}</p>\n'
            f'<ol class="chain">{"".join(rows)}</ol>')

    cross = [l for l in CAUSAL_LINKS if not is_chain_neighbour(l["from"], l["to"])]
    cross_items = "".join(
        f'<div class="cross-item">'
        f'<a class="cross-node" href="events/{l["from"]}.html">{l["from"]}</a>'
        f'<span class="cross-arrow {kind_cls(l["kind"])}">'
        f'<span class="kind">{l["kind"]}</span>{l["verb"]}<i>▶</i></span>'
        f'<a class="cross-node" href="events/{l["to"]}.html">{l["to"]}</a></div>'
        for l in cross)

    body = f"""
<header class="chead"><div class="cnum">因为所以 · 一百单八人的连锁</div>
<h1>事件因果链</h1><div class="cmark">◆</div></header>
<p class="note">{len(CAUSAL_CHAINS)} 条线索 · {len(events)} 幕事件 · {len(CAUSAL_LINKS)} 条因果边（因果 {n_cause} · 递进 {n_step}）· 点任意一环进入事件页</p>
<div class="end-quote"><p>只写「接着发生了 B」是时序；能写「因为 A 所以 B」才是因果——本站只把后者叫作因果边。</p>
<span class="end-m">—— 数据编纂原则（data/causal.json）</span></div>
<h2>判断标准</h2>
<div class="kind-legend">{legend}</div>
<h2>线索</h2>
<p class="note">每条线索按叙事顺序纵向展开；环节之间的连线标注关系动词</p>
{"".join(sections)}
<h2>跨线索因果</h2>
<p class="note">两端不在同一条线索上——单个线索视角看不到的连接，共 {len(cross)} 条</p>
{"".join(cross_items)}
"""
    (SITE / "causal.html").write_text(
        page_shell("事件因果链", "", body, wide=True), encoding="utf-8")


def render_events(events_data: dict, chapters_by_id: dict) -> dict:
    """渲染 events.html 长廊 + events/<名>.html 详情页；返回含摘录信息的事件列表。"""
    events = events_data["events"]
    acts = events_data["acts"]

    def act_of(ev: dict) -> dict:
        first = parse_ch_range(ev["ch"])[0]
        for a in acts:
            if a["from"] <= first <= a["to"]:
                return a
        return acts[-1]

    # 摘录定位（构建期一次性完成，未命中打印警告）
    missing = []
    for ev in events:
        ev["_act"] = act_of(ev)
        ev["_ex"] = find_excerpt(chapters_by_id, ev["ch"], ev["kw"])
        if not ev["_ex"]:
            missing.append(f"{ev['name']}(kw={ev['kw']}, ch={ev['ch']})")
    if missing:
        print("!! 摘录未定位: " + "、".join(missing))

    # ---- 长廊页 ----
    sections = []
    for a in acts:
        cards = []
        for ev in events:
            if ev["_act"]["id"] != a["id"]:
                continue
            cast_prev = "、".join(ev["cast"][:4]) + ("…" if len(ev["cast"]) > 4 else "")
            cards.append(
                f'<a class="event-card" href="events/{ev["name"]}.html">'
                f'<span class="cat">{ev["cat"]}</span>'
                f'<span class="name">{ev["name"]}</span>'
                f'<span class="sum">{ev["sum"]}</span>'
                f'<span class="meta">{ch_display(ev["ch"])} · {ev["loc"]} · {cast_prev}</span></a>')
        sections.append(
            f'<div class="act-head"><small>{a["range"]}</small><h2>{a["name"]}</h2></div>\n'
            f'<div class="event-cards">{"".join(cards)}</div>')
    body = f"""
<header class="chead"><div class="cnum">从误走妖魔到魂聚蓼儿洼</div>
<h1>名场面</h1><div class="cmark">◆</div></header>
<p class="note">{len(events)} 幕经典场景，按叙事顺序展开 · 点击卡片进入事件页</p>
{"".join(sections)}
"""
    (SITE / "events.html").write_text(page_shell("名场面", "", body, wide=True), encoding="utf-8")

    # ---- 详情页 ----
    outdir = SITE / "events"
    outdir.mkdir(parents=True, exist_ok=True)
    for i, ev in enumerate(events):
        ex = ev["_ex"]
        if ex:
            ch_title = chapters_by_id[ex["cid"]]["title"]
            excerpt_html = (
                f'<div class="excerpt"><p>「{html.escape(ex["snip"])}…」</p>'
                f'<a class="go" href="../chapters/{ex["cid"]}.html#p{ex["n"]}">'
                f'去原文 → 第{int(ex["cid"])}回 · 段{ex["n"]}</a></div>')
            ch_link = (f'<a href="../chapters/{parse_ch_range(ev["ch"])[0]}.html">'
                       f'{ch_display(ev["ch"])}</a>〈{html.escape(ch_title)}〉')
        else:
            excerpt_html = ""
            ch_link = ch_display(ev["ch"])
        cast_chips = []
        for name in ev["cast"]:
            if name in HERO_INFO or name in EXTRA_INFO:
                cast_chips.append(f'<a class="chip" href="../wiki/{name}.html">{name}</a>')
            else:
                cast_chips.append(f'<span class="chip">{name}</span>')
        prev_ev = events[i - 1] if i > 0 else None
        next_ev = events[i + 1] if i < len(events) - 1 else None
        prev_html = f'<a href="{prev_ev["name"]}.html">← {prev_ev["name"]}</a>' if prev_ev else "<span></span>"
        next_html = f'<a href="{next_ev["name"]}.html">{next_ev["name"]} →</a>' if next_ev else "<span></span>"
        crumbs_html = (f'<div class="crumbs">{prev_html}'
                       f'<span class="crumbs-mid"><a href="../events.html">名场面长廊</a></span>'
                       f'{next_html}</div>')
        # 事件地点 → 地名词条页（自由文本里认领最长命中的地名）
        loc_place = match_place(ev["loc"])
        loc_html = (f'<a href="../wiki/{loc_place}.html">{ev["loc"]}</a>'
                    if loc_place else ev["loc"])
        chain_r = chain_row(ev["name"])
        causal_html = causal_block(ev["name"])
        body = f"""
{crumbs_html}
<header class="chead"><div class="cnum">{ev["_act"]["name"]} · {ev["cat"]}</div>
<h1>{ev["name"]}</h1><div class="cmark">◆</div></header>
<table class="infobox">
  <tr><th>类型</th><td>{ev["cat"]}</td></tr>
  <tr><th>出处</th><td>{ch_link}</td></tr>
  <tr><th>地点</th><td>{loc_html}</td></tr>
  <tr><th>阶段</th><td>{ev["_act"]["name"]}（{ev["_act"]["range"]}）</td></tr>
{chain_r}</table>
<p class="event-sum">{ev["sum"]}</p>
{"<h2>原文摘录</h2>" + excerpt_html if excerpt_html else ""}
{causal_html}
<h2>出场人物</h2>
<p class="chips">{"".join(cast_chips)}</p>
{crumbs_html}
"""
        (outdir / f"{ev['name']}.html").write_text(
            page_shell(ev["name"], "../", body), encoding="utf-8")
    return events


def hero_events(hero_name: str, events: list[dict]) -> list[dict]:
    return [ev for ev in events if hero_name in ev["cast"]]


def write_assets() -> None:
    """样式/脚本唯一源在 scripts/assets/，构建时拷贝（design.md §9）。"""
    src = ROOT / "scripts" / "assets"
    adir = SITE / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "style.css", adir / "style.css")
    shutil.copy2(src / "search.js", adir / "search.js")

# ---------------------------------------------------------------- 主流程

ENTRIES: list[dict] = []
END_COUNTS: dict = {}


def main() -> None:
    global ENTRIES, HERO_INFO, EXTRA_INFO, END_CATS, ENDINGS, END_COUNTS
    global PLACE_CATS, PLACE_REALS, PLACE_INFO
    EXTRA_INFO = {p["name"]: {"cat": p["cat"], "blurb": p["blurb"]} for p in load_extra()}
    PLACE_CATS, PLACE_REALS, places = load_places()
    PLACE_INFO = {p["name"]: p for p in places}
    ENTRIES = build_entries()
    heroes = json.loads((DATA / "heroes.json").read_text(encoding="utf-8"))
    HERO_INFO = {h["name"]: {"nick": h["nickname"], "star": h["star"], "rank": h["rank"]}
                 for h in heroes}
    END_CATS, ENDINGS = load_endings()
    END_COUNTS = {c["id"]: sum(1 for v in ENDINGS.values() if v["cat"] == c["id"])
                  for c in END_CATS}
    # 结局面板是手工数据，必须逐项对账（HANDOFF §8.9：计数不对必须查）
    missing = [h["name"] for h in heroes if h["name"] not in ENDINGS]
    unknown = [n for n in ENDINGS if n not in HERO_INFO]
    bad_cat = [n for n, v in ENDINGS.items()
               if v["cat"] not in {c["id"] for c in END_CATS}]
    if missing or unknown or bad_cat:
        print(f"!! 结局数据异常：缺 {missing} · 多 {unknown} · 非法类型 {bad_cat}")
    # 地名是手工数据，同样对账；别名撞人名会导致链接错乱，必须拦
    p_cat = {c["id"] for c in PLACE_CATS}
    p_real = {r["id"] for r in PLACE_REALS}
    bad_place = [p["name"] for p in places if p["cat"] not in p_cat or p["reality"] not in p_real]
    if bad_place:
        print(f"!! 地名数据异常：类别或虚实非法 {bad_place}")
    people_alias = {e["alias"] for e in ENTRIES if e["kind"] != "place"}
    clash = sorted({a for p in places for a in p["aliases"]} & people_alias)
    if clash:
        print(f"!! 地名别名与人名实体冲突（会造成链接错乱）：{clash}")
    curated = json.loads((DATA / "aliases_curated.json").read_text(encoding="utf-8"))
    curated = {k: v for k, v in curated.items() if not k.startswith("_")}

    chapters_cn = load_chapters(CN_DIR)
    chapters_tw = load_chapters(TW_DIR)

    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    all_ap: dict = {}   # 人物 + 地名混合统计，渲染完章节后按 kind 拆分
    render_chapters(chapters_cn, "cn", SITE / "chapters", "../", all_ap)
    render_chapters(chapters_tw, "tw", SITE / "chapters_tw", "../", None)
    people_canon = {e["canonical"] for e in ENTRIES if e["kind"] != "place"}
    place_canon = {e["canonical"] for e in ENTRIES if e["kind"] == "place"}
    appearances = {k: v for k, v in all_ap.items() if k in people_canon}
    place_ap = {k: v for k, v in all_ap.items() if k in place_canon}

    total_chars = sum(len(t) for ch in chapters_cn for _, t in ch["paras"])
    chapters_by_id = {ch["id"]: ch for ch in chapters_cn}

    events_data = json.loads((DATA / "events.json").read_text(encoding="utf-8"))
    # 因果链是手工数据，先加载再做四项体检，最后才渲染（事件页要用到索引）
    causal_data = load_causal()
    ev_names = [e["name"] for e in events_data["events"]]
    ev_set = set(ev_names)
    c_bad = sorted(({n for ch in CAUSAL_CHAINS for n in ch["events"]}
                    | {n for l in CAUSAL_LINKS for n in (l["from"], l["to"])}) - ev_set)
    c_self = [l["from"] for l in CAUSAL_LINKS if l["from"] == l["to"]]
    c_dup = [k for k, v in collections.Counter(
        (l["from"], l["to"]) for l in CAUSAL_LINKS).items() if v > 1]
    c_kind = [l["kind"] for l in CAUSAL_LINKS
              if l["kind"] not in {k["id"] for k in CAUSAL_KINDS}]
    # 孤岛：既无前因也无后果的事件，说明线索没接上
    touched = {n for l in CAUSAL_LINKS for n in (l["from"], l["to"])}
    c_island = sorted(ev_set - touched)
    if c_bad or c_self or c_dup or c_kind or c_island:
        print(f"!! 因果链数据异常：事件名不存在 {c_bad} · 自环 {c_self} · "
              f"重复边 {c_dup} · 非法类型 {c_kind} · 孤岛 {c_island}")
    c_covered = {n for ch in CAUSAL_CHAINS for n in ch["events"]}
    if ev_set - c_covered:
        print(f"!! 未被任何线索收录的事件：{sorted(ev_set - c_covered)}")
    events = render_events(events_data, chapters_by_id)
    render_causal(events_data)

    render_home(chapters_cn, {"chars": total_chars, "aliases": len(ENTRIES),
                              "events": len(events), "places": len(places),
                              "causal": len(CAUSAL_LINKS)})
    extras = load_extra()
    render_heroes(heroes, appearances, extras)
    render_endings(heroes)
    render_places(places, place_ap)
    render_wiki(heroes, appearances, curated, events)
    render_people_extra(extras, appearances, events)
    render_place_wiki(places, place_ap, events)
    render_search(chapters_cn)
    render_notfound()
    write_assets()

    n_pages = len(list(SITE.rglob("*.html")))
    print(f"渲染完成 → {SITE}")
    print(f"  HTML 页面: {n_pages}（章节 {len(chapters_cn)}×2 + 词条 {len(heroes)}+{len(extras)}+{len(places)} + 事件 {len(events)} + 首页/图鉴/结局/地名/因果/长廊/搜索/404）")
    print(f"  有出场记录的人物: {len(appearances)}/{len(heroes) + len(extras)}")
    print(f"  结局数据: {len(ENDINGS)}/{len(heroes)} 条 · "
          + " · ".join(f"{c['id']}{END_COUNTS[c['id']]}" for c in END_CATS))
    print(f"  地名: {len(place_ap)}/{len(places)} 处有出现记录 · "
          + " · ".join(f"{r['id']}{sum(1 for p in places if p['reality'] == r['id'])}"
                       for r in PLACE_REALS))
    print(f"  因果链: {len(CAUSAL_CHAINS)} 条线索覆盖 {len(c_covered)}/{len(ev_names)} 幕 · "
          f"{len(CAUSAL_LINKS)} 条边（因果 {sum(1 for l in CAUSAL_LINKS if l['kind'] == '因果')}"
          f" · 递进 {sum(1 for l in CAUSAL_LINKS if l['kind'] == '递进')}）"
          f" · 跨线索 {sum(1 for l in CAUSAL_LINKS if not is_chain_neighbour(l['from'], l['to']))} 条")
    print(f"  搜索索引: {(SITE / 'data' / 'search-index.json').stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
