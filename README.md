# CNKI MCP Server

[![PyPI version](https://img.shields.io/pypi/v/cnki-mcp-server.svg)](https://pypi.org/project/cnki-mcp-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**CNKI (中国知网) MCP Server** — 通过 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 为 AI Agent 提供中文学术论文检索能力。

> **Fork 增强版 v0.4.1**（基于 upstream v0.2.1，个人优化，欢迎取用）：
>
> 1. **GB/T 7714-2025 引文格式（默认）** — 依据 2025 年 3 月发布的新国标：支持期刊/学位论文/会议/图书/报纸五种文献类型；网络首发自动著录 `[J/OL]` + 在线出版日期 + 获取路径；中文文献全角标点、西文半角标点；新增 `get_citation_all_styles` 一次生成全部 6 种风格。旧版 `gbt7714`（2015）兼容保留。
> 2. **本机资源优先** — 支持环境变量 `CNKI_BROWSER_CHANNEL=chrome`（或 `msedge`）直接复用系统已装浏览器、`CNKI_BROWSER_EXECUTABLE` 指定浏览器路径；未找到 Playwright 内核时**默认不再自动下载**（约 300MB），确需下载设 `CNKI_AUTO_INSTALL=1`。
> 3. **新增工具（6 → 12）** — `professional_search`（知网专业检索式，实验性）、`batch_paper_details`（批量详情）、`check_cnki_access`（连通性诊断）、`get_citation_all_styles`、**`download_papers_pdf`（批量下载 PDF，机构订阅用户专用）**、**`check_download_permission`（下载权限预检）**；`export_papers` 新增 markdown。
> 4. **一键分发客户端配置** — `python -m cnki_mcp install-clients` 自动把本 MCP 写入本机已装的 WorkBuddy / VS Code / Trae CN / TRAE SOLO / Trae 国际版 / Codex / Cherry Studio / NoteGen（全部先备份；`--list` 仅探测，`--python` 指定解释器）。**幂等**：重复运行不会产生重复条目（v0.4.1 修复）。
> 5. **`python -m cnki_mcp quota`** 查看当日下载配额使用情况。
> 6. **故障排查与恢复** — 见文末专章（含分层排查法：清理磁盘 / 客户端内存态 / 浏览器内核三级定位）。
>
> 测试: `pytest tests/`（42 passed，含 GB/T 7714-2025 标准示例逐字对照用例）。

## 手机端接入（RikkaHub 等仅支持 HTTP 的客户端）

Android 客户端（如 RikkaHub）无法启动 stdio 子进程，请使用 HTTP 模式：

1. **在电脑上启动服务**（监听局域网）：

   ```bash
   python -m cnki_mcp serve-http --host 0.0.0.0 --port 37777
   ```

   仓库内已备好两个脚本：`run-http-server.bat`（带窗口，便于看日志）与
   `launch-http-hidden.vbs`（无窗口，放入启动文件夹即开机自启：
   `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`）。
   日志落在 `logs/cnki-http.log`。

2. **放行防火墙**：允许入站 TCP 37777（仅需一次）：

   ```powershell
   New-NetFirewallRule -DisplayName "CNKI MCP HTTP (TCP 37777)" -Direction Inbound -Protocol TCP -LocalPort 37777 -Action Allow
   ```

3. **在 RikkaHub 中新建连接**：设置 → MCP → 新建
   - 名称：`cnki`
   - 传输类型：**Streamable HTTP**
   - URL：`http://<电脑局域网IP>:37777/mcp`（如 `http://192.168.0.210:37777/mcp`）
   - 保存后状态变为 Connected，应同步出 12 个工具；聊天页面需手动启用该 MCP

4. **注意事项**
   - 手机与电脑须在同一局域网；Android 首次连接会申请「本地网络」权限，需允许
   - 电脑 IP 变化时 URL 需同步修改，建议在路由器为电脑做 DHCP 地址保留
   - 服务监听 `0.0.0.0` 意味着同网段设备均可访问（无鉴权）。仅建议在可信网络使用；
     下载能力有 100 篇/日配额硬限制兜底

## 批量下载 PDF（机构订阅用户）

```json
{
  "urls": "[\"https://kns.cnki.net/kcms2/article/abstract?v=...\", \"...\"]",
  "output_dir": "D:\\文献\\2026",
  "max_count": 50,
  "filename_style": "author",
  "allow_caj": false
}
```

- **配额保护**：每日硬上限 100 篇（包库常见限额），本地持久化于 `~/.cnki-mcp/download_quota.json`，超限自动停止，次日重置；`CNKI_DAILY_LIMIT` 环境变量可调
- **限速**：每篇随机间隔 8~15 秒
- **权限预检**：先调 `check_download_permission`（传一篇详情页 URL），确认 `likely_authorized: true` 再批量下载
- **老文献**：无 PDF 的会自动检测 CAJ 并标注，`allow_caj: true` 时下载 CAJ（需 CAJViewer）
- **断点续传**：已存在的同名文件自动跳过；空文件（<1KB）自动拦截且不计配额
- ⚠️ 仅供已获授权用户下载订阅内容用于个人研究，请遵守所在机构与知网使用协议，严禁批量再分发

## 功能

| 工具 | 说明 | 需要浏览器 |
|------|------|-----------|
| `search_cnki` | 搜索 CNKI 论文，支持多页、多种搜索类型和排序 | 是 |
| `professional_search` | **[新增]** 知网专业检索式精确组合检索（实验性） | 是 |
| `get_paper_detail` | 获取论文详情（标题、摘要、作者、关键词、DOI 等 17 字段） | 是 |
| `batch_paper_details` | **[新增]** 批量获取论文详情（限速防反爬） | 是 |
| `check_cnki_access` | **[新增]** 连通性与反爬状态诊断（418/验证码） | 是 |
| `find_best_match` | 快速匹配论文标题，验证引用信息 | 是 |
| `format_citation` | 引文格式化（**GB/T 7714-2025 默认**、2015 兼容、APA, MLA, Chicago, Vancouver；5 种文献类型） | 否 |
| `get_citation_all_styles` | **[新增]** 一次生成全部 6 种风格引文 | 否 |
| `browse_journals` | 期刊浏览（学科分类、期刊搜索、最新文章） | 是 |
| `export_papers` | 批量导出（CSV, JSON, BibTeX, RIS, **Markdown**） | 否 |

### 搜索类型

支持 15 种搜索类型：主题、关键词、篇名、作者、作者单位、全文、DOI、基金、摘要等（中英文别名均可）。

### 排序方式

相关度 / 发表时间 / 被引 / 下载 / 综合（支持英文别名：relevance, date, cited, download, composite）。

## 安装

```bash
pip install cnki-mcp-server
```

**本 fork 默认不下载浏览器内核**（upstream 会要求 `python -m playwright install chromium`）。启动优先级：

1. `CNKI_BROWSER_EXECUTABLE=<浏览器路径>` — 显式指定
2. `CNKI_BROWSER_CHANNEL=chrome`（或 `msedge`）— 复用系统已装的 Chrome / Edge，**零下载**
3. 复用本机已有的 Playwright 内核缓存（Windows: `%LOCALAPPDATA%\ms-playwright`）— **零下载**
4. 以上都没有时：默认报错并给出指引；确需下载才设 `CNKI_AUTO_INSTALL=1`（约 300MB）

只在需要全新内核时才手动执行：

```bash
CNKI_AUTO_INSTALL=1 python -m cnki_mcp   # 或
python -m playwright install chromium
```

> **新版 Ubuntu（26.04+）用户**: Playwright 尚未官方支持 Ubuntu 26.04，请设置环境变量后再安装 Chromium：
> ```bash
> PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 python -m playwright install chromium
> ```
>
> **SOCKS 代理用户**: 如果系统配置了 SOCKS 代理（`ALL_PROXY=socks5://...`），请确保安装时包含 socks 支持：
> ```bash
> pip install cnki-mcp-server[socks]
> ```

## 代理配置

如果你的网络环境需要通过代理访问外网，代码会自动读取以下环境变量：

| 环境变量 | 说明 |
|----------|------|
| `CNKI_PROXY` | 代理地址（优先使用），如 `socks5://127.0.0.1:<port>` 或 `http://127.0.0.1:<port>` |
| `HTTPS_PROXY` / `https_proxy` | 标准 HTTPS 代理地址（`CNKI_PROXY` 未设置时使用） |
| `ALL_PROXY` / `all_proxy` | 全局代理地址（上述均未设置时使用） |
| `CNKI_PROXY_USERNAME` / `PROXY_USERNAME` | 代理用户名（需要认证时使用） |
| `CNKI_PROXY_PASSWORD` / `PROXY_PASSWORD` | 代理密码（需要认证时使用） |
| `NO_PROXY` / `no_proxy` | 不走代理的域名/地址列表，逗号分隔 |

> **注意**:
> - Playwright 不支持 `socks5h://`（DNS 通过代理解析），会自动替换为 `socks5://`。
> - 如果你使用 Clash 等系统代理，强烈建议用 `NO_PROXY` 排除 CNKI，让 CNKI 走直连避免 CDN 拦截。

### 常见场景

**场景一：系统已配置全局代理，CNKI 需要直连**

只需要排除 CNKI 即可，无需额外设置代理变量：

```json
{
  "mcpServers": {
    "cnki": {
      "command": "python",
      "args": ["-m", "cnki_mcp"],
      "env": {
        "NO_PROXY": "cnki.net,*.cnki.net"
      }
    }
  }
}
```

**场景二：MCP 进程需要独立的代理配置**

```json
{
  "mcpServers": {
    "cnki": {
      "command": "python",
      "args": ["-m", "cnki_mcp"],
      "env": {
        "HTTPS_PROXY": "<你的代理地址>",
        "NO_PROXY": "cnki.net,*.cnki.net"
      }
    }
  }
}
```

**场景三：新版 Ubuntu，需要指定 Playwright 平台**

```json
{
  "mcpServers": {
    "cnki": {
      "command": "python",
      "args": ["-m", "cnki_mcp"],
      "env": {
        "NO_PROXY": "cnki.net,*.cnki.net",
        "PLAYWRIGHT_HOST_PLATFORM_OVERRIDE": "ubuntu24.04-x64"
      }
    }
  }
}
```

## 使用

CNKI MCP Server 是一个标准 MCP 服务器，支持所有兼容 MCP（Model Context Protocol）的 AI Agent 平台。

### OpenCode

在 OpenCode 配置文件（`~/.config/opencode/config.json` 或项目 `.opencode.json`）中添加：

```json
{
  "mcpServers": {
    "cnki": {
      "command": "python",
      "args": ["-m", "cnki_mcp"]
    }
  }
}
```

### Claude Code

在 `.claude/settings.json` 中添加：

```json
{
  "mcpServers": {
    "cnki": {
      "command": "python",
      "args": ["-m", "cnki_mcp"]
    }
  }
}
```

### Claude Desktop

在 Claude Desktop 配置（`~/Library/Application Support/Claude/claude_desktop_config.json`）中添加：

```json
{
  "mcpServers": {
    "cnki": {
      "command": "python",
      "args": ["-m", "cnki_mcp"]
    }
  }
}
```

### Cursor

在 Cursor 设置 → MCP 中添加新服务器，或编辑 `~/.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "cnki": {
      "command": "python",
      "args": ["-m", "cnki_mcp"]
    }
  }
}
```

### Windsurf

在 `~/.codeium/windsurf/mcp_config.json` 中添加：

```json
{
  "mcpServers": {
    "cnki": {
      "command": "python",
      "args": ["-m", "cnki_mcp"]
    }
  }
}
```

### VS Code / Cline

在 Cline 扩展设置 → MCP Servers 中添加，或编辑 `~/AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`：

```json
{
  "mcpServers": {
    "cnki": {
      "command": "python",
      "args": ["-m", "cnki_mcp"]
    }
  }
}
```

### VS Code / Continue

在 Continue 配置（`~/.continue/config.json`）中添加：

```json
{
  "experimental": {
    "mcpServers": {
      "cnki": {
        "command": "python",
        "args": ["-m", "cnki_mcp"]
      }
    }
  }
}
```

### 命令行直接使用

```bash
python -m cnki_mcp
```

## 要求

- Python >= 3.10
- Playwright Chromium（首次使用时自动安装）

## 引文格式

| 风格 | 标准 | 适用场景 |
|------|------|----------|
| `gbt7714` | GB/T 7714-2015 | 中文学位论文、中文期刊 |
| `apa` | APA 7th Edition | 心理学、教育学、社会科学 |
| `mla` | MLA 9th Edition | 语言文学、人文学科 |
| `chicago` | Chicago Notes & Bibliography | 历史学、艺术学 |
| `vancouver` | Vancouver/ICMJE | 生物医学、临床医学 |

## 导出格式

| 格式 | 适用软件 |
|------|----------|
| JSON | 编程处理、数据分析 |
| CSV | Excel、Google Sheets |
| BibTeX | LaTeX、Zotero、JabRef |
| RIS | EndNote、Mendeley、Zotero |

## 技术实现

- **引擎**: Playwright（自带签名 Chromium，消除 macOS codesign 问题，跨平台零配置）
- **MCP 框架**: FastMCP
- **并发**: 原生 async/await
- **反检测**: 随机 User-Agent、模拟人类输入、navigator.webdriver 覆写
- **会话复用**: 共享 BrowserContext，Cookie 互通，避免 CNKI 验证码

## 开发

```bash
git clone https://github.com/xxxxchaos/cnki-mcp-server.git
cd cnki-mcp-server
pip install -e ".[dev]"
python -m playwright install chromium
pytest tests/ -v
```

## 故障排查

### Playwright 安装失败（Ubuntu 26.04+）

```
Failed to install browsers
Error: ERROR: Playwright does not support chromium on ubuntu26.04-x64
```

**解决方法**: 设置 `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64` 环境变量后重新安装。

### SOCKS 代理报错

```
ImportError: Using SOCKS proxy, but the 'socksio' package is not installed.
```

**解决方法**: 安装 socks 支持 `pip install httpx[socks]`，或升级到最新版 cnki-mcp-server。

### CNKI 返回 418 或空页面

```
Status: 418
server: TencentEdgeOne
```

**原因**: CNKI 的 CDN（TencentEdgeOne）对代理/服务器 IP 做了反爬拦截。

**解决方法**:
1. 设置 `NO_PROXY=cnki.net,*.cnki.net` 让 CNKI 直连本地网络（推荐）
2. 更换代理 IP 或使用住宅 IP
3. 确保运行环境能够正常访问 `https://www.cnki.net/`

### 搜索框找不到（#txt_SearchText 超时）

```
Locator.wait_for: Timeout 15000ms exceeded.
waiting for locator("#txt_SearchText") to be visible
```

**原因**: CNKI 首页未正确加载，通常是网络问题或被反爬拦截。

**解决方法**: 先确认在浏览器中能否正常打开 `https://www.cnki.net/`，如果不行则参考上一条「CNKI 返回 418」的解决方案。

### 搜索结果为空（中英文混合查询）

```
搜索 "ECMO 抗凝" 返回 0 条结果，但 "体外膜肺氧合 抗凝" 返回 40 条
```

**原因**: CNKI 搜索引擎对中英文混合关键词（如 `ECMO 抗凝`、`AI 辅助诊断`）的匹配效果不佳，短英文缩写与中文词拼接时可能返回空结果。

**解决方法**: 将英文缩写替换为中文全称，例如：
- `ECMO 抗凝` → `体外膜肺氧合 抗凝`
- `AI 诊断` → `人工智能 诊断`

### 客户端里 MCP 不可用（分层排查法）

不要一上来重装。按五层从下往上验证，能快速定位到底坏在哪一层：

| 层 | 验证方法 | 正常表现 |
|---|---------|---------|
| ① 解释器与包 | `<venv>\Scripts\python.exe -c "import cnki_mcp; print(cnki_mcp.__version__)"` | 打印版本号 |
| ② 浏览器内核 | 检查 `%LOCALAPPDATA%\ms-playwright\chromium-*\chrome-win64\chrome.exe` 存在 | 新版目录名是 **`chrome-win64`**（旧版才是 `chrome-win`） |
| ③ 服务器 | `<venv>\Scripts\python.exe -m cnki_mcp` 后发一条 `initialize` JSON-RPC | 返回 `serverInfo` |
| ④ 浏览器真启动 | Playwright `chromium.launch(headless=True)` 后打开知网 | 拿到标题「中国知网」 |
| ⑤ 客户端配置与进程 | 见下 | — |

**⑤ 客户端层最常见的三类问题：**

- **内存态缓存**（Cherry Studio、NoteGen 等）：清理磁盘或改配置时客户端仍在运行，它读的是启动时缓存的配置。**彻底退出再启动**（托盘常驻的要从托盘退出），多数情况重启即恢复。
- **配置未生效**：图形客户端需要重启后才加载新配置；WorkBuddy 需在连接器页面对新 server 点 Trust。
- **重新登记配置**：`python -m cnki_mcp install-clients` 幂等重刷（先备份，重复运行不会产生重复条目）。

### 磁盘清理后失效

实测经验：清理 C 盘通常**不会**影响本 MCP——venv、内核缓存、配置都在，命令行与浏览器均正常，报错几乎都来自客户端内存态（重启即可）。各组件位置：

| 组件 | 位置 | 说明 |
|---|---|---|
| venv 解释器 | `~/.workbuddy/binaries/python/envs/cnki/` | 被删才需重装依赖 |
| 浏览器内核 | `%LOCALAPPDATA%\ms-playwright/` | 被删可设 `CNKI_AUTO_INSTALL=1` 重下，或用 `CNKI_BROWSER_CHANNEL=chrome` 改用系统 Chrome |
| 下载配额 | `~/.cnki-mcp/download_quota.json` | 删掉即重置为 0 |
| NoteGen 配置 | `%APPDATA%/com.codexu.NoteGen/store.json` 的 `mcp.servers` | `local-mcp.json` 只是派生文件，会被应用重写 |
| Cherry Studio 配置 | `%APPDATA%/CherryStudio/Data/cherrystudio.sqlite` 的 `mcp_server` 表 | 需完全退出应用后再改 |

### 下载配额已用完

```
今日下载配额已用完（100 篇/日，已用 100）
```

配额按自然日计，次日自动重置。查看用 `python -m cnki_mcp quota`；调整限额设 `CNKI_DAILY_LIMIT`；确需重置可删除 `~/.cnki-mcp/download_quota.json`。

## 许可

MIT License
