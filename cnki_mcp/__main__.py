"""python -m cnki_mcp 入口

用法:
    python -m cnki_mcp                    # 启动 MCP server（stdio）
    python -m cnki_mcp install-clients    # 一键分发配置到本机 AI 客户端
    python -m cnki_mcp install-clients --list
"""

import sys

from cnki_mcp.server import main

if len(sys.argv) > 1 and sys.argv[1] == "install-clients":
    from cnki_mcp.clients import run_install_clients
    sys.exit(run_install_clients(sys.argv[2:]))
else:
    main()
