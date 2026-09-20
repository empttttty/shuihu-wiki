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
Cloudflare Pages  →  https://shuihu-wiki.pages.dev
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

仓库：`https://github.com/empttttty/shuihu-wiki`（公开）
remote：`git@github.com:empttttty/shuihu-wiki.git`（SSH 免密，本机 `~/.ssh/id_ed25519` 已加到 GitHub 账号）

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

### 1.3 上线后实测记录（2026-09-20 22:59，全部通过）

线上地址：**https://shuihu-wiki.pages.dev**

| 检查项 | 实测结果 |
|---|---|
| 首页 `/` | ✅ 200，14.7 KB |
| 章节页 `/chapters/003.html` | ✅ 200，title「第三回　史大郎夜走华阴县　鲁提辖拳打镇关西 · 水浒维基」 |
| **中文词条页 `/wiki/宋江.html`** | ✅ **200，title「宋江 · 水浒维基」，正文含「及时雨 / 呼保义 / 天魁星」** |
| 其他页 `/heroes`、`/events`、`/endings`、`/causal`、`/places`、`/chapters_tw/120.html` | ✅ 全部 200 |
| 样式与脚本 `/assets/style.css`、`/assets/search.js` | ✅ 200 |
| 搜索索引 `/data/search-index.json` | ✅ 200，2.7 MB |

**结论：中文文件名（词条页 `/wiki/宋江`）在 Cloudflare Pages 上完全正常，不需要第 4 节的拼音 slug 降级方案。** 词条页内的相对路径引用（`../assets/style.css`）在归一路径下解析依然正确。

#### 两个已知的线上行为（Cloudflare 侧特性，不是 bug，但要知道）

1. **`.html` 后缀会被 308 归一化**：请求 `/chapters/003.html` 或 `/wiki/宋江.html` 时会 308 跳转到无后缀路径（`/wiki/宋江`），最终 200。站内每条链接因此多一跳，功能无障碍。
2. **不存在的路径返回 200 + 首页（软 404）**：实测 `/wiki/nonexistent-xyz.html`、`/no-such-dir/no-such-page.html` 都返回首页内容且状态码 200。这是当前站点的短板——**待办：生成 `site/404.html`**（Cloudflare Pages 检测到输出目录里有 `404.html` 时，会用它作为 404 响应并返回真正的 404 状态码）。

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

AI 会执行第 2 节那条链路。前提：本机 SSH 密钥已加到 GitHub 账号（`ssh -T git@github.com` 返回 `Hi empttttty!`）。`gh` CLI 未登录**不影响** push——我们走 SSH 而非 gh。

---

## 4. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 首页 404 | Build output directory 填错 | 改成 `site`（不是 `/site`、不是 `site/`） |
| 全部页面 404 | 构建命令填了东西 | Build command 必须留空 |
| 中文词条页 404 | ~~CF Pages 对非 ASCII 文件名不兼容~~ → **已实测不会发生**（2026-09-20 验证通过） | 无需处理。万一将来出现：改 `render_site.py` 把词条页改用拼音 slug（`wiki/song-jiang.html`），中文名留在显示层，同时改 `check_links.py` 一起验 |
| 点错链接却看到首页 | CF 对未匹配路径返回 200 + 首页（软 404） | 待办：生成 `site/404.html`，CF 会用真正的 404 状态码 |
| 链接会多一跳 308 | CF 自动归一化掉 `.html` 后缀 | 正常行为，无需处理 |
| 部署成功但页面没变 | CF 缓存 | Deployments 里确认最新一次是 success；强制刷新（Cmd+Shift+R） |
| push 报 403 / 权限 | SSH 密钥失效或未加到 GitHub | 重新生成密钥并加到 GitHub（Settings → SSH and GPG keys）；`ssh -T git@github.com` 自测 |
| 站点整体变旧 | 忘了 push | 本地 `git status` 看有没有未提交改动 |

---

## 5. 本地预览（不用等线上）

```bash
cd ~/WorkBuddy/shuihu-wiki
python3 -m http.server 8000 --directory site
# 浏览器打开 http://localhost:8000
```
