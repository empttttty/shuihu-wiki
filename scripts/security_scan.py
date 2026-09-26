#!/usr/bin/env python3
"""提交前安全审计：扫描敏感信息，防止泄露进公开仓库。

用法:
    $PY scripts/security_scan.py            # 全量扫描所有被跟踪文件（手动体检）
    $PY scripts/security_scan.py --staged   # 只扫暂存区新增行（pre-commit 钩子用）

规则:
    - 命中任一项 → 退出码 1 并打印「文件: 规则名: 命中片段」
    - 全部干净  → 退出码 0
    - --staged 模式额外检查：敏感文件名入库 + 提交邮箱必须是 noreply

基线见 .workbuddy/memory/MEMORY.md 第 11 条（2026-09-26 历史改写后确立）。
新增误报时改 ALLOW 放行，不要删 PATTERNS——宁可多报不可漏报。
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (规则名, 正则) —— 针对新增行逐条匹配
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("GitHub PAT", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("GitHub fine-grained PAT", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("OpenAI 风格 key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Google API Key", re.compile(r"AIza[0-9A-Za-z_-]{20,}")),
    ("私钥块", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("口令赋值", re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|client[_-]?secret"
        r"|password|passwd|pwd|auth[_-]?token|access[_-]?token|refresh[_-]?token)"
        r"\b\s*[:=：]\s*[\"']?[A-Za-z0-9_/+\-.]{8,}")),
    ("邮箱地址", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("本机用户路径", re.compile(r"/Users/[A-Za-z0-9._-]+")),
    ("手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("IPv4 地址", re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")),
]

# 放行规则（命中 PATTERNS 但属于安全写法）
ALLOW: list[re.Pattern] = [
    re.compile(r"git@github\.com"),                              # SSH remote 地址
    re.compile(r"@users\.noreply\.github\.com"),                 # GitHub noreply 邮箱
    re.compile(r"(?<![\d.])127\.0\.0\.1(?![\d.])"),              # 本机回环
    re.compile(r"(?<![\d.])0\.0\.0\.0(?![\d.])"),
]

# 不扫描的文件（自身规则定义所在，避免误伤）
SKIP_FILES = {"scripts/security_scan.py"}

# 敏感文件名（任何路径段命中即拒绝入库）
SENSITIVE_NAME = re.compile(
    r"(?i)(^|/)(\.env(\..*)?|[^/]*\.(pem|p12|pfx|keystore|htpasswd)"
    r"|id_rsa.*|id_ed25519.*|credentials(\..*)?)$")

MAX_SNIPPET = 60


def allowed(line: str) -> bool:
    return any(p.search(line) for p in ALLOW)


def check_line(relpath: str, line: str, hits: list[str]) -> None:
    if allowed(line):
        return
    for name, pat in PATTERNS:
        m = pat.search(line)
        if m:
            snippet = m.group(0)
            if len(snippet) > MAX_SNIPPET:
                snippet = snippet[:MAX_SNIPPET] + "…"
            hits.append(f"{relpath}: [{name}] {snippet}")


def scan_staged() -> tuple[list[str], list[str]]:
    """扫暂存区：新增行内容 + 入库文件名。返回 (内容命中, 文件名命中)。"""
    diff = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--cached", "--unified=0", "--no-color"],
        capture_output=True, text=True, check=True).stdout
    hits: list[str] = []
    current = None
    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            current = line[len("+++ b/"):]
        elif line.startswith("+++ "):  # 新增文件以外的头部（如 /dev/null 目标）
            current = None
        elif line.startswith("+") and not line.startswith("+++"):
            if current and current not in SKIP_FILES:
                check_line(current, line[1:], hits)

    names = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--cached", "--name-only", "--diff-filter=ACR"],
        capture_output=True, text=True, check=True).stdout.split()
    name_hits = [n for n in names if SENSITIVE_NAME.search(n)]
    return hits, name_hits


def scan_all() -> tuple[list[str], list[str]]:
    """全量扫工作区所有被跟踪文件。"""
    files = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True, text=True, check=True).stdout.split()
    hits: list[str] = []
    for rel in files:
        if rel in SKIP_FILES:
            continue
        p = ROOT / rel
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # 二进制/不可读文件跳过（本站无密钥型二进制）
        for line in text.split("\n"):
            check_line(rel, line, hits)
    name_hits = [f for f in files if SENSITIVE_NAME.search(f)]
    return hits, name_hits


def check_committer_email() -> str | None:
    """提交邮箱必须是 GitHub noreply，防止真实邮箱进历史（仅 --staged 检查）。"""
    email = subprocess.run(
        ["git", "-C", str(ROOT), "config", "user.email"],
        capture_output=True, text=True).stdout.strip()
    if not email.endswith("@users.noreply.github.com"):
        return (f"提交邮箱是「{email or '(未设置)'}」，会进公开历史。"
                f"修复: git config user.email \"20416908+empttttty@users.noreply.github.com\"")
    return None


def main() -> int:
    staged = "--staged" in sys.argv
    hits, name_hits = scan_staged() if staged else scan_all()

    problems = [f"敏感文件名: {n}" for n in name_hits] + hits
    if staged:
        email_err = check_committer_email()
        if email_err:
            problems.append(email_err)

    if problems:
        print(f"✗ 安全审计未通过（{len(problems)} 项），已阻止：", file=sys.stderr)
        for p in problems[:30]:
            print(f"  {p}", file=sys.stderr)
        if len(problems) > 30:
            print(f"  … 另有 {len(problems) - 30} 项", file=sys.stderr)
        print("确认是误报 → 在 scripts/security_scan.py 的 ALLOW 里加放行规则；"
              "确认是敏感信息 → 移除后再提交。", file=sys.stderr)
        return 1

    mode = "暂存区" if staged else "全仓库"
    print(f"✓ 安全审计通过（{mode}）：无密钥/邮箱/本机路径等敏感信息")
    return 0


if __name__ == "__main__":
    sys.exit(main())
