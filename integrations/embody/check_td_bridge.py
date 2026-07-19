"""Check the project-scoped TD Knowledge MCP server and optional Envoy bridge.

Run this script with the Python interpreter from the td-ai-assistant virtual
environment so the official ``mcp`` client package is available.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import anyio
import mcp.types as types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_SERVER = WORKSPACE_ROOT / "td-knowledge-mcp" / "td_knowledge_mcp.py"
DEFAULT_FAISS_DB = WORKSPACE_ROOT / "td-ai-assistant" / "faiss_db"
DEFAULT_CONTEXT = Path(__file__).resolve().parent / "project-context.json"
EXPECTED_PROJECT_ID = "td-imagefx-library"
LOCAL_TOOL_NAMES = {
    "query_td_knowledge",
    "search_td_docs",
    "get_knowledge_stats",
    "reload_td_knowledge",
    "get_td_project_context",
}


def _positive_timeout(value):
    timeout = float(value)
    if not 1 <= timeout <= 300:
        raise argparse.ArgumentTypeError(
            "timeout must be between 1 and 300 seconds"
        )
    return timeout


def _port(value):
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _arguments(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate the ImageFX TD knowledge profile and optional live "
            "TouchDesigner Envoy bridge"
        )
    )
    parser.add_argument(
        "--server",
        type=Path,
        default=DEFAULT_SERVER,
        help="Path to td_knowledge_mcp.py",
    )
    parser.add_argument(
        "--faiss-db",
        type=Path,
        default=DEFAULT_FAISS_DB,
        help="Path to the td-ai-assistant FAISS database",
    )
    parser.add_argument(
        "--project-context",
        type=Path,
        default=DEFAULT_CONTEXT,
        help="Path to the ImageFX project-context JSON file",
    )
    parser.add_argument(
        "--port",
        type=_port,
        default=9870,
        help="Envoy Streamable HTTP port",
    )
    parser.add_argument(
        "--wait-seconds",
        type=_positive_timeout,
        default=60.0,
        help="Maximum wait for knowledge and Envoy startup",
    )
    parser.add_argument(
        "--require-envoy",
        action="store_true",
        help="Fail unless TouchDesigner Envoy is online and the live roots are clean",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show diagnostic output from the child TD Knowledge MCP server",
    )
    return parser.parse_args(argv)


def _payload(result):
    if result.isError:
        message = result.content[0].text if result.content else "Unknown tool error"
        raise RuntimeError(message)
    if result.structuredContent is not None:
        return result.structuredContent
    for block in result.content:
        if isinstance(block, types.TextContent):
            return json.loads(block.text)
    raise RuntimeError("Tool result did not include JSON content")


async def _wait_for_knowledge(session, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        stats = _payload(await session.call_tool("get_knowledge_stats", {}))
        status = stats.get("status")
        if status == "online":
            return stats
        if status == "offline":
            raise RuntimeError(stats.get("error") or "Knowledge index is offline")
        await anyio.sleep(0.25)
    raise TimeoutError("Timed out waiting for the knowledge index")


async def _wait_for_envoy(session, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        listed = await session.list_tools()
        names = {tool.name for tool in listed.tools}
        if "get_td_info" in names:
            return names
        await anyio.sleep(0.5)
    raise TimeoutError("Timed out waiting for Envoy")


async def _check(config):
    server = config.server.expanduser().resolve()
    faiss_db = config.faiss_db.expanduser().resolve()
    project_context = config.project_context.expanduser().resolve()
    for label, path in (
        ("TD Knowledge MCP server", server),
        ("FAISS database", faiss_db),
        ("project context", project_context),
    ):
        if not path.exists():
            raise FileNotFoundError("{} is missing: {}".format(label, path))

    child_env = os.environ.copy()
    child_env["PYTHONUTF8"] = "1"
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-u",
            str(server),
            "--port",
            str(config.port),
            "--faiss-db",
            str(faiss_db),
            "--project-context",
            str(project_context),
            "--max-concurrent-queries",
            "4",
        ],
        cwd=str(server.parent),
        env=child_env,
    )

    child_log = sys.stderr if config.verbose else subprocess.DEVNULL
    async with stdio_client(parameters, errlog=child_log) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            await session.send_ping()
            context = _payload(
                await session.call_tool(
                    "get_td_project_context",
                    {"section": "overview"},
                )
            )
            project_id = context.get("project_id")
            if project_id != EXPECTED_PROJECT_ID:
                raise RuntimeError(
                    "Expected project_id {!r}, received {!r}".format(
                        EXPECTED_PROJECT_ID,
                        project_id,
                    )
                )
            stats = await _wait_for_knowledge(session, config.wait_seconds)
            query = _payload(
                await session.call_tool(
                    "query_td_knowledge",
                    {
                        "query": (
                            "TouchDesigner operator errors warnings TOP capture "
                            "and project performance validation"
                        ),
                        "k": 3,
                        "strategy": "hybrid",
                    },
                )
            )
            listed = await session.list_tools()
            names = {tool.name for tool in listed.tools}
            envoy_online = "get_td_info" in names
            if config.require_envoy and not envoy_online:
                names = await _wait_for_envoy(session, config.wait_seconds)
                envoy_online = "get_td_info" in names

            live = {"status": "online" if envoy_online else "offline"}
            live_clean = True
            if envoy_online:
                library_errors = _payload(
                    await session.call_tool(
                        "get_op_errors",
                        {
                            "op_path": "/project1/td_imagefx",
                            "recurse": True,
                        },
                    )
                )
                demo_errors = _payload(
                    await session.call_tool(
                        "get_op_errors",
                        {
                            "op_path": "/project1/imagefx_demo",
                            "recurse": True,
                        },
                    )
                )
                live_clean = not any(
                    (
                        library_errors.get("hasErrors"),
                        library_errors.get("hasWarnings"),
                        demo_errors.get("hasErrors"),
                        demo_errors.get("hasWarnings"),
                    )
                )
                live.update(
                    {
                        "clean": live_clean,
                        "touchdesigner": _payload(
                            await session.call_tool("get_td_info", {})
                        ),
                        "library_errors": library_errors,
                        "demo_errors": demo_errors,
                        "performance": _payload(
                            await session.call_tool(
                                "get_project_performance",
                                {"include_hotspots": 0},
                            )
                        ),
                    }
                )

            return {
                "ok": (
                    project_id == EXPECTED_PROJECT_ID
                    and stats.get("status") == "online"
                    and len(query.get("results", [])) == 3
                    and (envoy_online or not config.require_envoy)
                    and live_clean
                ),
                "server": {
                    "name": initialized.serverInfo.name,
                    "version": initialized.serverInfo.version,
                    "local_tools": len(LOCAL_TOOL_NAMES.intersection(names)),
                    "total_tools": len(names),
                },
                "project": {
                    "status": context.get("status"),
                    "project_id": project_id,
                },
                "knowledge": {
                    "status": stats.get("status"),
                    "chunks": stats.get("total_chunks"),
                    "source_categories": stats.get("source_categories"),
                    "query_results": len(query.get("results", [])),
                },
                "envoy": live,
            }


def main(argv=None):
    config = _arguments(argv)
    try:
        report = anyio.run(_check, config)
    except Exception as exc:
        report = {
            "ok": False,
            "error": "{}: {}".format(type(exc).__name__, exc),
        }
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
