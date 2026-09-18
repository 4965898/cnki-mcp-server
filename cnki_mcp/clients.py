"""一键将本 MCP 配置分发到本机各 AI 客户端软件。

支持的客户端（自动探测，存在才写）：
- WorkBuddy      ~/.workbuddy/mcp.json
- VS Code        ~/.vscode/mcp.json
- Trae CN        %APPDATA%/Trae CN/User/mcp.json
- TRAE SOLO CN   %APPDATA%/TRAE SOLO CN/User/mcp.json
- Trae 国际版    %APPDATA%/Trae/User/mcp.json
- Codex          ~/.codex/config.toml
- Cherry Studio  %APPDATA%/CherryStudio/Data/cherrystudio.sqlite
- NoteGen        %APPDATA%/com.codexu.NoteGen/store.json + local-mcp.json

用法（在本包 venv 中执行）：
    python -m cnki_mcp install-clients            # 写入全部检测到的客户端
    python -m cnki_mcp install-clients --list     # 仅探测，不做修改
    python -m cnki_mcp install-clients --python <python.exe 路径>

所有写入前都会先备份原文件（*.bak-cnki）；SQLite 用 backup API 做一致性快照。
"""

import json
import os
import shutil
import sqlite3
import sys
import time
import uuid

HOME = os.path.expanduser("~")


def _appdata() -> str:
    return os.environ.get("APPDATA", os.path.join(HOME, "AppData", "Roaming"))


def _default_python() -> str:
    """默认用当前解释器（推荐在本包专用 venv 内运行）"""
    return sys.executable


def _cnki_entry(python_exe: str) -> dict:
    return {
        "command": python_exe,
        "args": ["-m", "cnki_mcp"],
        "env": {"NO_PROXY": "cnki.net,*.cnki.net"},
    }


def _stamp() -> str:
    return "bak-cnki-" + time.strftime("%Y%m%d")


# ---------- JSON 类客户端 ----------

def _write_json_mcp_servers(label: str, path: str, entry: dict, results: list, create: bool = False) -> None:
    try:
        if not os.path.exists(path):
            if not create:
                results.append({"client": label, "status": "skip", "detail": "配置文件不存在，跳过"})
                return
            data = {"mcpServers": {}}
        else:
            shutil.copy2(path, path + "." + _stamp())
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
        servers = data.setdefault("mcpServers", {})
        servers["cnki"] = dict(entry, disabled=False)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        results.append({"client": label, "status": "ok", "detail": path})
    except Exception as e:
        results.append({"client": label, "status": "fail", "detail": str(e)[:200]})


def _write_workbuddy(entry: dict, results: list) -> None:
    _write_json_mcp_servers("WorkBuddy", os.path.join(HOME, ".workbuddy", "mcp.json"), entry, results)


def _write_vscode(entry: dict, results: list) -> None:
    _write_json_mcp_servers("VSCode", os.path.join(HOME, ".vscode", "mcp.json"), entry, results)


def _write_trae_family(entry: dict, results: list) -> None:
    appdata = _appdata()
    _write_json_mcp_servers("Trae CN", os.path.join(appdata, "Trae CN", "User", "mcp.json"), entry, results)
    _write_json_mcp_servers("TRAE SOLO CN", os.path.join(appdata, "TRAE SOLO CN", "User", "mcp.json"), entry, results)
    _write_json_mcp_servers("Trae 国际版", os.path.join(appdata, "Trae", "User", "mcp.json"), entry, results, create=True)


def _write_codex(entry: dict, results: list) -> None:
    try:
        path = os.path.join(HOME, ".codex", "config.toml")
        if not os.path.exists(path):
            results.append({"client": "Codex", "status": "skip", "detail": "config.toml 不存在，跳过"})
            return
        shutil.copy2(path, path + "." + _stamp())
        with open(path, encoding="utf-8") as f:
            content = f.read()
        if "[mcp_servers.cnki]" in content:
            results.append({"client": "Codex", "status": "skip", "detail": "cnki 条目已存在"})
            return
        esc = entry["command"].replace("'", "''")
        block = (
            "\n[mcp_servers.cnki]\n"
            f"command = '{esc}'\n"
            "args = ['-m', 'cnki_mcp']\n"
            "startup_timeout_sec = 120\n\n"
            "[mcp_servers.cnki.env]\n"
            "NO_PROXY = 'cnki.net,*.cnki.net'\n"
        )
        with open(path, "a", encoding="utf-8") as f:
            f.write(block)
        results.append({"client": "Codex", "status": "ok", "detail": path})
    except Exception as e:
        results.append({"client": "Codex", "status": "fail", "detail": str(e)[:200]})


# ---------- Cherry Studio（SQLite） ----------

def _write_cherrystudio(entry: dict, results: list) -> None:
    try:
        db = os.path.join(_appdata(), "CherryStudio", "Data", "cherrystudio.sqlite")
        if not os.path.exists(db):
            results.append({"client": "Cherry Studio", "status": "skip", "detail": "数据库不存在，跳过"})
            return
        bak = db + "." + _stamp()
        src = sqlite3.connect(db)
        dst = sqlite3.connect(bak)
        src.backup(dst)
        dst.close()

        now_ms = int(time.time() * 1000)
        con = sqlite3.connect(db, timeout=10)
        con.execute("PRAGMA busy_timeout=8000")
        exists = con.execute("SELECT COUNT(*) FROM mcp_server WHERE name='cnki'").fetchone()[0]
        if exists:
            results.append({"client": "Cherry Studio", "status": "skip", "detail": "cnki 已存在于数据库"})
        else:
            mx = con.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM mcp_server").fetchone()[0]
            con.execute(
                """INSERT INTO mcp_server
                (id, name, type, description, command, args, env, sort_order, is_active,
                 install_source, is_trusted, trusted_at, installed_at, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()), "cnki", "stdio",
                    "CNKI 中国知网论文检索（GB/T 7714-2025 引文/专业检索式/批量详情）",
                    entry["command"],
                    json.dumps(entry["args"]),
                    json.dumps(entry["env"]),
                    mx, 1, "manual", 1, now_ms, now_ms, now_ms, now_ms,
                ),
            )
            con.commit()
            results.append({"client": "Cherry Studio", "status": "ok", "detail": db + "（需重启生效）"})
        con.close()
        src.close()
    except Exception as e:
        results.append({"client": "Cherry Studio", "status": "fail", "detail": str(e)[:200]})


# ---------- NoteGen ----------

def _write_notegen(entry: dict, results: list) -> None:
    try:
        base = os.path.join(_appdata(), "com.codexu.NoteGen")
        store = os.path.join(base, "store.json")
        local = os.path.join(base, "local-mcp.json")
        if not os.path.exists(store):
            results.append({"client": "NoteGen", "status": "skip", "detail": "store.json 不存在，跳过"})
            return
        shutil.copy2(store, store + "." + _stamp())
        with open(store, encoding="utf-8-sig") as f:
            data = json.load(f)
        servers = data.setdefault("mcp.servers", [])

        # 幂等：已存在 cnki 条目时复用其 id 并更新，避免重复安装产生多条
        existing = None
        for s in servers:
            if s.get("name") == "cnki 知网检索" or (
                s.get("type") == "stdio" and s.get("command") == entry["command"]
                and s.get("args") == entry["args"]
            ):
                existing = s
                break
        if existing is not None:
            sid = existing.get("id") or ("mcp-" + str(int(time.time() * 1000)))
            existing.update({
                "args": entry["args"],
                "command": entry["command"],
                "enabled": True,
                "env": entry["env"],
                "id": sid,
                "name": "cnki 知网检索",
                "type": "stdio",
            })
        else:
            sid = "mcp-" + str(int(time.time() * 1000))
            servers.append({
                "args": entry["args"],
                "command": entry["command"],
                "createdAt": int(time.time() * 1000),
                "enabled": True,
                "env": entry["env"],
                "id": sid,
                "name": "cnki 知网检索",
                "type": "stdio",
            })
        selected = data.setdefault("mcp.selectedServerIds", [])
        if sid not in selected:
            selected.append(sid)
        data["mcp.enabled"] = True
        with open(store, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        # local-mcp.json 派生文件双保险
        json.dump(
            {"mcpServers": {"cnki": dict(entry, disabled=False)}},
            open(local, "w", encoding="utf-8"),
            ensure_ascii=False, indent=2,
        )
        results.append({"client": "NoteGen", "status": "ok", "detail": store})
    except Exception as e:
        results.append({"client": "NoteGen", "status": "fail", "detail": str(e)[:200]})


# ---------- 主入口 ----------

def list_clients() -> list[dict]:
    """探测本机各客户端配置文件是否存在（只读）"""
    appdata = _appdata()
    checks = [
        ("WorkBuddy", os.path.join(HOME, ".workbuddy", "mcp.json")),
        ("VSCode", os.path.join(HOME, ".vscode", "mcp.json")),
        ("Trae CN", os.path.join(appdata, "Trae CN", "User", "mcp.json")),
        ("TRAE SOLO CN", os.path.join(appdata, "TRAE SOLO CN", "User", "mcp.json")),
        ("Trae 国际版", os.path.join(appdata, "Trae", "User")),
        ("Codex", os.path.join(HOME, ".codex", "config.toml")),
        ("Cherry Studio", os.path.join(appdata, "CherryStudio", "Data", "cherrystudio.sqlite")),
        ("NoteGen", os.path.join(appdata, "com.codexu.NoteGen", "store.json")),
    ]
    out = []
    for label, p in checks:
        if os.path.isdir(p):
            out.append({"client": label, "installed": True, "config": p, "config_exists": False})
        else:
            out.append({"client": label, "installed": os.path.exists(p), "config": p})
    return out


def install_to_clients(python_exe: str = "") -> list[dict]:
    """将本 MCP 写入全部检测到的客户端（全部先备份）"""
    entry = _cnki_entry(python_exe or _default_python())
    results: list = []
    _write_workbuddy(entry, results)
    _write_vscode(entry, results)
    _write_trae_family(entry, results)
    _write_codex(entry, results)
    _write_cherrystudio(entry, results)
    _write_notegen(entry, results)
    return results


def run_install_clients(args: list[str]) -> int:
    """CLI 入口: python -m cnki_mcp install-clients [--list] [--python <path>]"""
    python_exe = ""
    if "--python" in args:
        i = args.index("--python")
        if i + 1 < len(args):
            python_exe = args[i + 1]
    if "--list" in args:
        print(json.dumps(list_clients(), ensure_ascii=False, indent=2))
        return 0
    print(f"使用解释器: {python_exe or _default_python()}")
    print("开始分发 cnki MCP 配置到本机 AI 客户端...\n")
    results = install_to_clients(python_exe)
    ok = fail = skip = 0
    for r in results:
        mark = {"ok": "[OK]  ", "fail": "[FAIL]", "skip": "[SKIP]"}[r["status"]]
        print(f"{mark} {r['client']:<14} {r['detail']}")
        if r["status"] == "ok":
            ok += 1
        elif r["status"] == "fail":
            fail += 1
        else:
            skip += 1
    print(f"\n完成: {ok} 成功 / {skip} 跳过 / {fail} 失败")
    print("提示: Cherry Studio / NoteGen / Trae 等图形客户端需重启后加载新配置。")
    return 1 if fail else 0
