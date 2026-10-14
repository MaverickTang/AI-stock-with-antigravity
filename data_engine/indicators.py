"""
量化指标与风控计算工具
包含均线系统、量比、乖离率、区间涨跌以及持仓风控水位的数学计算
"""
from typing import Dict, Any, Optional
import pandas as pd


def _col(df: pd.DataFrame, *names) -> Optional[str]:
    for n in names:
        if n in df.columns:
            return n
    return None


def _r(v, n=3):
    try:
        if v is None or pd.isna(v):
            return None
        return round(float(v), n)
    except Exception:
        return None


def calculate_technical_indicators(daily_df: Optional[pd.DataFrame], current_price: float) -> Dict[str, Any]:
    """
    基于历史日K线 (不含当日) 和当前最新价，计算关键量化技术指标
    """
    ind: Dict[str, Any] = {
        "ma5": None, "ma10": None, "ma20": None,
        "bias20_pct": None, "volume_ratio": None,
        "recent_5d_high": None, "recent_5d_low": None, "recent_5d_pct_change": None,
        "recent_20d_high": None, "recent_20d_low": None, "recent_20d_pct_change": None,
        "trend_alignment": "数据不足",
    }
    if daily_df is None or len(daily_df) < 5:
        return ind

    try:
        df = daily_df.copy()
        c = _col(df, "close", "收盘")
        v = _col(df, "volume", "成交量")
        h = _col(df, "high", "最高")
        lo = _col(df, "low", "最低")
        for col in (c, v, h, lo):
            if col:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        closes = df[c].dropna()
        price = current_price if current_price and current_price > 0 else float(closes.iloc[-1])

        def ma(n):
            return _r(closes.tail(n).mean()) if len(closes) >= n else None

        ind["ma5"], ind["ma10"], ind["ma20"] = ma(5), ma(10), ma(20)

        if ind["ma20"]:
            ind["bias20_pct"] = _r((price - ind["ma20"]) / ind["ma20"] * 100, 2)

        ma5, ma10, ma20 = ind["ma5"], ind["ma10"], ind["ma20"]
        if ma5 and ma10 and ma20:
            if price >= ma5 >= ma10 >= ma20:
                ind["trend_alignment"] = "完美多头排列 (强势)"
            elif price < ma5 < ma10 < ma20:
                ind["trend_alignment"] = "空头排列 (弱势寻底)"
            elif price > ma20:
                ind["trend_alignment"] = "震荡偏强 (站上生命线)"
            else:
                ind["trend_alignment"] = "震荡偏弱 (受压于20日线)"

        if v:
            vols = df[v].dropna()
            if len(vols) >= 5 and vols.tail(5).mean() > 0:
                ind["volume_ratio"] = _r(vols.iloc[-1] / vols.tail(5).mean(), 2)

        last5, last20 = df.tail(5), df.tail(20)
        if h and lo:
            ind["recent_5d_high"] = _r(last5[h].max())
            ind["recent_5d_low"] = _r(last5[lo].min())
            ind["recent_20d_high"] = _r(last20[h].max())
            ind["recent_20d_low"] = _r(last20[lo].min())

        if len(closes) >= 5 and closes.iloc[-5] > 0:
            ind["recent_5d_pct_change"] = _r((price - closes.iloc[-5]) / closes.iloc[-5] * 100, 2)
        if len(closes) >= 20 and closes.iloc[-20] > 0:
            ind["recent_20d_pct_change"] = _r((price - closes.iloc[-20]) / closes.iloc[-20] * 100, 2)
    except Exception as e:
        ind["error"] = str(e)

    return ind


def calculate_position_risk(holding_config: Optional[Dict[str, Any]], current_price: float) -> Dict[str, Any]:
    """
    计算持仓风险水位、盈亏比例与止盈止损触发状态
    risk_level: NONE(未持仓) / UNSET(持仓但未填成本) / NORMAL / WARNING / CRITICAL(触发止损) / PROFIT(达止盈)
    """
    holding_config = holding_config or {}
    cost = float(holding_config.get("cost_price") or 0.0)
    shares = int(holding_config.get("shares") or 0)
    sl_pct = float(holding_config.get("stop_loss_pct") or 6.0)
    tp_pct = float(holding_config.get("take_profit_pct") or 15.0)

    base = {
        "is_holding": False, "risk_level": "NONE", "status_label": "未持仓 (观察标的)",
        "cost_price": cost, "shares": shares, "stop_loss_pct": sl_pct, "take_profit_pct": tp_pct,
        "current_price": current_price, "market_value": 0.0,
        "pnl_pct": 0.0, "pnl_amount": 0.0,
        "stop_loss_price": None, "take_profit_price": None, "distance_to_stop_pct": None,
        "action_advice": "跟踪形态，等待开仓信号",
    }

    if not holding_config.get("is_holding"):
        return base

    base["is_holding"] = True
    if cost <= 0 or not current_price or current_price <= 0:
        base.update({
            "risk_level": "UNSET", "status_label": "持仓中 (未设置成本价)",
            "action_advice": "请在标的详情页填写成本价，以启用盈亏与止损核算",
        })
        return base

    pnl_pct = (current_price - cost) / cost * 100
    stop_price = round(cost * (1 - sl_pct / 100), 3)
    tp_price = round(cost * (1 + tp_pct / 100), 3)
    dist_stop = (current_price - stop_price) / current_price * 100

    if pnl_pct <= -sl_pct:
        level, label = "CRITICAL", f"🚨 触发硬性止损 (跌破 -{sl_pct}%)"
        advice = f"现价 {current_price} 已跌破止损价 {stop_price}，严格执行纪律离场，严禁摊平死扛。"
    elif pnl_pct >= tp_pct:
        level, label = "PROFIT", f"🎯 达到止盈目标 (+{tp_pct}%)"
        advice = f"已达止盈价 {tp_price}，建议分批锁定半仓利润，剩余仓位止损上移至成本价。"
    elif pnl_pct < -(sl_pct * 0.7):
        level, label = "WARNING", "⚠️ 接近止损警戒区"
        advice = f"浮亏 {pnl_pct:.2f}%，距止损价 {stop_price} 仅剩 {dist_stop:.2f}%，盯紧分时支撑。"
    else:
        level, label = "NORMAL", "✅ 持仓安全区"
        advice = "持仓处于正常波动范围，结合均线走势继续跟踪。"

    base.update({
        "risk_level": level, "status_label": label,
        "market_value": round(current_price * shares, 2),
        "pnl_pct": round(pnl_pct, 2), "pnl_amount": round((current_price - cost) * shares, 2),
        "stop_loss_price": stop_price, "take_profit_price": tp_price,
        "distance_to_stop_pct": round(dist_stop, 2), "action_advice": advice,
    })
    return base
