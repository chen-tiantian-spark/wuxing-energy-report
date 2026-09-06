#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""五行能量说明书 · 安装自检脚本（纯标准库，任意 python3 可跑，免依赖）

用法：
    python3 scripts/selfcheck.py

检查四件事，任何一项失败都会以非 0 退出码结束，方便 CI 或人工一眼看出问题：
  1. 必备文件是否齐全（尤其是 references/ 下的三个 AI 必读文档）
  2. 排盘脚本能否正常跑通（vendored 依赖是否完整）
  3. 渲染脚本能否正常导入（模板是否完整）
  4. VERSION 是否可读、更新源配置是否还是占位符

为什么需要它：GitHub「Download ZIP」在部分解压方式下会静默丢失非 ASCII
文件名的条目（退出码仍是 0），用户会拿到一个看起来装好了、实际缺文档的
skill。跑一次这个脚本就能把「静默失败」变成显式报错。
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 相对路径 → 说明
REQUIRED = {
    "SKILL.md": "skill 主文件（AI 读它开工）",
    "VERSION": "版本号（自更新靠它比对）",
    "update.json": "更新源配置",
    "scripts/paipan.py": "排盘脚本",
    "scripts/render.py": "渲染脚本",
    "scripts/update.py": "自更新脚本",
    "scripts/vendor/lunar_python": "vendored 依赖（免 pip 的关键）",
    "templates/report_template.html": "HTML 骨架模板",
    "references/redlines.md": "红线清单（动手前必读）",
    "references/dialogue.md": "话术与边界应答",
    "references/wuxing-in-life.md": "喜忌落生活对照表",
}

ok, warn = [], []


def main():
    print(f"检查目录：{ROOT}\n")

    # ── 1. 必备文件 ──────────────────────────────────
    print("【1/4】必备文件")
    missing = []
    for rel, desc in REQUIRED.items():
        p = ROOT / rel
        if p.exists():
            print(f"  ✓ {rel:<34} {desc}")
        else:
            print(f"  ✗ {rel:<34} {desc}  ← 缺失")
            missing.append(rel)
    if missing:
        print("\n  ⚠️  缺了 " + str(len(missing)) + " 项，这个 skill 不能正常用。")
        print("  最常见原因：解压不完整——部分解压工具会静默跳过条目且退出码仍是 0，"
              "看起来成功其实没解全。")
        print("  解决：重新下一次，macOS 用 `ditto -x -k 包名.zip 目标目录`"
              "（别用 unzip），或在 Finder 里双击解压。")
        return 1
    ok.append("必备文件齐全")

    # ── 2. 排盘脚本 ──────────────────────────────────
    print("\n【2/4】排盘脚本（vendored 依赖是否有效）")
    try:
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "paipan.py"),
             "--date", "2001-07-01", "--time", "04:55",
             "--place", "深圳", "--gender", "女"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ 运行异常：{e}")
        return 1
    if r.returncode != 0:
        print(f"  ✗ 退出码 {r.returncode}")
        print((r.stderr or "").strip()[:500])
        return 1
    try:
        d = json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        print("  ✗ 输出不是合法 JSON")
        return 1
    bazi = d.get("八字")
    if bazi != "辛巳 甲午 乙丑 戊寅":
        print(f"  ✗ 八字不符预期：{bazi!r}（应为 '辛巳 甲午 乙丑 戊寅'）")
        return 1
    print(f"  ✓ 排盘正常，示例盘八字 = {bazi}")
    ok.append("排盘脚本可用")

    # ── 3. 渲染脚本 ──────────────────────────────────
    print("\n【3/4】渲染脚本与模板")
    tpl = ROOT / "templates" / "report_template.html"
    try:
        tpl_text = tpl.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ 模板读取失败：{e}")
        return 1
    if "{{" not in tpl_text:
        print("  ✗ 模板里没有任何 {{占位符}}，可能被覆盖成了渲染后的成品 HTML")
        return 1
    print(f"  ✓ 模板完整（含 {tpl_text.count('{{')} 个占位符）")
    ok.append("渲染模板完整")

    # ── 4. 版本与更新源 ──────────────────────────────
    print("\n【4/4】版本与更新源")
    try:
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        print("  ✗ VERSION 读取失败")
        return 1
    print(f"  ✓ 当前版本 v{ver}")
    try:
        cfg = json.loads((ROOT / "update.json").read_text(encoding="utf-8"))
        urls = [s.get("latest_url", "") for s in cfg.get("sources", [])]
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ update.json 解析失败：{e}")
        return 1
    if any(("TODO" in u) or ("<" in u) or (">" in u) for u in urls):
        print("  ⚠️  更新源仍是占位符，自动更新未启用（不影响正常使用）")
        warn.append("更新源未配置")
    else:
        print(f"  ✓ 更新源已配置 {len(urls)} 个")
        ok.append("更新源已配置")

    # ── 汇总 ─────────────────────────────────────────
    print("\n" + "─" * 52)
    print(f"通过 {len(ok)} 项：" + "、".join(ok))
    if warn:
        print("提醒：" + "、".join(warn))
    print("自检通过，可以开始用了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
