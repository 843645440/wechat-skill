#!/usr/bin/env python3
"""本地凭证自动加载：本机跑脚本时不必每次 export。

查找顺序（从调用者所在目录逐级向上，命中第一个即停）：

1. `$WECHAT_SKILL_ENV_FILE` 指定的文件（绝对路径优先）
2. `<某级目录>/secrets/wechat.env`
3. `<某级目录>/.env.local`

规则：

- **不覆盖**已经存在于进程环境里的变量，临时换号只需 export 一次。
- 不打印任何变量值；文件权限过宽时只在 stderr 提示一次。
- 解析失败不抛异常，让调用方回到「缺少凭证」的既有错误路径。
"""

import os
import stat
import sys
from pathlib import Path


ENV_FILE_VAR = "WECHAT_SKILL_ENV_FILE"
CANDIDATE_NAMES = (("secrets", "wechat.env"), (".env.local",))
_LOADED = set()


def _parse(text):
    pairs = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        pairs.append((key, value))
    return pairs


def candidate_files(start):
    explicit = os.environ.get(ENV_FILE_VAR, "").strip()
    if explicit:
        yield Path(explicit).expanduser()
    base = Path(start or Path.cwd()).resolve()
    for directory in (base, *base.parents):
        for name in CANDIDATE_NAMES:
            yield directory.joinpath(*name)


def find_env_file(start=None):
    for path in candidate_files(start):
        if path.is_file():
            return path
    return None


def warn_if_world_readable(path):
    try:
        mode = path.stat().st_mode
    except OSError:
        return
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        print(
            f"[local_env] 警告：{path} 对同组/其他用户可读，建议 chmod 600",
            file=sys.stderr,
        )


def load_local_env(start=None):
    """填充缺失的环境变量，返回本次实际填充的变量名列表（不含值）。"""
    path = find_env_file(start)
    if path is None:
        return []
    resolved = str(path.resolve())
    if resolved in _LOADED:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    _LOADED.add(resolved)
    warn_if_world_readable(path)
    filled = []
    for key, value in _parse(text):
        if os.environ.get(key):
            continue
        os.environ[key] = value
        filled.append(key)
    return filled


def main(argv=None):
    """`python3 scripts/local_env.py` 只报告加载结果，永不打印值。"""
    argv = list(sys.argv[1:] if argv is None else argv)
    start = argv[0] if argv else None
    path = find_env_file(start)
    if path is None:
        print("未找到本地凭证文件（secrets/wechat.env 或 .env.local）")
        return 1
    filled = load_local_env(start)
    print(f"凭证文件：{path}")
    print(f"本次填充 {len(filled)} 个变量：{'、'.join(filled) if filled else '（都已在环境中）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
