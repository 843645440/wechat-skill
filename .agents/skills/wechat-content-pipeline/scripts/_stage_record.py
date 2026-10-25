#!/usr/bin/env python3
"""阶段记账的共享小工具：让「跑一条命令」和「把结果写回 job.json」合成一步。

背景：illustrations / cover 这两个阶段的门禁要求 `pending → running →
completed|skipped` 三段式，漏掉 running 会被 pipeline_job.py 直接拒绝。原来这
一步靠 agent 自己看提示补命令，弱模型很容易只跑生成、忘了记账，或者忘了先标
running——这属于「本可以由脚本消除的判断」，所以下沉到这里。

设计约束：
- 只调用 pipeline_job.py 这个既有入口，不自己写 job.json，避免两处写同一份状态。
- 记账失败绝不影响主流程的退出码：生图成功但记账失败时，主命令仍返回它的
  JSON，只是在结果里多一个 record 字段说明记账没成功，让上层能看见。
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_JOB = SCRIPT_DIR / "pipeline_job.py"


def _run_stage(job_path, name, status, detail=None):
    cmd = [
        sys.executable, str(PIPELINE_JOB), "stage",
        "--job", str(job_path), "--name", name, "--status", status,
    ]
    if detail:
        cmd.extend(("--detail", detail))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (subprocess.SubprocessError, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout).strip()[:200]
    return True, ""


def mark_running(job_path, name):
    """生成开始前标 running。返回 (ok, error)。"""
    if not job_path:
        return False, "未提供 --job，跳过记账"
    return _run_stage(job_path, name, "running")


def mark_result(job_path, name, result):
    """按脚本自己的结果 JSON 记账 completed / skipped。

    detail 从 result 里推导，agent 不需要再拼一遍字符串——这正是原来最容易
    抄错的地方（backend 写错、reason 漏掉）。
    """
    if not job_path:
        return False, "未提供 --job，跳过记账"
    status = result.get("status")
    if status == "completed":
        detail = f"backend={result.get('backend', 'unknown')}"
        provider = result.get("provider")
        if provider:
            detail += f";provider={str(provider).replace(';', ',')[:80]}"
        inserted = result.get("inserted")
        if inserted is not None:
            detail += f";count={inserted}"
    elif status in ("skipped", "failed"):
        reason = str(result.get("reason", "")).replace(";", ",")[:120]
        detail = f"reason={reason or 'unknown'}"
    else:
        return False, f"未知 status：{status!r}"
    return _run_stage(job_path, name, status, detail)


def record_around(job_path, stage_name, produce):
    """把 running → 执行 → completed/skipped 三步包成一次调用。

    produce() 返回脚本自己的结果 dict；本函数原样返回它，并附加 record 字段：
    记账成功时 record="ok"，失败时 record="failed: <原因>"（主结果不受影响）。
    """
    if not job_path:
        return produce()
    running_ok, running_err = mark_running(job_path, stage_name)
    result = produce()
    if not running_ok:
        result["record"] = f"failed: 标记 running 失败：{running_err}"
        return result
    ok, err = mark_result(job_path, stage_name, result)
    result["record"] = "ok" if ok else f"failed: {err}"
    return result


def emit(result):
    print(json.dumps(result, ensure_ascii=False))
