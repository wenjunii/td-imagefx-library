"""Check the project-scoped TD Knowledge MCP server and optional Envoy bridge.

Run this script with the Python interpreter from td-knowledge-mcp/.venv.
The bridge owns its MCP 2.x dependencies; the assistant environment does not.
Only read-only knowledge, health and live diagnostic tools are called.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_SERVER = WORKSPACE_ROOT / "td-knowledge-mcp" / "td_knowledge_mcp.py"
DEFAULT_FAISS_DB = WORKSPACE_ROOT / "td-ai-assistant" / "faiss_db"
DEFAULT_CONTEXT = Path(__file__).resolve().parent / "project-context.json"
DEFAULT_ENVOY_CONFIG = (
    Path(__file__).resolve().parent / "local" / ".embody" / "envoy.json"
)
EXPECTED_PROJECT_ID = "td-imagefx-library"
LOCAL_TOOL_NAMES = {
    "query_td_knowledge",
    "search_td_docs",
    "get_knowledge_stats",
    "reload_td_knowledge",
    "get_td_project_context",
    "get_td_server_health",
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
        "--envoy-config",
        type=Path,
        default=DEFAULT_ENVOY_CONFIG,
        help=(
            "Project-local Embody .embody/envoy.json registry; its active "
            "instance port takes precedence over --port"
        ),
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
    if result.is_error:
        message = result.content[0].text if result.content else "Unknown tool error"
        raise RuntimeError(message)
    if result.structured_content is not None:
        if not isinstance(result.structured_content, dict):
            raise RuntimeError("Tool structured content must be a JSON object")
        return result.structured_content
    for block in result.content:
        if getattr(block, "type", None) == "text":
            payload = json.loads(block.text)
            if not isinstance(payload, dict):
                raise RuntimeError("Tool text content must be a JSON object")
            return payload
    raise RuntimeError("Tool result did not include JSON content")


def _validated_error_report(payload, expected_path):
    if payload.get("error"):
        raise RuntimeError(
            "Live ImageFX root {!r} is unavailable: {}".format(
                expected_path,
                payload["error"],
            )
        )
    if payload.get("path") != expected_path:
        raise RuntimeError(
            "Live error report did not confirm {!r}".format(expected_path)
        )
    for key in ("hasErrors", "hasWarnings"):
        if not isinstance(payload.get(key), bool):
            raise RuntimeError(
                "Live error report for {!r} is missing boolean {!r}".format(
                    expected_path,
                    key,
                )
            )
    return payload


def _root_exception(error):
    while isinstance(error, BaseExceptionGroup) and len(error.exceptions) == 1:
        error = error.exceptions[0]
    return error


async def _wait_for_knowledge(session, timeout):
    import anyio

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
    import anyio

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        listed = await session.list_tools()
        names = {tool.name for tool in listed.tools}
        if "get_td_info" in names:
            return names
        await anyio.sleep(0.5)
    health = _payload(await session.call_tool("get_td_server_health", {}))
    envoy = health.get("envoy", {})
    raise TimeoutError(
        "Timed out waiting for Envoy: status={}, registry={}, identity_verified={}. "
        "Open the ImageFX development harness and enable Embody Envoy.".format(
            envoy.get("status"), envoy.get("registry_status"),
            envoy.get("identity_verified"),
        )
    )


async def _check(config):
    import anyio
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters, stdio_client

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
    server_args = [
        "-u",
        str(server),
        "--port",
        str(config.port),
    ]
    if config.envoy_config is not None:
        server_args.extend(
            [
                "--envoy-config",
                str(config.envoy_config.expanduser().resolve()),
            ]
        )
    server_args.extend(
        [
            "--faiss-db",
            str(faiss_db),
            "--project-context",
            str(project_context),
            "--max-concurrent-queries",
            "4",
        ]
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=server_args,
        cwd=str(server.parent),
        env=child_env,
    )

    child_log = sys.stderr if config.verbose else subprocess.DEVNULL
    with anyio.fail_after(config.wait_seconds * 2 + 60):
        async with Client(
            stdio_client(parameters, errlog=child_log), read_timeout_seconds=30,
        ) as session:
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
            missing = LOCAL_TOOL_NAMES - names
            if missing:
                raise RuntimeError("Missing local MCP tools: " + ", ".join(sorted(missing)))
            envoy_online = "get_td_info" in names
            if config.require_envoy and not envoy_online:
                names = await _wait_for_envoy(session, config.wait_seconds)
                envoy_online = "get_td_info" in names

            health = _payload(await session.call_tool("get_td_server_health", {}))

            live = {"status": "online" if envoy_online else "offline"}
            live_clean = True
            if envoy_online:
                library_errors = _validated_error_report(
                    _payload(
                        await session.call_tool(
                            "get_op_errors",
                            {
                                "op_path": "/project1/td_imagefx",
                                "recurse": True,
                            },
                        )
                    ),
                    "/project1/td_imagefx",
                )
                demo_errors = _validated_error_report(
                    _payload(
                        await session.call_tool(
                            "get_op_errors",
                            {
                                "op_path": "/project1/imagefx_demo",
                                "recurse": True,
                            },
                        )
                    ),
                    "/project1/imagefx_demo",
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
                    "name": session.server_info.name,
                    "version": session.server_info.version,
                    "protocol": session.protocol_version,
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
                "health": health,
            }


def main(argv=None):
    config = _arguments(argv)
    try:
        import anyio

        report = anyio.run(_check, config)
    except ImportError:
        report = {
            "ok": False,
            "error": (
                "MCP 2.x runtime is unavailable. Run this checker with "
                "td-knowledge-mcp/.venv/Scripts/python.exe on Windows "
                "(or .venv/bin/python on macOS/Linux), not td-ai-assistant/venv."
            ),
        }
    except Exception as exc:
        exc = _root_exception(exc)
        report = {
            "ok": False,
            "error": "{}: {}".format(type(exc).__name__, exc),
        }
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
