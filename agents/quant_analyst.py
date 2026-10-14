"""
量化规则诊断引擎 (本地 Python，每次运行即时生成，不依赖大模型)
把全市场切片拆解为模块化结论：大盘 / 各指数 / 各板块 / 各标的 / 全局纪律清单。
深度的自然语言解读由 Antigravity 定时任务写入 reports/ai_insights/latest.json (见 agents/ai_bridge.py)。
"""
from typing import Dict, Any, List, Optional


def _s(v, suffix="%"):
    """带符号格式化"""
    if v is None:
        return "-"
    try:
        return f"{'+' if float(v) > 0 else ''}{float(v):.2f}{suffix}"
    except Exception:
        return str(v)


def _v(v):
    return "-" if v is None else v


# ----------------------------------------------------------------------
# 大盘
# ----------------------------------------------------------------------

def analyze_market(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    indices = snapshot.get("indices", [])
    board = snapshot.get("industry_board", [])

    valid = [i for i in indices if i.get("price")]
    up = [i for i in valid if i["change_pct"] > 0]
    down = [i for i in valid if i["change_pct"] < 0]
    avg = sum(i["change_pct"] for i in valid) / len(valid) if valid else 0.0

    up_ind = sum(1 for b in board if b["change_pct"] > 0)
    down_ind = sum(1 for b in board if b["change_pct"] < 0)
    net_total = round(sum(b["net_yi"] for b in board), 2) if board else None

    below_ma20 = [i["name"] for i in valid if i["indicators"].get("ma20") and i["price"] < i["indicators"]["ma20"]]

    if len(down) >= 3 and avg < -1:
        sentiment, level = "整体偏空，成长科技失血，资金避险情绪浓厚", "bear"
        stance = "防守优先，严控仓位，禁止左侧抄底"
    elif len(down) >= 3:
        sentiment, level = "普跌调整，但跌幅可控", "bear"
        stance = "控制仓位，等待企稳信号"
    elif len(up) >= 3 and avg > 1:
        sentiment, level = "多头共振，增量资金承接良好", "bull"
        stance = "顺势而为，聚焦主线，持股待涨"
    elif len(up) >= 3:
        sentiment, level = "温和普涨，情绪修复", "bull"
        stance = "持股为主，回踩低吸"
    else:
        sentiment, level = "指数分化，存量博弈，题材轮动", "neutral"
        stance = "去弱留强，紧盯持仓止损红线"

    position_advice = "总仓位建议 ≤ 5 成 (主要指数位于 MA20 下方)" if len(below_ma20) >= 2 else "总仓位可维持正常水平 (主要指数仍在 MA20 上方)"

    points = [
        "宽基表现：" + "、".join(f"{i['name']} {_s(i['change_pct'])}" for i in valid) if valid else "宽基数据暂缺",
        f"行业涨跌比：{up_ind} 涨 / {down_ind} 跌" + (f"，行业资金合计净额 {_s(net_total, ' 亿')}" if net_total is not None else ""),
    ]
    if board:
        points.append("领涨行业：" + "、".join(f"{b['name']} {_s(b['change_pct'])}" for b in board[:5]))
        points.append("领跌行业：" + "、".join(f"{b['name']} {_s(b['change_pct'])}" for b in board[-5:][::-1]))
    if below_ma20:
        points.append("位于 MA20 下方的指数：" + "、".join(below_ma20))
    points.append(position_advice)

    return {"sentiment": sentiment, "stance": stance, "level": level, "points": points,
            "position_advice": position_advice, "breadth": {"up": up_ind, "down": down_ind, "net_yi": net_total}}


def analyze_index(idx: Dict[str, Any]) -> Dict[str, Any]:
    ind = idx.get("indicators", {})
    price, chg = idx.get("price", 0), idx.get("change_pct", 0)
    ma5, ma20 = ind.get("ma5"), ind.get("ma20")

    if not price:
        return {"verdict": "数据暂缺", "level": "neutral", "points": ["指数报价获取失败"]}
    if ma20 and price > ma20:
        verdict, level = ("强势运行 · 站稳 MA20", "bull") if chg >= 0 else ("回调 · 仍在 MA20 上方", "neutral")
    elif ma20:
        verdict, level = ("弱势反弹 · 受压 MA20", "neutral") if chg > 0 else ("弱势 · 运行于 MA20 下方", "bear")
    else:
        verdict, level = "均线数据不足", "neutral"

    points = [
        f"现价 {price} 点（{_s(chg)}），成交额 {idx.get('amount_yi', '-')} 亿",
        f"MA5 {_v(ma5)} / MA10 {_v(ind.get('ma10'))} / MA20 {_v(ma20)}，{ind.get('trend_alignment', '-')}",
        f"近 5 日 {_s(ind.get('recent_5d_pct_change'))}，近 20 日 {_s(ind.get('recent_20d_pct_change'))}，20 日乖离 {_s(ind.get('bias20_pct'))}",
    ]
    hi, lo = ind.get("recent_20d_high"), ind.get("recent_20d_low")
    if hi and lo:
        points.append(f"20 日区间 {lo} ~ {hi}，距区间高点 {_s((price - hi) / hi * 100)}")
    if ma5 and ma20:
        points.append(f"关键位：短线 MA5 {ma5}，生命线 MA20 {ma20}")
    return {"verdict": verdict, "level": level, "points": points}


# ----------------------------------------------------------------------
# 板块
# ----------------------------------------------------------------------

def analyze_sector(sec: Dict[str, Any], stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    name = sec.get("name")
    related = [f"{s['name']}({s['code']})" for s in stocks
               if name and (name in (s.get("sector") or "") or (sec.get("matched_name") or "#") in (s.get("sector") or ""))]

    if sec.get("found") is False:
        sug = sec.get("suggestions") or []
        return {"verdict": "未匹配到同花顺行业", "level": "neutral", "related": related,
                "points": [f"「{name}」不在同花顺行业列表中" + (f"，可尝试：{'、'.join(sug)}" if sug else "，请检查名称")]}

    chg, net = sec.get("change_pct", 0.0), sec.get("net_yi", 0.0)
    rank, total = sec.get("rank"), sec.get("total")
    if chg > 0 and net > 0:
        verdict, level = ("主线领涨 · 资金流入", "bull") if rank and rank <= 10 else ("资金流入 · 偏强", "bull")
    elif chg > 0:
        verdict, level = "上涨但资金流出 · 谨防冲高回落", "neutral"
    elif net > 0:
        verdict, level = "下跌但资金逆势流入 · 观察承接", "neutral"
    else:
        verdict, level = "资金流出 · 弱势回避", "bear"

    points = [
        f"今日 {_s(chg)}，涨幅排名 {rank}/{total}",
        f"资金：流入 {sec.get('inflow_yi')} 亿 / 流出 {sec.get('outflow_yi')} 亿，净额 {_s(net, ' 亿')}",
        f"领涨股：{sec.get('leader')}（{_s(sec.get('leader_change_pct'))}），板块共 {sec.get('companies')} 家公司",
    ]
    if sec.get("focus_note"):
        points.append(f"我的观察逻辑：{sec['focus_note']}")
    if related:
        points.append("自选池中相关标的：" + "、".join(related))
    return {"verdict": verdict, "level": level, "points": points, "related": related}


# ----------------------------------------------------------------------
# 个股 / ETF
# ----------------------------------------------------------------------

def _linked_sector(stock: Dict[str, Any], sectors: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    label = stock.get("sector") or ""
    for sec in sectors:
        if sec.get("found") and (sec["name"] in label or sec.get("matched_name", "#") in label):
            return sec
    return None


def analyze_stock(s: Dict[str, Any], sectors: List[Dict[str, Any]]) -> Dict[str, Any]:
    q, ind, risk = s.get("quote", {}), s.get("indicators", {}), s.get("risk", {})
    price, chg = q.get("current_price", 0.0), q.get("change_pct", 0.0)
    ma5, ma10, ma20 = ind.get("ma5"), ind.get("ma10"), ind.get("ma20")
    vr, trend = ind.get("volume_ratio"), ind.get("trend_alignment", "-")
    lvl = risk.get("risk_level", "NONE")

    if not price:
        return {"decision": "数据暂缺", "level": "watch", "priority": 9, "points": ["行情获取失败，下次运行时自动重试"],
                "actions": []}

    # ---- 决策 ----
    if risk.get("is_holding"):
        if lvl == "CRITICAL":
            decision, level, pr = "坚决止损", "stop", 0
        elif lvl == "PROFIT":
            decision, level, pr = "分批止盈", "profit", 2
        elif lvl == "WARNING":
            decision, level, pr = "减仓防守", "warn", 1
        elif ma20 and price < ma20:
            decision, level, pr = "跌破 MA20 · 减仓防守", "warn", 1
        elif ma5 and price >= ma5:
            decision, level, pr = "持股待涨", "hold", 4
        else:
            decision, level, pr = "锁仓观望", "hold", 4
    else:
        if "多头" in trend and vr and vr >= 1.3 and chg > 0:
            decision, level, pr = "分批低吸 / 轻仓试错", "buy", 3
        elif ma20 and price > ma20 and chg > 0:
            decision, level, pr = "关注回踩低吸", "watch", 5
        else:
            decision, level, pr = "空仓观望", "watch", 6

    # ---- 论据 ----
    vol_note = ""
    if vr is not None:
        vol_note = "，放量" if vr >= 1.3 else ("，缩量" if vr <= 0.8 else "，量能平稳")
    points = [
        f"量价：现价 {price}（{_s(chg)}），成交额 {q.get('amount_yi', '-')} 亿，量比(近日/5日均) {_v(vr)}{vol_note}",
        f"均线：MA5 {_v(ma5)} / MA10 {_v(ma10)} / MA20 {_v(ma20)}，{trend}",
    ]
    bias = ind.get("bias20_pct")
    if bias is not None:
        tip = "，深度超跌，警惕弱势惯性" if bias < -8 else ("，短线乖离偏大，追高风险" if bias > 8 else "")
        points.append(f"乖离：20 日乖离率 {_s(bias)}{tip}")
    points.append(f"区间：近 5 日 {_s(ind.get('recent_5d_pct_change'))}（{_v(ind.get('recent_5d_low'))} ~ {_v(ind.get('recent_5d_high'))}），"
                  f"近 20 日 {_s(ind.get('recent_20d_pct_change'))}")

    sec = _linked_sector(s, sectors)
    if sec:
        points.append(f"板块：所属关注板块「{sec['name']}」今日 {_s(sec.get('change_pct'))}，资金净额 {_s(sec.get('net_yi'), ' 亿')}")

    if risk.get("is_holding"):
        if lvl == "UNSET":
            points.append("仓位：持仓中，但尚未填写成本价，无法核算盈亏")
        else:
            points.append(f"仓位：成本 {risk['cost_price']}，浮动 {_s(risk['pnl_pct'])}（{_s(risk['pnl_amount'], ' 元')}），"
                          f"止损价 {risk['stop_loss_price']}（距现价 {_s(risk['distance_to_stop_pct'])}），止盈价 {risk['take_profit_price']}")
        points.append(f"风控：{risk.get('action_advice', '')}")

    if s.get("news"):
        points.append("资讯：" + " | ".join(n["title"] for n in s["news"][:2]))

    # ---- 触发条件 ----
    actions = []
    if risk.get("is_holding") and risk.get("stop_loss_price"):
        actions.append(f"跌破止损价 {risk['stop_loss_price']} → 无条件离场")
        if ma20:
            actions.append(f"收盘跌破 MA20 {ma20} 且无法收回 → 减半仓")
        actions.append(f"触及止盈价 {risk['take_profit_price']} → 分批锁定半仓利润")
    elif not risk.get("is_holding"):
        if ma20:
            actions.append(f"放量 (量比 ≥ 1.3) 站上 MA20 {ma20} → 可轻仓试错")
        if ma5:
            actions.append(f"回踩 MA5 {ma5} 缩量企稳 → 低吸观察")

    return {"decision": decision, "level": level, "priority": pr, "points": points, "actions": actions}


# ----------------------------------------------------------------------
# 汇总
# ----------------------------------------------------------------------

PRIORITY_LABEL = {0: "🟢 紧急止损", 1: "🟡 警戒减仓", 2: "🔴 分批止盈", 3: "🔴 试仓机会",
                  4: "⚪ 持仓跟踪", 5: "⚪ 观察回踩", 6: "⚪ 观察等待", 9: "⚪ 数据暂缺"}


def build_analysis(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    stocks = snapshot.get("stocks", [])
    monitored = snapshot.get("monitored_sectors", [])
    board = snapshot.get("industry_board", [])

    stock_analysis = {s["code"]: analyze_stock(s, monitored) for s in stocks}
    sector_analysis = {sec["name"]: analyze_sector(sec, stocks) for sec in monitored}
    # 热门板块 (未加入关注的) 也提供下钻诊断
    for b in board[:5] + board[-5:]:
        sector_analysis.setdefault(b["name"], analyze_sector({**b, "found": True}, stocks))

    discipline = []
    for s in stocks:
        a = stock_analysis[s["code"]]
        cond = a["actions"][0] if a["actions"] else a["decision"]
        discipline.append({"priority": a["priority"], "label": PRIORITY_LABEL.get(a["priority"], "⚪"),
                           "code": s["code"], "name": s["name"], "decision": a["decision"],
                           "level": a["level"], "condition": cond})
    discipline.sort(key=lambda x: x["priority"])

    return {
        "market": analyze_market(snapshot),
        "indices": {i["name"]: analyze_index(i) for i in snapshot.get("indices", [])},
        "sectors": sector_analysis,
        "stocks": stock_analysis,
        "discipline": discipline,
    }


def render_markdown(result: Dict[str, Any]) -> str:
    """把模块化结论编译为 Markdown (用于归档与推送)"""
    snap, ana = result["snapshot"], result["analysis"]
    m = ana["market"]
    lines = [f"🔗 官方策略跟踪与参考通道：{result.get('mandatory_link', 'https://52etf.site/')}", "",
             f"# {result.get('session_title', '投研内参')}", f"> 数据时点：`{snap.get('generated_at')}`", "",
             "## 一、大盘研判", f"**{m['sentiment']}** —— {m['stance']}", ""]
    lines += [f"- {p}" for p in m["points"]]
    lines += ["", "## 二、指数"]
    for i in snap.get("indices", []):
        a = ana["indices"].get(i["name"], {})
        lines.append(f"- **{i['name']}** {i['price']}（{_s(i['change_pct'])}）：{a.get('verdict', '-')}")
    lines += ["", "## 三、关注板块"]
    for sec in snap.get("monitored_sectors", []):
        a = ana["sectors"].get(sec["name"], {})
        lines.append(f"- **{sec['name']}**（{_s(sec.get('change_pct'))}）：{a.get('verdict', '-')}")
    lines += ["", "## 四、自选标的"]
    for s in snap.get("stocks", []):
        a = ana["stocks"].get(s["code"], {})
        lines.append(f"### {s['name']} ({s['code']}) —— **{a.get('decision', '-')}**")
        lines += [f"- {p}" for p in a.get("points", [])]
        lines += [f"- ▶ {x}" for x in a.get("actions", [])]
        lines.append("")
    lines += ["## 五、纪律清单", "| 优先级 | 标的 | 结论 | 触发条件 |", "| :--- | :--- | :--- | :--- |"]
    for d in ana["discipline"]:
        lines.append(f"| {d['label']} | {d['name']}({d['code']}) | {d['decision']} | {d['condition']} |")
    return "\n".join(lines)
