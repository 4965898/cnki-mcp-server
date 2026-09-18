"""python -m cnki_mcp 入口

用法:
    python -m cnki_mcp                          # 启动 MCP server（stdio，默认）
    python -m cnki_mcp serve-http               # 以 HTTP 模式启动（默认 127.0.0.1:37777）
    python -m cnki_mcp serve-http --port 8080   # 自定义端口
    python -m cnki_mcp install-clients          # 一键分发配置到本机 AI 客户端
    python -m cnki_mcp install-clients --list
    python -m cnki_mcp quota                    # 查看当日下载配额
"""

import sys

from cnki_mcp.server import main

if len(sys.argv) > 1 and sys.argv[1] == "serve-http":
    host, port = "127.0.0.1", 37777
    args = sys.argv[2:]
    if "--host" in args:
        i = args.index("--host")
        if i + 1 < len(args):
            host = args[i + 1]
    if "--port" in args:
        i = args.index("--port")
        if i + 1 < len(args):
            port = int(args[i + 1])

    from cnki_mcp.server import mcp

    print(f"CNKI MCP 服务（HTTP/streamable）启动于 http://{host}:{port}/mcp")
    print("提示: 保持本窗口运行；客户端填写的 URL 为 http://%s:%d/mcp" % (host, port))
    mcp.run(transport="http", host=host, port=port)
elif len(sys.argv) > 1 and sys.argv[1] == "quota":
    from cnki_mcp.downloader import QuotaManager

    q = QuotaManager()
    print(f"今日已下载: {q.used_today()} / {q.limit} 篇（剩余 {q.remaining()}）")
    print("配额文件: ~/.cnki-mcp/download_quota.json")
elif len(sys.argv) > 1 and sys.argv[1] == "install-clients":
    from cnki_mcp.clients import run_install_clients

    sys.exit(run_install_clients(sys.argv[2:]))
else:
    main()
