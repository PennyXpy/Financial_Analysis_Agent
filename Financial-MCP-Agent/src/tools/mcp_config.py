"""
MCP服务器配置模块 - 包含连接A股MCP服务器的配置信息
"""

import os

# Paths:
# - This file is at Financial-MCP-Agent/src/tools/mcp_config.py
# - MCP server project is at ../a-share-mcp-is-just-i-need (sibling of Financial-MCP-Agent)
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MCP_SERVER_DIR = os.path.join(ROOT_DIR, "a-share-mcp-is-just-i-need")

SERVER_CONFIGS = {
    "a_share_mcp_v2": {
        "command": "uv",
        "args": [
            "run",
            "--directory",
            MCP_SERVER_DIR,
            "python",
            "mcp_server.py"
        ],
        "transport": "stdio",
    }
}