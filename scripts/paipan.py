#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
五行能量说明书 · 排盘脚本（判断下沉版）
依赖：lunar-python 已 vendor 进 scripts/vendor/（v1.4 起），任何 python3 直接可跑。
职责：输入出生信息 → 输出结构化盘面数据 + 身强弱/喜用的「初判」。
      AI 只负责把这里的判断「翻译成人话」，不在判断层面自由发挥。

用法（任意 python3，vendor 内置免装依赖）：
  python3 paipan.py --date 2000-01-01 --time 08:30 --place 北京 --gender 女
  python3 paipan.py --date 2000-01-01 --time 08:30 --place 喀什 --lon 75.99 --gender 女

依赖（仅 vendor 目录缺失时才需要）：
  pip install -r requirements.txt   # lunar-python==1.4.8

排盘口径（重要）：
  - 时柱默认按「钟表时间」排，不做无条件真太阳时校正。
  - 真太阳时只作为「参考信息」输出；仅当钟表时间落在时辰边界
    （整点 ±15 分钟）时，才输出「分叉提示」让用户确认走哪个时辰。

经度口径（2026-09-03 修正）：
  - 优先级：--lon > 城市表（仅 12 座）> 东经 120° 近似。
  - 城市未命中时输出「城市已匹配」= False，并写入「需确认事项」。
  - 钟表时间与真太阳时不在同一时辰时，写入「需确认事项」（不设分钟阈值）。

夏令时口径（2026-09-03 新增）：
  - 中国 1986-1991 曾实行夏令时，出生日期落在区间内会写入「需确认事项」。
  - 脚本不自动减 1 小时——钟表时间是否已换算，必须由用户确认。

「需确认事项」非空时，SKILL 层必须先向用户确认，再出报告。
"""

import json
import argparse
import datetime
import os
import sys

# ── 依赖引导（2026-09-05，v1.4）────────────────────────────
# lunar-python 已 vendor 进 scripts/vendor/lunar_python（纯 Python，440K），
# 任何 python3 直接可跑，无需 pip install。若 vendor 目录缺失，
# 再回落到环境里已安装的 lunar-python（pip install lunar-python==1.4.8）。
_VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

from lunar_python import Solar

# ── 五行映射 ─────────────────────────────
WX_GAN = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
          "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
WX_ZHI = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
          "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
YIN_GAN = set("乙丁己辛癸")
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}  # 生
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}      # 克
DRY_SOIL = {"未", "戌"}   # 燥土（生金力弱）
WET_SOIL = {"辰", "丑"}   # 湿土（生金力强）

# ── 流年详解用的关系表（事实层，不含吉凶判断）─────────────
ZHI_BENQI = {"子": "癸", "丑": "己", "寅": "甲", "卯": "乙", "辰": "戊", "巳": "丙",
             "午": "丁", "未": "己", "申": "庚", "酉": "辛", "戌": "戊", "亥": "壬"}
GAN_WUHE = {"甲": "己", "己": "甲", "乙": "庚", "庚": "乙", "丙": "辛", "辛": "丙",
            "丁": "壬", "壬": "丁", "戊": "癸", "癸": "戊"}
ZHI_LIUHE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯",
             "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}
ZHI_LIUCHONG = {"子": "午", "午": "子", "丑": "未", "未": "丑", "寅": "申", "申": "寅",
                "卯": "酉", "酉": "卯", "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳"}
# 相刑：子卯互刑、寅巳申三刑、丑戌未三刑、辰午酉亥自刑
XING_PAIRS = {frozenset(p) for p in [("子", "卯"), ("寅", "巳"), ("巳", "申"), ("寅", "申"),
                                     ("丑", "戌"), ("戌", "未"), ("丑", "未")]}
SELF_XING = {"辰", "午", "酉", "亥"}

# 十神 → 主题（事实性语义，不是吉凶判断；伴侣星按性别区分）
SHISHEN_THEME = {
    "正官": "责任、规则、事业推力", "七杀": "压力、挑战、事业推力",
    "正财": "资源、机会、财务动作", "偏财": "资源、机会、财务动作",
    "正印": "学习、休整、被支持", "偏印": "学习、休整、被支持",
    "食神": "表达、输出、创造", "伤官": "表达、输出、创造",
    "比肩": "同辈、合作、竞争", "劫财": "同辈、合作、竞争",
}
GUAN_SHA = {"正官", "七杀"}   # 女命伴侣星
CAI = {"正财", "偏财"}        # 男命伴侣星


def shishen(day_gan, target_gan):
    if target_gan == day_gan:
        return "比肩"
    dw, tw = WX_GAN[day_gan], WX_GAN[target_gan]
    same = (day_gan in YIN_GAN) == (target_gan in YIN_GAN)
    if dw == tw:
        return "比肩" if same else "劫财"
    if SHENG[dw] == tw:
        return "食神" if same else "伤官"
    if SHENG[tw] == dw:
        return "偏印" if same else "正印"
    if KE[dw] == tw:
        return "偏财" if same else "正财"
    if KE[tw] == dw:
        return "七杀" if same else "正官"
    return "比肩"


# ⚠️ 城市表很短。未命中时按东经 120° 近似，并在 JSON 输出「城市已匹配」= False
# ——SKILL 层看到 False 必须先向用户确认经度，不许静默排盘。
CITY_LNG = {
    "深圳": 114.06, "梅州": 116.12, "广州": 113.26, "惠州": 114.42,
    "北京": 116.41, "上海": 121.47, "成都": 104.07, "重庆": 106.55,
    "武汉": 114.30, "杭州": 120.15, "汕头": 116.68, "东莞": 113.75,
}
DEFAULT_LNG = 120.0  # 城市未命中时的近似基准（东经 120°，即北京时间标准经度）


def resolve_lng(place, lon=None):
    """解析出生地经度，返回 (经度, 是否命中城市表)。

    优先级：--lon 显式传入 > 城市表 > 东经 120° 近似（并标记未命中）。
    """
    if lon is not None:
        return float(lon), True
    if place in CITY_LNG:
        return CITY_LNG[place], True
    return DEFAULT_LNG, False


def true_solar_time(hh, mm, lng):
    delta = round((lng - 120.0) * 4, 1)
    total = (hh * 60 + mm + delta) % (24 * 60)
    return int(total // 60), int(total % 60), lng, delta


# 中国夏令时区间（1986-1991 曾实行，此后未再实行），闭区间
DST_RANGES = {
    1986: ("05-04", "09-14"), 1987: ("04-12", "09-13"),
    1988: ("04-10", "09-11"), 1989: ("04-16", "09-17"),
    1990: ("04-15", "09-16"), 1991: ("04-14", "09-15"),
}


def hour_branch(hh, mm):
    """返回 hh:mm 所属的时辰名（子时跨日：23:00–00:59）。"""
    total = hh * 60 + mm
    if total >= 23 * 60 or total < 1 * 60:
        return "子"
    name = "子"
    for s, n in [(1, "丑"), (3, "寅"), (5, "卯"), (7, "辰"), (9, "巳"), (11, "午"),
                 (13, "未"), (15, "申"), (17, "酉"), (19, "戌"), (21, "亥")]:
        if total >= s * 60:
            name = n
    return name


def check_dst(y, mo, d):
    """检测出生日期是否落在中国夏令时期间。返回提示 dict 或 None。

    ⚠️ 不自动加减小 1 小时——出生记录上的钟表时间是否已经换算，
    只有用户/出生记录知道，这一步必须交给确认，不能替用户决定。
    """
    r = DST_RANGES.get(y)
    if not r:
        return None
    cur = f"{mo:02d}-{d:02d}"
    if r[0] <= cur <= r[1]:
        return {
            "类型": "夏令时",
            "说明": f"{y} 年 {r[0]} 至 {r[1]} 中国实行夏令时，钟表时间拨快 1 小时。",
            "提示": ("请向用户确认：出生记录上的时间是「当时的钟表时间（夏令时）」"
                     "还是「已换算回标准时间」。若是前者，排盘需用的时间应减去 1 小时，"
                     "且减后若跨时辰需重新确认走哪个时辰。"),
        }
    return None


def hour_branch_boundary(hh, mm, true_hh, true_mm):
    """用【钟表时间】检测是否落在时辰边界（整点 ±15 分钟）。

    返回分叉提示列表（含真太阳时参考），供 SKILL 层询问用户走哪个时辰。
    ⚠️ 必须基于钟表时间检测，不能基于真太阳时校正后的时间——
    否则整点出生（如 03:00）会被静默推进相邻时辰而不提示。
    """
    total = hh * 60 + mm
    starts = [23 * 60, 1 * 60, 3 * 60, 5 * 60, 7 * 60, 9 * 60,
              11 * 60, 13 * 60, 15 * 60, 17 * 60, 19 * 60, 21 * 60]
    names = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
    warn = []
    for i, s in enumerate(starts):
        if abs(total - s) <= 15:
            warn.append({
                "边界": names[i],
                "钟表时间": f"{hh:02d}:{mm:02d}",
                "真太阳时": f"{true_hh:02d}:{true_mm:02d}",
                "提示": (f"钟表时间落在{names[i]}时起点 ±15 分钟内，"
                         f"真太阳时可能落入相邻时辰，请向用户确认走哪个时辰"),
            })
    return warn


def count_wuxing(ec, pillars):
    """五行计数，返回两个口径：
    - 本气：4 天干 + 4 地支本气（8 字，主框架）
    - 含藏干：4 天干 + 4 地支全部藏干（本气/中气/余气，能量全貌）
    展示层以「含藏干」为主口径（与身强弱判断一致，避免低估），本气作参考。"""
    ben = {"金": 0, "木": 0, "水": 0, "火": 0, "土": 0}
    full = {"金": 0, "木": 0, "水": 0, "火": 0, "土": 0}
    # 天干：两个口径都算
    for g in [ec.getYearGan(), ec.getMonthGan(), ec.getDayGan(), ec.getTimeGan()]:
        ben[WX_GAN[g]] += 1
        full[WX_GAN[g]] += 1
    # 地支：本气口径只算本气五行；含藏干口径算全部藏干
    for p in pillars:
        zhi = p["地支"]
        ben[WX_ZHI[zhi]] += 1
        for g in p["藏干"]:
            full[WX_GAN[g]] += 1
    return {"本气": ben, "含藏干": full}


def judge_strength(day_gan, month_zhi, pillars):
    """身强弱初判：力量加权（帮身 vs 克泄耗）+ 根气 + 燥湿土"""
    dw = WX_GAN[day_gan]
    yin_help = 0.0
    drain = 0.0

    def add(gan, from_zhi=None):
        nonlocal yin_help, drain
        ss = shishen(day_gan, gan)
        if ss in ("比肩", "劫财"):
            yin_help += 2.0
        elif ss in ("正印", "偏印"):
            # 金日主 + 燥土 → 生金力弱
            if dw == "金" and WX_GAN[gan] == "土" and from_zhi in DRY_SOIL:
                yin_help += 0.5
            elif dw == "金" and WX_GAN[gan] == "土" and from_zhi in WET_SOIL:
                yin_help += 1.5
            else:
                yin_help += 1.2
        elif ss in ("正官", "七杀"):
            drain += 2.0
        elif ss in ("正财", "偏财"):
            drain += 1.5
        elif ss in ("食神", "伤官"):
            drain += 1.0

    # 天干（除日主）
    for p in pillars:
        if p["柱"] != "日":
            add(p["天干"])
    # 地支藏干（带地支信息，判断燥湿）
    root = 0
    for p in pillars:
        for g in p["藏干"]:
            add(g, from_zhi=p["地支"])
            if WX_GAN.get(g) == dw:
                root += 1

    mw = WX_ZHI[month_zhi]
    month_helps = (mw == dw) or (SHENG.get(mw) == dw)
    score = round(yin_help - drain + (2.0 if month_helps else -2.0), 1)

    if score >= 2:
        level = "身强"
    elif score <= -2:
        level = "身弱"
    else:
        level = "中和"

    # 「扶不扶得动」提示
    cong_weak = False  # 接近从弱：不宜扶抑硬补，宜顺势（2026-09-05 v1.4 修 Codex 反馈第 5 条）
    if level == "身弱":
        if root == 0 and yin_help <= 1.0:
            cong_weak = True
            fuyi = "身弱且无根、印比极弱 → 接近「从弱/顺势」，不宜硬补，宜顺势泄耗"
        elif root == 0:
            fuyi = "身弱且无根、印比偏弱（帮身吃力）→ 扶抑与调候需并重"
        else:
            fuyi = "身弱但有根/印比 → 可扶抑补身（喜印比）"
    elif level == "身强":
        fuyi = "身强 → 喜克泄耗（官杀/食伤/财），忌生扶"
    else:
        fuyi = "中和 → 需看根气与透干细判"

    return {"level": level, "score": score, "yin_help": round(yin_help, 1),
            "drain": round(drain, 1), "root": root, "month_helps": month_helps,
            "cong_weak": cong_weak,
            "fuyi_hint": fuyi}


def guess_xiyong(level, day_gan, month_zhi, cong_weak=False, dominant_wx=None):
    dw = WX_GAN[day_gan]
    mw = WX_ZHI[month_zhi]
    all_wx = ["木", "火", "土", "金", "水"]
    sheng_me = {wx for wx, k in SHENG.items() if k == dw}  # 生我 = 印
    cong_note = ""
    if cong_weak and dominant_wx:
        # 接近从弱（2026-09-05 v1.4）：不扶不补，顺命局最旺之势取用——
        # 喜「旺神 + 旺神所生（顺势泄）」，忌「日主五行 + 印星（帮扶逆局）」。
        # 修复 Codex 反馈第 5 条：旧版一边提示「接近从弱宜顺势」、
        # 一边仍机械输出「补日主与印星」，前后冲突。
        # 注意：旺神所生若恰是印星/比劫（如从金而金生水、水为木日主之印），
        # 该五行归忌不归喜——从格忌印比优先，避免同一五行既喜既忌。
        fuyi_ji = [dw] + [wx for wx in all_wx if wx in sheng_me]
        fuyi_xi = [dominant_wx]
        if SHENG[dominant_wx] not in fuyi_ji:
            fuyi_xi.append(SHENG[dominant_wx])
        cong_note = f"（接近从弱口径：喜用按顺势取——从「{dominant_wx}」之旺，不再补日主与印星）"
    elif level == "身弱":
        fuyi_xi = [dw] + [wx for wx in all_wx if wx in sheng_me]
        fuyi_ji = [wx for wx in all_wx if wx not in fuyi_xi]
    elif level == "身强":
        fuyi_ji = [dw] + [wx for wx in all_wx if wx in sheng_me]
        fuyi_xi = [wx for wx in all_wx if wx not in fuyi_ji]
    else:
        fuyi_xi, fuyi_ji = [], []

    # 调候（用月支季节，非月支五行）
    if month_zhi in ("亥", "子", "丑"):
        tiaohou = "生于寒月（冬），调候喜「火」暖局"
    elif month_zhi in ("巳", "午", "未"):
        tiaohou = "生于燥月（夏），调候喜「水」润局"
    elif month_zhi in ("申", "酉", "戌"):
        tiaohou = "生于燥秋，调候喜「水」润局"
    else:
        tiaohou = "生于春季，调候需求不明显"
    return {"扶抑喜": fuyi_xi, "扶抑忌": fuyi_ji,
            "调候": tiaohou,
            "综合提示": "「扶抑」与「调候」冲突时，调候优先；最终喜用需结合根气与透干" + cong_note}


def tiaohou_wx(month_zhi):
    """调候五行（与 guess_xiyong 同口径）：寒月喜火，燥月/燥秋喜水，春季不明显。"""
    if month_zhi in ("亥", "子", "丑"):
        return "火"
    if month_zhi in ("巳", "午", "未", "申", "酉", "戌"):
        return "水"
    return None


def liunian_detail(yy, day_gan, pillars, cur_yun, xiyong, month_zhi, gender):
    """流年详解（事实层）：干支五行十神、与命局/日主/大运的合冲刑关系、喜忌归属。

    只输出客观关系与主题归类（十神语义），不做吉凶判断——
    「怎么翻译成人话、怎么落到事业/健康/感情/注意」由 SKILL 层的 AI 负责。
    """
    gz = Solar.fromYmd(yy, 6, 1).getLunar().getYearInGanZhi()
    g, z = gz[0], gz[1]
    g_wx, z_wx = WX_GAN[g], WX_ZHI[z]
    g_ss = shishen(day_gan, g)
    z_ss = shishen(day_gan, ZHI_BENQI[z])

    # 主题（事实性十神语义 + 伴侣星按性别标注）
    themes = [SHISHEN_THEME[g_ss]]
    if gender == "女" and g_ss in GUAN_SHA:
        themes.append("女命的伴侣星")
    if gender == "男" and g_ss in CAI:
        themes.append("男命的伴侣星")

    # 流年天干 vs 日主：五合
    relations = []
    if GAN_WUHE[day_gan] == g:
        relations.append(f"流年天干「{g}」与日主「{day_gan}」天干五合（{day_gan}{g}合）")

    # 流年地支 vs 四柱地支：六合 / 六冲 / 相刑（含自刑）
    seen = set()
    for p in pillars:
        bz = p["地支"]
        if bz == z and z in SELF_XING:
            relations.append(f"流年地支「{z}」与{p['柱']}支「{bz}」自刑")
        elif frozenset((z, bz)) in XING_PAIRS and frozenset((z, bz)) not in seen:
            relations.append(f"流年地支「{z}」与{p['柱']}支「{bz}」相刑")
            seen.add(frozenset((z, bz)))
        if ZHI_LIUHE.get(z) == bz:
            relations.append(f"流年地支「{z}」与{p['柱']}支「{bz}」六合")
        if ZHI_LIUCHONG.get(z) == bz:
            relations.append(f"流年地支「{z}」与{p['柱']}支「{bz}」六冲")

    # 流年 vs 当前大运：岁运并临 / 天克地冲 / 天合地合
    yun_rel = []
    if cur_yun:
        yg, yz = cur_yun["天干"], cur_yun["地支"]
        if (g, z) == (yg, yz):
            yun_rel.append(f"岁运并临（流年与当前大运同为「{gz}」，这股能量的年份主题被放大）")
        else:
            if KE[WX_GAN[g]] == WX_GAN[yg] and ZHI_LIUCHONG.get(z) == yz:
                yun_rel.append(f"流年「{gz}」与当前大运「{yg}{yz}」天克地冲（年度气候与十年气候拉扯明显）")
            if GAN_WUHE.get(g) == yg and ZHI_LIUHE.get(z) == yz:
                yun_rel.append(f"流年「{gz}」与当前大运「{yg}{yz}」天合地合（年度气候与十年气候同向）")

    # 喜忌归属（扶抑 + 调候）
    th = tiaohou_wx(month_zhi)
    xi, ji = xiyong.get("扶抑喜", []), xiyong.get("扶抑忌", [])

    def tag(wx):
        t = []
        if wx in xi:
            t.append("扶抑喜")
        if wx in ji:
            t.append("扶抑忌")
        if th and wx == th:
            t.append("调候喜")
        return t

    return {
        "年": yy, "干支": gz,
        "天干": {"字": g, "五行": g_wx, "十神": g_ss, "喜忌": tag(g_wx)},
        "地支": {"字": z, "五行": z_wx, "本气十神": z_ss, "喜忌": tag(z_wx)},
        "主题": themes,
        "与命局关系": relations,
        "与当前大运": yun_rel,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--place", default="上海",
                    help="出生城市，用于真太阳时校正；城市表查无则按东经 120° 近似，"
                         "并在输出的「需确认事项」里提示（可用 --lon 直接给经度）")
    ap.add_argument("--lon", type=float, default=None,
                    help="出生地经度（东经为正，西经为负）。城市表查不到时用，优先级高于 --place")
    ap.add_argument("--gender", required=True, choices=["男", "女"])
    args = ap.parse_args()

    y, mo, d = map(int, args.date.split("-"))
    hh, mm = map(int, args.time.split(":"))

    # 经度：--lon > 城市表 > 东经 120° 近似（未命中会标记，交给 SKILL 层询问）
    lng, city_hit = resolve_lng(args.place, args.lon)
    # 真太阳时只作参考，不用于排盘；边界检测基于钟表时间
    thh, tmm, lng, delta = true_solar_time(hh, mm, lng)
    boundary = hour_branch_boundary(hh, mm, thh, tmm)

    # 排盘用【钟表时间】（默认口径），不做无条件真太阳时校正
    solar = Solar.fromYmdHms(y, mo, d, hh, mm, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()

    day_gan = ec.getDayGan()

    pillars = []
    for name, gan, zhi in [
        ("年", ec.getYearGan(), ec.getYearZhi()),
        ("月", ec.getMonthGan(), ec.getMonthZhi()),
        ("日", ec.getDayGan(), ec.getDayZhi()),
        ("时", ec.getTimeGan(), ec.getTimeZhi()),
    ]:
        hide = ec.getYearHideGan() if name == "年" else \
               ec.getMonthHideGan() if name == "月" else \
               ec.getDayHideGan() if name == "日" else ec.getTimeHideGan()
        pillars.append({
            "柱": name,
            "天干": gan, "天干十神": "日主" if name == "日" else shishen(day_gan, gan),
            "地支": zhi, "藏干": hide,
            "藏干十神": [shishen(day_gan, g) for g in hide],
        })

    strength = judge_strength(day_gan, ec.getMonthZhi(), pillars)
    cnt = count_wuxing(ec, pillars)
    # 接近从弱时，取命局最旺五行为「旺神」，顺势取用（v1.4）
    dominant_wx = None
    if strength.get("cong_weak"):
        dominant_wx = max(cnt["含藏干"], key=lambda k: cnt["含藏干"][k])
    xiyong = guess_xiyong(strength["level"], day_gan, ec.getMonthZhi(),
                          cong_weak=strength.get("cong_weak", False),
                          dominant_wx=dominant_wx)

    yun = ec.getYun(0 if args.gender == "女" else 1)
    dayun = []
    # ⚠️ 循环变量必须用 dy 不能用 d——d 已被上面的「出生日」占用，
    # 用 d 会遮蔽日期导致后续 check_dst(y, mo, d) 崩掉（2026-09-03 踩过）
    for dy in yun.getDaYun()[:9]:
        gz = dy.getGanZhi()
        if not gz:
            continue
        g, z = gz[0], gz[1]
        dayun.append({"岁": dy.getStartAge(), "干支": gz,
                      "年": f"{dy.getStartYear()}-{dy.getEndYear()}",
                      "天干": g, "地支": z,
                      "天干五行": WX_GAN.get(g, ""), "地支五行": WX_ZHI.get(z, ""),
                      "天干十神": shishen(day_gan, g)})
    now_year = datetime.date.today().year
    cur_yun = next((dy for dy in dayun
                    if int(dy["年"].split("-")[0]) <= now_year <= int(dy["年"].split("-")[1])), None)

    liunian = []
    for i in range(0, 6):
        yy = now_year + i
        gz = Solar.fromYmd(yy, 6, 1).getLunar().getYearInGanZhi()
        liunian.append({"年": yy, "干支": gz, "天干十神": shishen(day_gan, gz[0]),
                        "天干五行": WX_GAN[gz[0]], "地支五行": WX_ZHI[gz[1]]})

    # 流年详解（事实层）：当年 + 明年
    liunian_xq = [liunian_detail(yy, day_gan, pillars, cur_yun, xiyong,
                                 ec.getMonthZhi(), args.gender)
                  for yy in (now_year, now_year + 1)]

    # 汇总所有「必须先向用户确认再出报告」的事项
    # SKILL 层：此项非空 → 先确认，再写报告；不得静默跳过
    pending = []
    if not city_hit:
        pending.append({
            "类型": "出生地经度未知",
            "说明": f"城市表里没有「{args.place}」，已按东经 {DEFAULT_LNG}° 近似处理。",
            "提示": ("请向用户确认出生地经度（或所在省市）。经度差每 1° 相当于 4 分钟，"
                     "偏远地区（如乌鲁木齐）误差可达 2 小时，时柱会排错。"),
        })
    # 只有「钟表时间与真太阳时落在不同时辰」才提示——这会真正改变时柱。
    # 单纯「差了几分钟」不提示，否则深圳（-23.8 分钟）这类会次次报警，变成噪音。
    b_clock, b_true = hour_branch(hh, mm), hour_branch(thh, tmm)
    if b_clock != b_true:
        pending.append({
            "类型": "真太阳时跨时辰",
            "说明": (f"按钟表时间 {hh:02d}:{mm:02d} 属「{b_clock}时」，"
                     f"按真太阳时 {thh:02d}:{tmm:02d} 属「{b_true}时」——两者不在同一时辰"
                     f"（出生地东经 {lng}°，修正 {delta:+.1f} 分钟）。"),
            "提示": ("默认按钟表时间排盘。但这一步会改变时柱，进而影响整张盘的五行结构，"
                     "请向用户确认按哪个口径（现代命理多数按钟表时间，部分流派按真太阳时），"
                     "不要替用户选流派。"),
        })
    dst = check_dst(y, mo, d)
    if dst:
        pending.append(dst)
    # 统一补齐「说明」字段，让所有待确认项结构一致（类型/说明/提示），
    # 便于 SKILL 层用同一套方式读取，不必按类型分支处理
    for b in boundary:
        pending.append({
            "类型": "时辰边界",
            "说明": (f"钟表时间 {b['钟表时间']} 落在「{b['边界']}时」起点 ±15 分钟内，"
                     f"真太阳时为 {b['真太阳时']}，可能落入相邻时辰。"),
            **b,
        })

    result = {
        "输入": {"date": args.date, "time": args.time, "place": args.place,
                 "gender": args.gender, "经度": lng, "城市已匹配": city_hit,
                 "经度来源": ("--lon 指定" if args.lon is not None
                             else "城市表" if city_hit
                             else f"未命中城市表，按东经 {DEFAULT_LNG}° 近似"),
                 "真太阳时修正(分)": delta,
                 "真太阳时": f"{thh:02d}:{tmm:02d}",
                 "排盘时辰口径": "钟表时间（默认，真太阳时仅作参考）"},
        "需确认事项": pending,
        "时辰边界提示": boundary,
        "农历": lunar.toString(),
        "八字": f"{ec.getYear()} {ec.getMonth()} {ec.getDay()} {ec.getTime()}",
        "日主": {"天干": day_gan, "五行": WX_GAN[day_gan],
                 "阴阳": "阴" if day_gan in YIN_GAN else "阳",
                 "日主解读": "阳金（刀剑矿石，硬直刚健）" if day_gan == "庚"
                 else "阴金（珠玉首饰，精致重修饰）" if day_gan == "辛"
                 else WX_GAN[day_gan]},
        "五行计数": cnt,
        "四柱": pillars,
        "身强弱初判": strength,
        "喜用候选": xiyong,
        "大运": dayun,
        "当前大运": cur_yun,
        "流年": liunian,
        "流年详解": liunian_xq,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
