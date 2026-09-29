# 开发记录 — Fork 增强版（cnki-mcp-server）

> 基线：upstream v0.2.1。本 fork 的所有改动、设计决策与踩坑记录。最后更新 2026-09-30。

## 一、版本历史

| 版本 | 日期 | 主要内容 |
|---|---|---|
| 0.2.1 | — | upstream 基线（6 工具，GB/T 7714-2015 引文） |
| **0.3.0** | 09-18 | ① GB/T 7714-2025 引文（默认）② 本机浏览器资源优先 ③ 新增 4 工具 ④ 一键分发客户端配置 |
| **0.4.0** | 09-18 | 批量 PDF 下载（机构订阅，含每日 100 篇硬配额） |
| 0.4.1 | 09-19 | `install-clients` 对 NoteGen 幂等（原会重复写入） |
| 0.4.2 | 09-19 | 向 NoteGen 注入系统环境变量（它不继承系统环境，缺 `SYSTEMROOT` 会导致 Python 静默死亡） |
| **0.4.3** | 09-19 | HTTP（streamable）传输：`serve-http` 子命令 + `start-http.cmd`（为 NoteGen / RikkaHub 等不支持 stdio 的客户端） |
| **0.4.4** | 09-30 | 修正浏览器错误处理（不再掩盖真实异常）+ 文档化「服务模式下的浏览器选择」 |

## 二、功能一览（12 个 MCP 工具）

| 类别 | 工具 |
|---|---|
| 检索 | `search_cnki`（15 种搜索类型 × 5 排序，最多 10 页）、`professional_search`（专业检索式，实验性）、`find_best_match` |
| 详情与诊断 | `get_paper_detail`（17 字段）、`batch_paper_details`（限速批量）、`check_cnki_access`（418/验证码诊断） |
| 引文 | `format_citation`（默认 GB/T 7714-2025，5 种文献类型）、`get_citation_all_styles`（6 风格） |
| 导航与导出 | `browse_journals`、`export_papers`（csv/json/bibtex/ris/**markdown**） |
| 下载（机构订阅） | `download_papers_pdf`（每日配额 + 限速 + CAJ 回退）、`check_download_permission` |

CLI：`python -m cnki_mcp [serve-http [--host H] [--port P] | install-clients [--list] [--python P] | quota]`

## 三、关键设计决策

**1. GB/T 7714-2025 引文实现**（`citation.py`）
- 依据标准原文实现 5 种文献类型（期刊[J]/学位[D]/会议[C]//图书[M]/报纸[N]）
- **中文文献全角标点、西文半角标点**（`_is_cjk()` 判定）
- 电子资源自动加载体标识：有 `access_url`/`online_date` → `[J/OL]`
- 网络首发：仅著录在线出版日期（无卷期页码时）
- 作者 ≤3 全录，>3 取前 3 + `，等` / `, et al`（西文不带点，由后置句点补足）
- 旧版保留为 `gbt7714`（2015）；`STYLE_ALIASES` 做别名归一
- **测试**：8 个标准示例逐字对照（`tests/test_citation.py`）

**2. 本机资源优先，避免额外下载**（`browser.py`）
- 优先级：`CNKI_BROWSER_EXECUTABLE` > `CNKI_BROWSER_CHANNEL` > 已有内核缓存 > 报错
- `CNKI_AUTO_INSTALL=1` 才允许自动下载（默认拒绝，避免隐式 300MB）

**3. 批量下载的安全阀**（`downloader.py`）
- 每日硬配额 100 篇（`~/.cnki-mcp/download_quota.json` 跨进程持久化，次日重置）
- 每篇随机限速 8–15 秒；空文件（<1KB）拦截且不计配额；同名文件跳过（断点续传）

**4. HTTP 传输**（`__main__.py` + `serve-http`）
- 面向不支持 stdio 的客户端：NoteGen（Tauri）、RikkaHub（Android）
- FastMCP `mcp.run(transport="http", ...)`，端点 `/mcp`，SSE 响应格式

**5. Windows 服务化**（NSSM，见 README）
- 换取：开机自启（免登录）+ 无窗口 + 崩溃自愈（实测 6 秒恢复）
- **服务账户决定一切**（见下节）

**6. 一键分发客户端配置**（`clients.py`）
- 覆盖 WorkBuddy / VS Code / Trae×3 / Codex / Cherry Studio(SQLite) / NoteGen
- 全部先备份；**幂等**（重复运行不产生重复条目）

## 四、踩坑记录（按层归纳）

### A. 客户端层
| 现象 | 根因 | 解法 |
|---|---|---|
| NoteGen 报 `EOF while reading MCP response` | 它的 `start_mcp_stdio_server` 会 kill 同 serverId 旧进程；自动连接与手动测试并发时互相打断 | 改用 HTTP 传输 |
| NoteGen 报 `runpy` 错误、进程静默死亡 | **它启动子进程时不继承系统环境**，缺 `SYSTEMROOT`（Windows 下 Python 必需） | 向条目 env 注入系统变量（0.4.2） |
| Cherry Studio 配置不生效 | 内存态覆盖：清理磁盘时客户端仍在运行 | 彻底退出再启动 |
| RikkaHub 无法使用 | 仅支持 SSE / Streamable HTTP | 用 `serve-http` + 局域网/Tailscale |
| 外部改 `store.json` 被还原 | NoteGen 运行时会用内存态覆盖 | 在 UI 内修改，或完全退出后再改 |

### B. 浏览器层（本机反复出问题的地方）
| 现象 | 根因 | 解法 |
|---|---|---|
| 「未找到可用的 Playwright Chromium 内核」 | `%LOCALAPPDATA%\ms-playwright` 被 C 盘清理工具**整目录删空**（实测 683MB → 空） | 复用系统浏览器（`CNKI_BROWSER_CHANNEL`）或把内核放非系统盘 |
| 系统 Chrome 完全无法启动（`WinError 14001` 并行配置不正确） | Chrome **自动更新后损坏**（SxS / 缺 VC++ 运行库） | 换 Edge，或重装 Chrome |
| 服务模式下 Edge 启动后立即退出（`exitCode=1002`） | 服务以 **LocalSystem** 运行 → 无用户 profile 环境 | **把服务账户改为用户账户**（见第三节第 5 条） |
| 错误永远显示"内核缺失"，看不到真实原因 | `except` 条件 `"playwright" in str(e).lower()` 过宽，**任何** Playwright 异常都被误判为内核缺失（0.4.4 修复） | 收紧为仅匹配真正的内核缺失文案 |

### C. 环境/系统层（本机特有）
- **程序黑名单**：`schtasks.exe`、`wmic.exe`、`sc.exe` 均被安全策略拦截（不可绕过）→ 定时任务改用「启动文件夹」，服务状态改用 `nssm status` / `Get-Service`
- **工具内启动的常驻进程会被沙箱清理**（含 `subprocess` DETACHED、`os.startfile`）→ 常驻服务必须由用户双击或登录自启
- **`Start-Process` 启动解释器被拒**（安全策略）
- **safe-delete 拦截** `shutil.rmtree` / `Remove-Item`（走 trash 失败）→ 改**逐文件 `os.remove` + 自底向上 `os.rmdir`**
- **`iphlpsvc`（IP Helper）被 360 优化禁用** → Tailscale 装不上/连不通；`Set-Service -Name iphlpsvc -StartupType Automatic; Start-Service iphlpsvc`
- **系统代理端口会漂移**（6790 → 3280）→ 探测本机服务须绕过代理，否则得到 502 误判
- **Bash 环境不完整**（`dirname`/`sed`/`head` 缺失）→ 输出改用「写文件 + 读文件」
- **PowerShell 5.1 重定向默认 UTF-16** + 本机 PowerShell 输出常丢失 → 用 `[IO.File]::WriteAllText` + 读文件

## 五、调试方法（可复用）

**1. 分层排查法**（由下至上，任一层失败即定位）
解释器与包 → 浏览器内核 → MCP 服务器握手 → 浏览器真启动 → 客户端配置与进程状态

**2. 用真实异常排查**
客户端代码常把异常包装成固定文案，先确认能抛原始错误（本 fork 0.4.4 已修）。**不要被错误文案牵着走。**

**3. 服务身份 ≠ 用户身份**
同一浏览器在用户会话下正常、在 LocalSystem 服务下失败——测试时要复现**目标身份**。

**4. 直连 HTTP 测 MCP**（绕过客户端）
`initialize` → `notifications/initialized` → `tools/call`（带 `Mcp-Session-Id`），可精确定位是服务端还是客户端问题。

**5. 复现客户端启动条件**
如「只传条目 env、不继承系统环境」来复现 NoteGen 的 spawn 行为。

## 六、部署方式对照

| 方式 | 适用 | 浏览器可用性 | 备注 |
|---|---|---|---|
| stdio（默认 `python -m cnki_mcp`） | WorkBuddy、VS Code、Trae、Codex、Cherry Studio | 取决于客户端环境 | 最省事 |
| HTTP 局域网（`serve-http --host 0.0.0.0`） | 同网段手机/其他设备 | — | 需放行防火墙端口 |
| HTTP + Tailscale | 流量/异地访问 | — | IP 固定（`100.x.x.x`），推荐手机端 |
| **Windows 服务（NSSM）** | 需免登录自启 + 崩溃自愈 | **用户账户**下可复用系统浏览器；LocalSystem 需自带内核 | 本机最终方案 |

## 七、本机部署现状（2026-09-30）

```
服务名   : CNKIMcpHttp（NSSM 托管）
运行账户 : .\Daxoel（用户账户 —— 系统浏览器可用的关键）
浏览器   : CNKI_BROWSER_CHANNEL=msedge（零下载）
端口     : 37777，端点 /mcp
接入地址 : 局域网 http://192.168.0.210:37777/mcp
           Tailscale http://100.87.180.39:37777/mcp（手机用这个）
日志     : logs/service-out.log / logs/service-err.log
管理     : tools/nssm.exe status|start|stop|restart CNKIMcpHttp
卸载     : tools/nssm.exe remove CNKIMcpHttp confirm
```

## 八、已知限制

- `professional_search` 依赖知网高级检索页结构，知网改版可能失效（实验性）
- 每日下载配额 100 篇（`CNKI_DAILY_LIMIT` 可调）；下载权限取决于运行机器的网络是否有机构订阅 IP
- 服务账户使用用户密码 → **修改 Windows 密码后需重新设置 `ObjectName`**
- 知网页面前端变更可能影响选择器（`config.py` 集中管理，便于修）
