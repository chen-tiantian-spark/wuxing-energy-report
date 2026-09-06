#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
五行能量说明书 · 自更新脚本（纯标准库，任意 python3 可跑，免依赖）

用法：
  python3 scripts/update.py --check          # 只检查，报告是否有新版本（默认动作）
  python3 scripts/update.py --apply --yes    # 执行更新

⚠️ --apply 必须搭配 --yes：调用方（AI）必须先把 changelog 展示给用户、
   征得明确同意后，才准加 --yes。绝不静默替换。

机制：
  1. 读 skill 根目录 update.json 的 sources（latest.json URL 列表，按序尝试；
     URL 含 TODO / <占位符> 的源自动跳过）。
  2. latest.json 形如：
     {"version":"1.6","released_at":"2026-09-05",
      "zip_url":"https://.../wuxing-energy-report_v1.6.zip",
      "sha256":"...","changelog":"..."}
  3. --apply：下载 zip → 校验 sha256 → 解压校验含 SKILL.md →
     当前 skill 目录整体改名备份（同级：五行能量说明书_备份_vX.Y_时间戳）→
     新版就位；中途失败自动回滚。
  4. skill 根目录有 .git（git clone 安装）：改走 git fetch + git pull --ff-only。
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

SKILL_ROOT = pathlib.Path(__file__).resolve().parent.parent
VERSION_FILE = SKILL_ROOT / "VERSION"
CHANNEL_FILE = SKILL_ROOT / "update.json"
TIMEOUT = 15


def local_version():
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip().lstrip("v")
    return "0"


def parse_ver(s):
    parts = []
    for x in str(s).strip().lstrip("v").split("."):
        digits = "".join(ch for ch in x if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def load_sources():
    if not CHANNEL_FILE.exists():
        return []
    try:
        cfg = json.loads(CHANNEL_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for src in cfg.get("sources", []):
        url = src.get("latest_url", "")
        if not url or "TODO" in url or "<" in url:
            continue
        out.append((src.get("name", "source"), url))
    return out


def fetch_latest():
    """成功返回 (latest_dict, 源名)；失败返回 (None, 说明文字)。"""
    sources = load_sources()
    if not sources:
        return None, ("未配置更新源（update.json 里还是占位符地址）。"
                      "请向 skill 作者索取新版 zip 手动覆盖，或等作者发布更新仓库。")
    errs = []
    for name, url in sources:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "wuxing-skill-updater"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8")), name
        except Exception as e:
            errs.append(f"{name}: {e}")
    return None, "所有更新源都连不上（" + "；".join(errs) + "）。可稍后再试。"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_update(apply):
    try:
        subprocess.run(["git", "fetch", "--quiet"], cwd=str(SKILL_ROOT), check=True, timeout=60)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(SKILL_ROOT),
                              capture_output=True, text=True, check=True).stdout.strip()
        up = subprocess.run(["git", "rev-parse", "@{u}"], cwd=str(SKILL_ROOT),
                            capture_output=True, text=True, check=True).stdout.strip()
    except Exception as e:
        print(f"git 仓库状态读取失败（{e}）。可进入 skill 目录手动 git pull。")
        return 1
    if head == up:
        print(f"已是最新（本地 {head[:8]}）。")
        return 0
    print(f"检测到新版本：{head[:8]} → {up[:8]}")
    if not apply:
        print("这是 git 安装。经用户同意后执行 git pull --ff-only（或加 --apply --yes 由我执行）。")
        return 0
    r = subprocess.run(["git", "pull", "--ff-only"], cwd=str(SKILL_ROOT),
                       capture_output=True, text=True)
    print((r.stdout + r.stderr).strip())
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    if args.apply and not args.yes:
        print("拒绝执行：--apply 必须搭配 --yes，且调用方必须先把更新内容展示给用户、征得同意。")
        return 2

    lv = local_version()
    print(f"当前版本: v{lv}")

    if (SKILL_ROOT / ".git").exists():
        return git_update(args.apply)

    latest, info = fetch_latest()
    if latest is None:
        print(info)
        return 1

    rv = str(latest.get("version", "")).strip()
    print(f"最新版本: v{rv}（源: {info}，发布于 {latest.get('released_at', '未知')}）")
    if parse_ver(rv) <= parse_ver(lv):
        print("已是最新，无需更新。")
        return 0

    print("发现新版本！更新内容：")
    print(latest.get("changelog", "（作者未填写更新说明）"))
    if not args.apply:
        print("\n如用户同意更新，执行：python3 scripts/update.py --apply --yes")
        print("（会先备份当前版本，可随时回滚）")
        return 0

    zip_url = latest.get("zip_url", "")
    if not zip_url or "TODO" in zip_url:
        print("latest.json 里的 zip_url 未配置，无法自动下载。请向作者索取新版 zip。")
        return 1

    tmpdir = tempfile.mkdtemp(prefix="wuxing_update_")
    zpath = os.path.join(tmpdir, "new.zip")
    try:
        print("下载中…")
        req = urllib.request.Request(zip_url, headers={"User-Agent": "wuxing-skill-updater"})
        with urllib.request.urlopen(req, timeout=120) as r, open(zpath, "wb") as f:
            shutil.copyfileobj(r, f)
        expect = latest.get("sha256", "")
        if expect:
            actual = sha256_of(zpath)
            if actual.lower() != expect.lower():
                print(f"校验失败：sha256 不符（期望 {expect[:12]}…，实得 {actual[:12]}…）。已中止，未改动任何文件。")
                return 1
        with zipfile.ZipFile(zpath) as z:
            z.extractall(tmpdir)
        candidates = [p for p in pathlib.Path(tmpdir).iterdir() if p.name != "new.zip"]
        newroot = candidates[0] if len(candidates) == 1 and candidates[0].is_dir() else pathlib.Path(tmpdir)
        if not (newroot / "SKILL.md").exists():
            print("下载的包结构不对（找不到 SKILL.md）。已中止，未改动任何文件。")
            return 1
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = SKILL_ROOT.with_name(f"{SKILL_ROOT.name}_备份_v{lv}_{ts}")
        os.rename(str(SKILL_ROOT), str(backup))
        try:
            shutil.move(str(newroot), str(SKILL_ROOT))
        except Exception:
            os.rename(str(backup), str(SKILL_ROOT))  # 回滚
            raise
        print(f"更新完成：v{lv} → v{rv}")
        print(f"旧版本已备份到：{backup}")
        print("提示：重新阅读 SKILL.md 以加载新版工作流；确认无误后可自行删除备份目录。")
        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
