# INSTALL.md — 安装与首次使用

> 你收到的是「五行能量说明书」skill 的完整包。这份文件告诉你：放哪、装什么、怎么验证装好了、怎么开始用。
> 全程 3 步，约 2 分钟。

---

## 零、从 GitHub 下载后

1. 点仓库右上角绿色 **Code** 按钮 → **Download ZIP**，或到 Releases 页下 `wuxing-energy-report_vX.Y.zip`。
2. 解压。macOS 直接双击即可；命令行请用 `ditto -x -k 包名.zip 目标目录`，**别用 `unzip`**（见文末「常见问题」）。
3. 从 **Download ZIP** 得到的文件夹叫 `wuxing-energy-report-main`，**重命名为 `wuxing-energy-report`**（去掉 `-main` 后缀）。从 Releases 页下的 zip 已经是正确名字，不用改。
4. 继续下面一节。

---

## 一、放到 skills 目录

把整个 `wuxing-energy-report/` 文件夹（不是 zip）放到 WorkBuddy 的 skills 目录，二选一：

| 位置 | 路径 | 适合 |
|---|---|---|
| **用户级（推荐）** | `~/.workbuddy/skills/wuxing-energy-report/` | 所有项目都能用 |
| 项目级 | `<你的项目>/.workbuddy/skills/wuxing-energy-report/` | 只在一个项目里用 |

> 目录名其实随意，WorkBuddy 认的是 SKILL.md 里的 `name` 字段；但为兼容 Codex / Claude Code，**建议就叫 `wuxing-energy-report`**。

放好后，在 WorkBuddy 对话里说「五行能量」「帮我看看八字」等触发词即可唤起（触发词见 SKILL.md 顶部 description）。

---

## 二、依赖：已内置，不用装（v1.4 起）

排盘用的 `lunar-python` 库已经**直接打包在 skill 里**（`scripts/vendor/lunar_python/`，纯 Python，440K）。
**任何 python3 都能直接跑脚本，不需要 pip install、不需要 venv、不挑环境**——WorkBuddy、Codex、Claude Code、裸终端都一样。

> 仅当 `scripts/vendor/` 目录被删掉时才需要手动装依赖：
> `python3 -m pip install -r requirements.txt`（lunar-python==1.4.8）。

自检一下你的环境（可选）：

```bash
python3 scripts/paipan.py --date 2001-07-01 --time 04:55 --place 深圳 --gender 女
```

看到 JSON 输出就是能跑。

---

## 三、在其他 agent 环境安装（Codex / Claude Code 等）

本仓库的目录名与 SKILL.md 的 `name` 已统一为 `wuxing-energy-report`（小写连字符），
Codex / Claude Code **开箱即用，无需改名**。直接放进对应 skills 目录即可：

- Codex：`~/.codex/skills/`
- Claude Code：`~/.claude/skills/`

因为依赖已 vendor，装完即用，没有任何环境要求。

---

## 四、自检（确认装好了）

```bash
cd <skill 目录>   # 例如 cd ~/.workbuddy/skills/wuxing-energy-report
python3 scripts/selfcheck.py
```

四件事一次查完：必备文件齐不齐（含 `references/` 下三个 AI 必读文档）、排盘能不能跑、
渲染模板完不完整、更新源配没配。**四项全 ✓ 就是装好了，任何一项 ✗ 它会直接告诉你缺什么、怎么补。**

只想快速验一下排盘，也可以只跑：

```bash
python3 scripts/paipan.py --date 2001-07-01 --time 04:55 --place 深圳 --gender 女
```

看到一段 JSON（`"八字": "辛巳 甲午 乙丑 戊寅"`）就是能跑。
这组是**编造示例信息**，仅用于自检，不指向任何真人。

> **为什么建议跑自检而不是只跑排盘**：有些解压工具会静默跳过条目（退出码仍是 0），
> 结果是"脚本能跑，但 AI 读不到红线清单"——排盘正常不代表包装全了。

---

## 五、开始用

回到 WorkBuddy 对话，直接说：

```
帮我看看五行。2001年7月1日 凌晨4点55分 广东深圳 女
```

（换成你自己的：阳历日期 / 出生时间 / 出生城市 / 性别，4 样一次给全。）

AI 会走「开场 → 收信息 → 排盘 → 渲染 → 收尾」全流程，产出一份 HTML 报告（白话/专业双版本可切换）。

---

## 常见问题

- **macOS 命令行解压报 `Illegal byte sequence`** → 部分解压工具对压缩包里的条目处理不一致，会静默跳过（退出码还是 0）。改用 `ditto -x -k 包名.zip 目标目录`，或直接在 Finder 里双击解压。不确定有没有解全，跑一次 `python3 scripts/selfcheck.py`。
- **跑脚本报 `ModuleNotFoundError: No module named 'lunar_python'`** → 说明 `scripts/vendor/` 目录丢了，重新解压 zip，或 `python3 -m pip install -r requirements.txt`。
- **出生地查不到经度** → 正常现象，城市表只有 12 座。AI 会问你经度或省市，然后带 `--lon` 重排，不影响使用。
- **想分享报告给别人** → 渲染时加 `--anon`，出生日期/性别/出生地会替换成「已隐去」。
- **想改话术 / 看边界** → 话术在 `references/dialogue.md`，红线在 `references/redlines.md`，完整工作流在 `SKILL.md`。
