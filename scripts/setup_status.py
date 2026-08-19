#!/usr/bin/env python3
"""Report what a new user still needs to configure. No secrets in the output."""

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


try:
    from local_env import load_local_env
    load_local_env(str(ROOT / "scripts"))
except Exception:
    pass


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _env_set(name):
    return bool(os.environ.get(name, "").strip())


def main():
    accounts_path = ROOT / "wechat-accounts.json"
    example_path = ROOT / "assets" / "wechat-accounts.example.json"
    profiles_path = ROOT / "config" / "wechat-content-profiles.json"
    local_archive = ROOT / "config" / "local" / "public-event-archive.json"
    archive_path = local_archive if local_archive.is_file() else ROOT / "config" / "public-event-archive.json"

    accounts = _read_json(accounts_path)
    profiles = (_read_json(profiles_path) or {}).get("profiles") or {}
    archive = _read_json(archive_path) or {}

    missing = []
    ready = []
    questions = []

    if not accounts_path.is_file():
        missing.append("wechat-accounts.json（从 assets/wechat-accounts.example.json 复制）")
        questions.append("要用哪个公众号？我先帮你从模板生成 wechat-accounts.json。")
        account_aliases = list(((_read_json(example_path) or {}).get("accounts") or {}).keys())
    else:
        ready.append("wechat-accounts.json 已存在")
        account_aliases = list((accounts.get("accounts") or {}).keys())

    for alias in account_aliases:
        account = ((accounts or {}).get("accounts") or {}).get(alias) or {}
        appid_env = account.get("appid_env") or f"WECHAT_{alias.upper()}_APP_ID"
        secret_env = account.get("secret_env") or f"WECHAT_{alias.upper()}_APP_SECRET"
        if _env_set(appid_env) and _env_set(secret_env):
            ready.append(f"账号 {alias} 的 AppID/AppSecret 环境变量已设置")
        else:
            missing.append(f"账号 {alias} 的 {appid_env} / {secret_env}")
            questions.append(f"账号 {alias} 的 AppID 和 AppSecret 是什么？只放进环境变量，不要写进仓库。")

    if _env_set("AGNES_API_KEY"):
        ready.append("AGNES_API_KEY 已设置（可选生图）")
    else:
        questions.append(
            "要不要开正文配图或 AI 封面？要的话去 https://platform.agnes-ai.cn 领免费 Key，设置 AGNES_API_KEY。"
        )

    if profiles:
        ready.append("内容档案 config/wechat-content-profiles.json 可读")
    else:
        missing.append("config/wechat-content-profiles.json")

    preset = archive.get("preset") or "public-event"
    if archive.get("enabled") and preset == "tech-ai":
        ready.append(
            f"科技/AI 系列已开启，账号 {archive.get('account') or '未指定'}，只写草稿"
        )
        questions.append("科技/AI 系列已开。是否要用你的 Agent 定时任务每天触发？")
    elif archive.get("enabled"):
        ready.append(
            f"本机系列已开启（preset={preset}），账号 {archive.get('account') or '未指定'}，只写草稿"
        )
    else:
        questions.append("要不要开启科技/AI 系列选题？")

    questions.append("你更常用哪一种：把已有文章拿来排版，还是给主题让 AI 写？")

    result = {
        "status": "ok",
        "project_root": str(ROOT),
        "ready": ready,
        "missing": missing,
        "next_questions": questions,
        "defaults": {
            "output": "draft",
            "publish": False,
            "manuscript_humanize": False,
            "brief_humanize": True,
            "inline_images": False,
            "agnes_key_url": "https://platform.agnes-ai.cn",
        },
        "hint": "凭证只进环境变量。流水线只创建草稿，不群发。",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
