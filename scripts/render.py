#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
五行能量说明书 · 渲染脚本（锁死骨架版）

职责：paipan.py 输出的 JSON（盘面数据）+ AI 写的 content.json（纯文案）
      → 生成完整 HTML 报告。

为什么要有它：AI 手写整页 HTML 容易静默失效（骨架、CSS、切换逻辑出错）。
本脚本把「数据层」（四柱 / 五行条 / 大运卡片 / 总结速览）锁死自动生成，
AI 只负责写「解读层」的纯文案（content.json），不碰页面骨架。

用法：
  python3 scripts/paipan.py --date 2001-07-01 --time 04:55 --place 深圳 --gender 女 > paipan.json
  python3 scripts/render.py --paipan paipan.json --content content.json --out 报告.html

  或管道（paipan JSON 从 stdin 读）：
  python3 scripts/paipan.py ... | python3 scripts/render.py --content content.json --out 报告.html

依赖：仅标准库（json / argparse / sys / os），无需额外安装。
"""

import json
import argparse
import sys
import os

# ── 五行 → 颜色 / CSS class（与 templates/report_template.html 对齐）──
WX_HEX = {"金": "#b8912f", "木": "#2f9e74", "水": "#3d84c4", "火": "#cf4a3a", "土": "#a9712f"}
WX_CLASS = {"金": "wx-jin", "木": "wx-mu", "水": "wx-shui", "火": "wx-huo", "土": "wx-tu"}
WX_ORDER = ["金", "木", "水", "火", "土"]
PILLAR_POS = {"年": "年柱", "月": "月柱", "日": "日柱", "时": "时柱"}

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "templates", "report_template.html")


# ── 数据层生成 ─────────────────────────────────────────────

def build_pillars(pillars):
    """四柱 grid：天干 / 地支 / 十神 / 藏干，日柱高亮。"""
    out = []
    for p in pillars:
        cls = "pillar is-day" if p["柱"] == "日" else "pillar"
        hide = "藏 " + "·".join(p["藏干"])
        out.append(
            f'<div class="{cls}">'
            f'<div class="pos">{PILLAR_POS[p["柱"]]}</div>'
            f'<div class="gz"><span class="gan">{p["天干"]}</span>{p["地支"]}</div>'
            f'<div class="ss">{p["天干十神"]}</div>'
            f'<div class="hide">{hide}</div>'
            f'</div>'
        )
    return "\n".join(out)


def build_wxbar(count):
    """五行条（双口径：条长=含藏干，后缀「明面 N」=本气）。"""
    full = count.get("含藏干", {})
    ben = count.get("本气", {})
    mx = max(full.values()) or 1
    rows = []
    for wx in WX_ORDER:
        f = full.get(wx, 0)
        b = ben.get(wx, 0)
        pct = round(f / mx * 100, 1)
        rows.append(
            f'<div class="wxrow">'
            f'<span class="label {WX_CLASS[wx]}">{wx}</span>'
            f'<div class="track"><div class="fill" style="width:{pct}%;background:{WX_HEX[wx]}"></div></div>'
            f'<span class="num">{f}</span>'
            f'<span class="benqi">明面 {b}</span>'
            f'</div>'
        )
    legend = ('<div class="legend">大数＝这股能量的真实总量（包括藏着的）'
              '· 小字＝明面上能看得到的</div>')
    return legend + "\n".join(rows)


def build_dayun(dayun, jiedu_map, cur_gz, now_year, pro=False):
    """大运卡片列表。pro=True 时 wxtag 带十神，并把解读里的「为什么」展开。"""
    out = []
    for d in dayun:
        gz = d["干支"]
        g, z = d["天干"], d["地支"]
        gwx, zwx = d.get("天干五行", ""), d.get("地支五行", "")
        start_year = int(d["年"].split("-")[0])

        cls = "dayun"
        if gz == cur_gz:
            cls += " cur"
        elif start_year < now_year:
            cls += " past"

        if pro:
            wxtag = f'{g}{gwx}（{d.get("天干十神", "")}）· {z}{zwx}'
        else:
            wxtag = f'{gwx} · {zwx}'

        jiedu = jiedu_map.get(gz, "")

        cur_tag = '<span class="tag2">当前</span>' if gz == cur_gz else ""
        out.append(
            f'<div class="{cls}">'
            f'<div class="head">'
            f'<span class="gz"><span class="gan {WX_CLASS.get(gwx, "")}">{g}</span>'
            f'<span class="zhi {WX_CLASS.get(zwx, "")}">{z}</span></span>'
            f'<span class="yr">{d["年"]} · {d["岁"]}岁</span>'
            f'{cur_tag}'
            f'</div>'
            f'<div class="wxtag">{wxtag}</div>'
            f'{jiedu}'
            f'</div>'
        )
    return "\n".join(out)


def build_summary(summary):
    """总结速览板块（「先看这里」，四句）。"""
    ps = []
    for k in ["定性", "身强弱", "喜用忌神", "盘面结构"]:
        v = summary.get(k, "")
        if v:
            ps.append(f"<p>{v}</p>")
    return ('<div class="card">'
            '<h2><span class="no">◈</span>先看这里 <span class="faint">（30 秒看懂这张盘）</span></h2>'
            f'<div class="key">{"".join(ps)}</div>'
            '</div>')


def build_liunian(xq_list, ln_map):
    """流年板块：事实层数据卡（自动生成）+ AI 四节文案（事业/健康/感情/注意事项）。

    ln_map 结构：{"开头": "...", "年": {"2026": {"事业": "...", "健康": "...",
                  "感情": "...", "注意事项": "..."}, "2027": {...}}}
    四节标题由本函数锁死，AI 只写各节正文，防止骨架漂移。
    """
    parts = [ln_map.get("开头", "")]
    year_map = ln_map.get("年", {})
    for xq in xq_list:
        g, z = xq["天干"], xq["地支"]
        tags = [f'{xq["干支"]}年 · {g["字"]}{g["五行"]}（{g["十神"]}）· {z["字"]}{z["五行"]}（{z["本气十神"]}）']
        tags += [f'主题：{"、".join(xq["主题"])}']
        for rel in xq["与命局关系"]:
            tags.append(rel)
        for rel in xq["与当前大运"]:
            tags.append(rel)
        xi_tags = [f'{g["字"]}：{"·".join(g["喜忌"])}' if g["喜忌"] else "",
                   f'{z["字"]}：{"·".join(z["喜忌"])}' if z["喜忌"] else ""]
        tag_html = "".join(f'<span class="lntag">{t}</span>' for t in tags if t)
        xi_html = " ".join(
            f'<span class="lntag xi">{t}</span>' for t in xi_tags if t)
        head = (f'<div class="head"><span class="gz">'
                f'<span class="gan {WX_CLASS.get(g["五行"], "")}">{g["字"]}</span>'
                f'<span class="zhi {WX_CLASS.get(z["五行"], "")}">{z["字"]}</span></span>'
                f'<span class="yr">{xq["年"]} 年</span></div>'
                f'<div class="lntags">{tag_html}{xi_html}</div>')
        body = []
        yy = str(xq["年"])
        sec = year_map.get(yy, {})
        for name in ["事业", "健康", "感情", "注意事项"]:
            txt = sec.get(name, "")
            if txt:
                body.append(f"<h3>{name}</h3>{txt}")
        parts.append(f'<div class="dayun ln">{head}{"".join(body)}</div>')
    return "\n".join(parts)


# ── 主渲染 ────────────────────────────────────────────────

def render(paipan, content, anon=False):
    if anon:
        # 隐私脱敏：HTML 里去掉出生日期/性别/出生地/真太阳时
        # 用深拷贝，不污染上游 paipan 对象
        paipan = json.loads(json.dumps(paipan))
        inp = paipan["输入"]
        inp["date"] = "已隐去"
        inp["gender"] = "已隐去"
        inp["place"] = "已隐去"
        inp["真太阳时"] = "已隐去"

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        html = f.read()

    day_gan = paipan["日主"]["天干"]
    wx = paipan["日主"]["五行"]
    inp = paipan["输入"]

    now_year = __import__("datetime").date.today().year
    cur_gz = paipan.get("当前大运", {}).get("干支", "")

    # 大运解读（白话 / 专业 各自的「大运解读」map）
    jielv = content.get("节律", {})
    plain_dy = (jielv.get("白话", {}) or {}).get("大运解读", {})
    pro_dy = (jielv.get("专业", {}) or {}).get("大运解读", {})

    # 04 节律板块（白话 / 专业整段）
    jielv_plain = (jielv.get("白话", {}).get("开头", "")
                   + build_dayun(paipan["大运"], plain_dy, cur_gz, now_year, pro=False)
                   + jielv.get("白话", {}).get("结尾", ""))
    jielv_pro = (jielv.get("专业", {}).get("开头", "")
                 + build_dayun(paipan["大运"], pro_dy, cur_gz, now_year, pro=True)
                 + jielv.get("专业", {}).get("结尾", ""))

    # 05 流年板块（白话 / 专业整段）
    liunian_c = content.get("流年", {})
    liunian_plain = build_liunian(paipan.get("流年详解", []), liunian_c.get("白话", {}) or {})
    liunian_pro = build_liunian(paipan.get("流年详解", []), liunian_c.get("专业", {}) or {})

    mapping = {
        "WX": wx,
        "八字": paipan["八字"],
        "出生日期": inp["date"],
        "性别": inp["gender"],
        "出生地": inp["place"],
        "真太阳时": inp.get("真太阳时", ""),
        "日主天干": day_gan,
        "日主五行": wx,
        "日主阴阳": paipan["日主"]["阴阳"],
        "四柱": build_pillars(paipan["四柱"]),
        "五行条": build_wxbar(paipan["五行计数"]),
        "总结速览": build_summary(content.get("总结速览", {})),
        "能量地图_白话": content.get("能量地图", {}).get("白话", ""),
        "能量地图_专业": content.get("能量地图", {}).get("专业", ""),
        "身强弱_白话": content.get("身强弱", {}).get("白话", ""),
        "身强弱_专业": content.get("身强弱", {}).get("专业", ""),
        "喜忌_白话": content.get("喜忌", {}).get("白话", ""),
        "喜忌_专业": content.get("喜忌", {}).get("专业", ""),
        "容器_白话": content.get("容器", {}).get("白话", ""),
        "容器_专业": content.get("容器", {}).get("专业", ""),
        "节律_白话": jielv_plain,
        "节律_专业": jielv_pro,
        "流年_白话": liunian_plain,
        "流年_专业": liunian_pro,
        "决策镜_白话": content.get("决策镜", {}).get("白话", ""),
        "决策镜_专业": content.get("决策镜", {}).get("专业", ""),
        "边界": content.get("边界", ""),
    }

    for k, v in mapping.items():
        html = html.replace("{{" + k + "}}", v)

    return html


def main():
    ap = argparse.ArgumentParser(description="五行能量说明书 · 渲染脚本")
    ap.add_argument("--paipan", help="paipan.py 输出的 JSON 文件路径；不传则从 stdin 读")
    ap.add_argument("--content", required=True, help="AI 写的文案 content.json 路径")
    ap.add_argument("--out", required=True, help="输出 HTML 路径")
    ap.add_argument("--anon", action="store_true",
                    help="脱敏输出：隐藏 HTML 中的出生日期/性别/出生地/真太阳时，"
                         "用于把报告分享给他人前的隐私保护")
    args = ap.parse_args()

    if args.paipan:
        with open(args.paipan, encoding="utf-8") as f:
            paipan = json.load(f)
    else:
        paipan = json.load(sys.stdin)

    with open(args.content, encoding="utf-8") as f:
        content = json.load(f)

    html = render(paipan, content, anon=args.anon)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ 已生成：{args.out}")


if __name__ == "__main__":
    main()
