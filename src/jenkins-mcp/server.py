"""Jenkins MCP server for Quartz.

A small, dependency-light FastMCP server that exposes a read-mostly set of
Jenkins tools (plus build triggering) over Streamable HTTP so that kagent agents
(specifically the cicd-agent) can inspect and operate the in-cluster Jenkins.

Configuration (environment variables):
  JENKINS_URL    Base URL of the Jenkins controller, e.g.
                 http://jenkins.jenkins.svc.cluster.local:8080
  JENKINS_USER   Username for Basic auth.
  JENKINS_TOKEN  API token (or password) for Basic auth.
  MCP_HOST       Bind host (default 0.0.0.0).
  MCP_PORT       Bind port (default 3000).
  MCP_PATH       HTTP path for the MCP endpoint (default /mcp).

All write operations (currently only triggering a build) obtain a CSRF crumb
first and are clearly named so the calling agent can gate them behind user
confirmation.
"""

import os
from typing import Any
from urllib.parse import quote

import requests
from fastmcp import FastMCP

JENKINS_URL = os.environ.get("JENKINS_URL", "").rstrip("/")
JENKINS_USER = os.environ.get("JENKINS_USER", "")
JENKINS_TOKEN = os.environ.get("JENKINS_TOKEN", "")

# Cap console output so a single tool call cannot flood the model context.
MAX_CONSOLE_CHARS = 20_000
HTTP_TIMEOUT = 30

mcp = FastMCP("jenkins-mcp")


def _auth() -> tuple[str, str]:
    return (JENKINS_USER, JENKINS_TOKEN)


def _require_config() -> str | None:
    if not JENKINS_URL:
        return "JENKINS_URL is not configured."
    if not JENKINS_USER or not JENKINS_TOKEN:
        return "JENKINS_USER / JENKINS_TOKEN are not configured."
    return None


def _job_path(job_full_name: str) -> str:
    """Translate a job full name (possibly nested with '/') into a Jenkins URL
    path. ``folder/sub/job`` -> ``job/folder/job/sub/job/job``."""
    parts = [p for p in job_full_name.strip("/").split("/") if p]
    return "/".join(f"job/{quote(p)}" for p in parts)


def _get_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{JENKINS_URL}/{path.lstrip('/')}"
    resp = requests.get(url, auth=_auth(), params=params, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _crumb() -> dict[str, str]:
    """Fetch a CSRF crumb header if the controller has CSRF protection on."""
    try:
        data = _get_json("crumbIssuer/api/json")
        return {data["crumbRequestField"]: data["crumb"]}
    except Exception:
        return {}


@mcp.tool()
def jenkins_whoami() -> dict[str, Any]:
    """Return the authenticated Jenkins user and controller version. Use this to
    verify connectivity and credentials before doing anything else."""
    if err := _require_config():
        return {"error": err}
    try:
        me = _get_json("me/api/json")
        resp = requests.get(
            f"{JENKINS_URL}/api/json", auth=_auth(), timeout=HTTP_TIMEOUT
        )
        version = resp.headers.get("X-Jenkins", "unknown")
        return {
            "authenticated_as": me.get("fullName") or me.get("id"),
            "jenkins_version": version,
            "url": JENKINS_URL,
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def jenkins_list_jobs(folder: str = "") -> dict[str, Any]:
    """List Jenkins jobs. If ``folder`` is given (a folder full name), list the
    jobs inside that folder; otherwise list top-level jobs."""
    if err := _require_config():
        return {"error": err}
    try:
        base = _job_path(folder) + "/" if folder else ""
        data = _get_json(
            f"{base}api/json",
            params={"tree": "jobs[name,fullName,url,color,_class]"},
        )
        return {"jobs": data.get("jobs", [])}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def jenkins_get_job(job: str) -> dict[str, Any]:
    """Get details for a single job, including its recent builds and the status
    of the last build. ``job`` is the job full name (use '/' for folders)."""
    if err := _require_config():
        return {"error": err}
    try:
        tree = (
            "name,fullName,url,buildable,color,"
            "lastBuild[number,result,building,timestamp,url],"
            "lastSuccessfulBuild[number,url],lastFailedBuild[number,url],"
            "builds[number,result,building,timestamp,url]{0,15}"
        )
        return _get_json(f"{_job_path(job)}/api/json", params={"tree": tree})
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def jenkins_get_build(job: str, build_number: str = "lastBuild") -> dict[str, Any]:
    """Get details for a specific build of a job. ``build_number`` may be a
    number or a symbolic name such as ``lastBuild``, ``lastSuccessfulBuild`` or
    ``lastFailedBuild``."""
    if err := _require_config():
        return {"error": err}
    try:
        tree = (
            "number,result,building,timestamp,duration,url,displayName,"
            "actions[causes[shortDescription]]"
        )
        return _get_json(
            f"{_job_path(job)}/{quote(str(build_number))}/api/json",
            params={"tree": tree},
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def jenkins_get_build_console(
    job: str, build_number: str = "lastBuild"
) -> dict[str, Any]:
    """Return the (tail of the) console log for a build. Output is truncated to
    the last ~20k characters to keep responses manageable."""
    if err := _require_config():
        return {"error": err}
    try:
        url = f"{JENKINS_URL}/{_job_path(job)}/{quote(str(build_number))}/consoleText"
        resp = requests.get(url, auth=_auth(), timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        text = resp.text
        truncated = len(text) > MAX_CONSOLE_CHARS
        return {
            "job": job,
            "build": build_number,
            "truncated": truncated,
            "console": text[-MAX_CONSOLE_CHARS:],
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def jenkins_get_queue() -> dict[str, Any]:
    """List items currently waiting in the Jenkins build queue."""
    if err := _require_config():
        return {"error": err}
    try:
        data = _get_json(
            "queue/api/json",
            params={"tree": "items[id,why,stuck,task[name,url]]"},
        )
        return {"items": data.get("items", [])}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def jenkins_trigger_build(
    job: str, parameters: dict[str, str] | None = None
) -> dict[str, Any]:
    """Trigger a build of a job. WRITE OPERATION — only call this when the user
    has explicitly asked to start a build. If ``parameters`` is provided the
    parameterized build endpoint is used."""
    if err := _require_config():
        return {"error": err}
    try:
        headers = _crumb()
        job_url = f"{JENKINS_URL}/{_job_path(job)}"
        if parameters:
            resp = requests.post(
                f"{job_url}/buildWithParameters",
                auth=_auth(),
                headers=headers,
                data=parameters,
                timeout=HTTP_TIMEOUT,
            )
        else:
            resp = requests.post(
                f"{job_url}/build",
                auth=_auth(),
                headers=headers,
                timeout=HTTP_TIMEOUT,
            )
        resp.raise_for_status()
        return {
            "job": job,
            "triggered": True,
            "queue_url": resp.headers.get("Location"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=os.environ.get("MCP_HOST", "0.0.0.0"),
        port=int(os.environ.get("MCP_PORT", "3000")),
        path=os.environ.get("MCP_PATH", "/mcp"),
    )
