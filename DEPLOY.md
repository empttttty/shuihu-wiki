# 部署手册 (DEPLOY.md)

> 目标：本地改完 → 一条 push → Cloudflare 自动上线。
> 手工上传 dist 的老办法（md2mp 那种）本项目**不用**。

---

## 0. 架构：为什么这样设计

```
本地仓库 ~/WorkBuddy/shuihu-wiki
        │  git push
        ▼
GitHub 公开仓库  (源码 + 生成好的 site/)
        │  Cloudflare Pages 监听 main 分支
        ▼
Cloudflare Pages  →  https://<项目名>.pages.dev
```

**关键决定：把生成好的 `site/` 一起提交，Cloudflare 只做托管，不跑 Python 构建。**

理由：

| 方案 | 结果 |
|---|---|
| **A. 提交 `site/`，CF 构建命令留空**（本方案） | ✅ 部署秒级完成、零失败风险；站点质量由本地 `check_links.py` 体检把关（571 页 / 88,357 条链接全 0 失效） |
| B. 让 CF 跑 `python scripts/render_site.py` | ❌ `render_site.py` 依赖 OpenCC（C++ 扩展包），CF 构建镜像能否装上不确定；且会让未经本地体检的产物直接上线 |

项目是内容型静态站，**本地渲染 = 唯一真源**，所以 A 才是正解。

---

## 1. 一次性设置

### 1.1 GitHub 仓库

仓库：`https://github.com/<你的用户名>/shuihu-wiki`（公开）

已由 AI 完成：`git init`、`.gitignore`、首次提交、推送到 main。

> `.workbuddy/`（AI 工作记忆与项目日志）已在 `.gitignore` 中排除，不进公开仓库。

### 1.2 Cloudflare Pages 连接仓库

1. 打开 <https://dash.cloudflare.com> → 左侧 **Workers & Pages**
2. **Create** → 选 **Pages** 标签 → **Connect to Git**
3. 授权 GitHub（选 "Only select repositories" → 勾 `shuihu-wiki`）→ 选中仓库 → **Begin setup**
4. 填构建配置（**这里最容易填错，照抄**）：

| 字段 | 填什么 |
|---|---|
| Project name | `shuihu-wiki`（决定域名 `shuihu-wiki.pages.dev`） |
| Production branch | `main` |
| Framework preset | `None` |
| Build command | **留空**（不要填任何东西） |
| Build output directory | `site` |
| Root directory | 留空 |

5. **Save and Deploy**

> ⚠️ 不要复用 `md2mp` 那个项目——它是 Direct Upload（手工上传）类型，无法接 Git，只能新建。

### 1.3 上线后必查

1. 打开 `https://shuihu-wiki.pages.dev` → 首页正常
2. 点进任意一回（如 `/chapters/003.html`）
3. **重点验中文路径**：点任意好汉名（如「宋江」）→ 应打开 `/wiki/宋江.html`，不要 404
   （本站词条页文件名是中文，CF Pages 走 URL 解码匹配；万一 404，见第 4 节降级方案）
4. 搜一个词（搜索页有 JS，验一下 `/search.html`）

---

## 2. 日常更新（一条命令链路）

改完 `data/*.json` 或 `corpus/` 之后：

```bash
PY=~/.workbuddy/binaries/python/envs/default/bin/python
cd ~/WorkBuddy/shuihu-wiki

$PY scripts/render_site.py      # 1. 重建 site/（整体重建）
$PY scripts/check_links.py      # 2. 体检：断链 + 锚点，必须全 0
git add -A
git commit -m "说明这次改了什么"
git push                        # 3. Cloudflare 自动重新部署（约 1 分钟）
```

**第 2 步不能跳。** 链接体检是本地唯一的守门人——因为 CF 那边不做任何校验，推上去就是线上。

查看部署进度：CF Dashboard → Workers & Pages → shuihu-wiki → Deployments。
失败时看某次部署的 Build log（虽然本项目构建命令为空，一般只有同步文件的过程）。

---

## 3. 交给 AI 的话怎么说

> 「改完 X 之后，重建 + 体检 + push 上线。」

AI 会执行第 2 节那条链路。前提：本机 `gh` 已授权（`gh auth status` 返回已登录）。

---

## 4. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 首页 404 | Build output directory 填错 | 改成 `site`（不是 `/site`、不是 `site/`） |
| 全部页面 404 | 构建命令填了东西 | Build command 必须留空 |
| 中文词条页 404，英文页面正常 | CF Pages 对非 ASCII 文件名的兼容问题 | 降级方案：改 `render_site.py`，词条页改用拼音/编号 slug（`wiki/song-jiang.html`），中文名留在显示层；同时改 `check_links.py` 一起验 |
| 部署成功但页面没变 | CF 缓存 | Deployments 里确认最新一次是 success；强制刷新（Cmd+Shift+R） |
| push 报 403/权限 | gh 授权过期 | 重新 `gh auth login` |
| 站点整体变旧 | 忘了 push | 本地 `git status` 看有没有未提交改动 |

---

## 5. 本地预览（不用等线上）

```bash
cd ~/WorkBuddy/shuihu-wiki
python3 -m http.server 8000 --directory site
# 浏览器打开 http://localhost:8000
```
