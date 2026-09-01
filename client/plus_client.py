#!/usr/bin/env python3
"""Thin Plus connector: upload audit metadata, execute tasks locally, never upload source."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SESSION_FILE = Path.home() / ".architecture-review-plus" / "session.json"


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def request_json(endpoint, path, payload=None, token=None):
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = "Bearer " + token
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    method = "GET" if payload is None else "POST"
    request = Request(endpoint.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8"))
        except Exception:
            detail = {"error": error.reason}
        raise RuntimeError("Plus 服务请求失败：{}".format(detail.get("error", detail))) from error
    except URLError as error:
        raise RuntimeError("无法连接 Plus 服务：{}".format(error.reason)) from error


def save_session(value, path=SESSION_FILE):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_session(path=SESSION_FILE):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def summary_from_state(state_path):
    """Allow-list audit metadata; paths, source text and diffs never leave the machine."""
    state = read_json(state_path)
    modules = []
    for module in state.get("modules") or []:
        findings = module.get("findings") or []
        modules.append({
            "id": str(module.get("id") or ""),
            "score": module.get("score"),
            "grade": str(module.get("grade") or ""),
            "severities": sorted({str(item.get("sev", "UNKNOWN")) for item in findings}),
            "tags": [str(tag) for tag in (module.get("tags") or [])],
            "codeLines": module.get("loc"),
        })
    modules.sort(key=lambda item: item["id"])
    identity = json.dumps(
        [{"id": item["id"], "score": item["score"], "grade": item["grade"]} for item in modules],
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema": "architecture-review-summary/v1",
        "projectHash": hashlib.sha256(identity).hexdigest(),
        "architectureScore": state.get("meta", {}).get("architectureScore"),
        "modules": modules,
    }


def redeem(endpoint, code, device_id):
    result = request_json(endpoint, "/v1/invites/redeem", {"code": code, "deviceId": device_id})
    save_session(result)
    return result


def run_local_agent(command, root, task, plan_id):
    if not command:
        raise RuntimeError("执行修复需要 --agent-command；云端不会读取源码")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump({"planId": plan_id, "task": task}, handle, ensure_ascii=False, indent=2)
        task_file = handle.name
    env = os.environ.copy()
    env.update({"ARCHITECTURE_REPAIR_TASK_FILE": task_file, "ARCHITECTURE_REPAIR_PROJECT_ROOT": str(Path(root).resolve()), "ARCHITECTURE_REPAIR_PLAN": plan_id})
    try:
        return subprocess.run(command, cwd=root, env=env, shell=True).returncode
    finally:
        try:
            os.unlink(task_file)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description="Architecture Review Plus thin local connector")
    parser.add_argument("--endpoint", required=True, help="Cloudflare Worker URL")
    parser.add_argument("--root", required=True, help="local project root")
    parser.add_argument("--state", help="local .codemap/modules.json")
    parser.add_argument("--invite", help="one-time Plus invite code")
    parser.add_argument("--device-id", default=os.environ.get("PLUS_DEVICE_ID", "local-device"))
    parser.add_argument("--plan", choices=("short-term", "long-term", "perfect"))
    parser.add_argument("--agent-command", help="local Agent command; it edits the project in place")
    parser.add_argument("--status", metavar="JOB_ID", help="show a remote job")
    args = parser.parse_args()
    session = load_session()
    if args.invite:
        session = redeem(args.endpoint, args.invite, args.device_id)
        print("Plus 授权成功，令牌有效期至：{}".format(session.get("expiresAt")))
    if not session or not session.get("token"):
        raise SystemExit("缺少授权，请使用 --invite 兑换邀请码")
    token = session["token"]
    if args.status:
        print(json.dumps(request_json(args.endpoint, "/v1/repair-jobs/" + args.status, token=token), ensure_ascii=False, indent=2))
        return
    if not args.state or not args.plan:
        raise SystemExit("启动修复需要同时提供 --state 和 --plan")
    summary = summary_from_state(args.state)
    audit = request_json(args.endpoint, "/v1/audit-summaries", summary, token)
    job = request_json(args.endpoint, "/v1/repair-jobs", {"auditId": audit["auditId"], "planId": args.plan}, token)
    print("Plus 任务已创建：{}（模块摘要已上传，源码未上传）".format(job["jobId"]))
    for task in job.get("tasks", []):
        base = "/v1/repair-jobs/{}/events".format(job["jobId"])
        request_json(args.endpoint, base, {"taskId": task["id"], "status": "repairing", "detail": "本机 Agent 开始处理"}, token)
        code = run_local_agent(args.agent_command, args.root, task, args.plan)
        status = "completed" if code == 0 else "failed"
        request_json(args.endpoint, base, {"taskId": task["id"], "status": status, "detail": "本机 Agent 退出码 {}".format(code)}, token)
        if code != 0:
            raise SystemExit("模块 {} 修复失败，任务已停止".format(task["moduleId"]))
        print("已完成模块：{}".format(task["moduleId"]))
    print("Plus 任务完成：{}".format(job["jobId"]))


if __name__ == "__main__":
    main()
