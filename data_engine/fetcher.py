"""
稳健多源数据采集引擎
- 实时报价 / 指数报价：新浪 hq.sinajs.cn 直连 (快、稳定)
- 日K线：新浪 (个股 stock_zh_a_daily / ETF fund_etf_hist_sina / 指数 stock_zh_index_daily)
- 行业板块：同花顺行业资金流 (含涨跌幅、资金净额、领涨股)
- 个股资讯：东方财富
所有外部请求均带超时保护，单个接口卡死不会拖垮整条流水线。
"""
import os
import re
import difflib
import requests
import pandas as pd
import akshare as ak
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import List, Dict, Any, Optional

from .indicators import calculate_technical_indicators, calculate_position_risk


def clean_network_env():
    """清理可能导致底层 HTTP 连接挂起的代理环境变量"""
    for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
        os.environ.pop(key, None)


clean_network_env()

_EXECUTOR = ThreadPoolExecutor(max_workers=16, thread_name_prefix="fetch")


def call_with_timeout(fn, *args, timeout: float = 20, default=None, label: str = "", **kwargs):
    """在线程中执行外部请求，超时或异常时返回默认值"""
    future = _EXECUTOR.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except FutureTimeout:
        print(f"⚠️ [{label}] 请求超时 ({timeout}s)，已跳过")
    except Exception as e:
        print(f"⚠️ [{label}] 获取失败: {e}")
    return default


INDEX_CODES = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "创业板指": "sz399006",
    "科创50": "sh000688",
}


def format_symbol_for_sina(code: str) -> str:
    """根据股票或ETF代码生成新浪规范代码 (sh/sz/bj)"""
    code_str = str(code).strip()
    if code_str.startswith(("sh", "sz", "bj")):
        return code_str
    if code_str.startswith(("60", "68", "51", "56", "58", "90")):
        return f"sh{code_str}"
    if code_str.startswith(("00", "30", "15", "16", "12", "20")):
        return f"sz{code_str}"
    if code_str.startswith(("4", "8")):
        return f"bj{code_str}"
    return f"sh{code_str}"


def infer_asset_type(code: str) -> str:
    return "etf" if str(code).startswith(("51", "56", "58", "15", "16")) else "stock"


def _f(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


# ----------------------------------------------------------------------
# 纯函数：便于离线 (不联网) 重算
# ----------------------------------------------------------------------

def build_monitored_sectors(board: List[Dict[str, Any]], custom_sectors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把用户关注的板块与同花顺行业全表匹配，输出带资金明细的板块数据"""
    results = []
    names = [b["name"] for b in board]
    for s in custom_sectors or []:
        name = str(s.get("name", "")).strip()
        if not name:
            continue
        match = next((b for b in board if b["name"] == name), None)
        if not match:
            match = next((b for b in board if name in b["name"] or b["name"] in name), None)
        entry = {"name": name, "focus_note": s.get("focus_note", ""), "found": bool(match)}
        if match:
            entry.update({k: v for k, v in match.items() if k != "name"})
            entry["matched_name"] = match["name"]
        else:
            entry.update({"change_pct": 0.0, "suggestions": difflib.get_close_matches(name, names, n=3, cutoff=0.3)})
        results.append(entry)
    return results


def build_stock_entry(item: Dict[str, Any], quote: Dict[str, Any], indicators: Dict[str, Any],
                      news: List[Dict[str, Any]]) -> Dict[str, Any]:
    code = item["code"]
    curr = quote.get("current_price", 0.0)
    return {
        "code": code,
        "name": quote.get("name") or item.get("name", code),
        "asset_type": item.get("asset_type", infer_asset_type(code)),
        "sector": item.get("sector", ""),
        "quote": quote,
        "indicators": indicators,
        "risk": calculate_position_risk(item.get("holding", {}), curr),
        "news": news,
        "strategy_note": item.get("strategy_note", ""),
    }


class MarketDataEngine:
    def __init__(self):
        clean_network_env()

    # ------------------------------------------------------------------
    # 实时报价
    # ------------------------------------------------------------------
    def _fetch_sina(self, sina_symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        if not sina_symbols:
            return {}
        url = f"https://hq.sinajs.cn/list={','.join(sina_symbols)}"
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        out = {}
        resp = requests.get(url, headers=headers, timeout=8)
        resp.encoding = "gbk"
        for line in resp.text.strip().split("\n"):
            m = re.search(r'var hq_str_(\w+)="([^"]*)";', line)
            if not m:
                continue
            sym, data = m.groups()
            f = data.split(",")
            if len(f) < 32:
                continue
            pre_close, cur = _f(f[2]), _f(f[3])
            if cur <= 0:  # 停牌或集合竞价前，用昨收代替
                cur = pre_close
            chg = cur - pre_close if pre_close > 0 else 0.0
            amount = _f(f[9])
            out[sym] = {
                "name": f[0],
                "open_price": round(_f(f[1]), 3),
                "pre_close": round(pre_close, 3),
                "current_price": round(cur, 3),
                "high_price": round(_f(f[4]), 3),
                "low_price": round(_f(f[5]), 3),
                "volume": _f(f[8]),
                "amount_yi": round(amount / 1e8, 2),
                "change_amount": round(chg, 3),
                "change_pct": round(chg / pre_close * 100, 2) if pre_close > 0 else 0.0,
                "datetime": f"{f[30]} {f[31]}",
            }
        return out

    def get_realtime_quotes(self, codes: List[str]) -> Dict[str, Dict[str, Any]]:
        sym_map = {format_symbol_for_sina(c): c for c in codes}
        raw = call_with_timeout(self._fetch_sina, list(sym_map.keys()), timeout=10, default={}, label="实时报价")
        result = {}
        for sym, q in (raw or {}).items():
            code = sym_map.get(sym, sym)
            q["code"] = code
            result[code] = q
        return result

    # ------------------------------------------------------------------
    # 元数据自动补全 (只输入代码即可)
    # ------------------------------------------------------------------
    def enrich_stock_metadata(self, code: str, existing_item: Optional[Dict[str, Any]] = None,
                              quote: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code_str = str(code).strip()
        item = dict(existing_item or {})
        item["code"] = code_str
        item.setdefault("asset_type", infer_asset_type(code_str))

        if quote is None:
            quote = self.get_realtime_quotes([code_str]).get(code_str, {})
        if quote.get("name"):
            item["name"] = quote["name"]
        item.setdefault("name", f"标的_{code_str}")

        if not item.get("sector"):
            item["sector"] = "行业ETF" if item["asset_type"] == "etf" else "待补充 (可在详情页修改)"

        h = item.get("holding") if isinstance(item.get("holding"), dict) else {}
        h.setdefault("is_holding", False)
        h.setdefault("cost_price", 0.0)
        h.setdefault("shares", 0)
        h.setdefault("stop_loss_pct", 6.0)
        h.setdefault("take_profit_pct", 15.0)
        item["holding"] = h

        item.setdefault("strategy_note", "")
        return item

    @staticmethod
    def needs_enrich(item: Dict[str, Any]) -> bool:
        return (not item.get("name") or not item.get("asset_type") or not isinstance(item.get("holding"), dict)
                or "strategy_note" not in item or not item.get("sector"))

    # ------------------------------------------------------------------
    # 大盘指数
    # ------------------------------------------------------------------
    def get_index_kline(self, sina_code: str, days: int = 60) -> Optional[pd.DataFrame]:
        df = call_with_timeout(ak.stock_zh_index_daily, symbol=sina_code, timeout=20, label=f"指数K线 {sina_code}")
        if df is None or df.empty:
            return None
        return df.tail(days)

    def get_market_indices(self, with_detail: bool = True) -> List[Dict[str, Any]]:
        raw = call_with_timeout(self._fetch_sina, list(INDEX_CODES.values()), timeout=10, default={}, label="指数报价")
        indices = []
        for name, sym in INDEX_CODES.items():
            q = (raw or {}).get(sym)
            if not q:
                indices.append({"name": name, "code": sym, "price": 0.0, "change_pct": 0.0, "amount_yi": 0.0,
                                "indicators": calculate_technical_indicators(None, 0)})
                continue
            entry = {
                "name": name, "code": sym,
                "price": round(q["current_price"], 2),
                "change_pct": q["change_pct"],
                "high": q["high_price"], "low": q["low_price"],
                "amount_yi": q["amount_yi"],
            }
            entry["indicators"] = calculate_technical_indicators(
                self.get_index_kline(sym) if with_detail else None, q["current_price"])
            indices.append(entry)
        return indices

    # ------------------------------------------------------------------
    # 行业板块 (同花顺行业资金流，全表约 90 个行业)
    # ------------------------------------------------------------------
    def get_industry_board(self) -> List[Dict[str, Any]]:
        df = call_with_timeout(ak.stock_fund_flow_industry, symbol="即时", timeout=25, label="行业资金流")
        if df is None or df.empty:
            return []
        board = []
        for _, r in df.iterrows():
            board.append({
                "name": str(r.get("行业")),
                "index_value": _f(r.get("行业指数")),
                "change_pct": round(_f(r.get("行业-涨跌幅")), 2),
                "inflow_yi": round(_f(r.get("流入资金")), 2),
                "outflow_yi": round(_f(r.get("流出资金")), 2),
                "net_yi": round(_f(r.get("净额")), 2),
                "companies": int(_f(r.get("公司家数"))),
                "leader": str(r.get("领涨股", "")),
                "leader_change_pct": round(_f(r.get("领涨股-涨跌幅")), 2),
                "leader_price": _f(r.get("当前价")),
            })
        board.sort(key=lambda x: x["change_pct"], reverse=True)
        for i, b in enumerate(board, 1):
            b["rank"] = i
            b["total"] = len(board)
            b["sector"] = b["name"]  # 兼容旧字段
        return board

    # ------------------------------------------------------------------
    # 个股 K 线与资讯
    # ------------------------------------------------------------------
    def get_stock_kline(self, code: str, asset_type: str = "stock", days: int = 60) -> Optional[pd.DataFrame]:
        sym = format_symbol_for_sina(code)
        if asset_type == "etf":
            df = call_with_timeout(ak.fund_etf_hist_sina, symbol=sym, timeout=20, label=f"ETF K线 {code}")
        else:
            df = call_with_timeout(ak.stock_zh_a_daily, symbol=sym, adjust="qfq", timeout=20, label=f"K线 {code}")
        if df is None or df.empty:
            return None
        return df.tail(days)

    def get_stock_news(self, code: str, limit: int = 5) -> List[Dict[str, Any]]:
        df = call_with_timeout(ak.stock_news_em, symbol=code, timeout=12, label=f"资讯 {code}")
        news = []
        if df is not None and not df.empty:
            for _, r in df.head(limit).iterrows():
                title = str(r.get("新闻标题", "")).strip()
                if title:
                    news.append({
                        "title": title,
                        "time": str(r.get("发布时间", "")),
                        "source": str(r.get("文章来源", "")),
                        "url": str(r.get("新闻链接", "")),
                    })
        return news

    # ------------------------------------------------------------------
    # 一键全市场切片
    # ------------------------------------------------------------------
    def collect_full_market_snapshot(self, watchlist_items: List[Dict[str, Any]],
                                     custom_sectors: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        indices = self.get_market_indices(with_detail=True)
        board = self.get_industry_board()
        quotes = self.get_realtime_quotes([it["code"] for it in watchlist_items])

        stocks = []
        for item in watchlist_items:
            code = item["code"]
            quote = quotes.get(code, {"code": code, "name": item.get("name", code), "current_price": 0.0,
                                      "change_pct": 0.0, "amount_yi": 0.0, "datetime": "-"})
            kline = self.get_stock_kline(code, item.get("asset_type", infer_asset_type(code)), days=60)
            ind = calculate_technical_indicators(kline, quote.get("current_price", 0.0))
            news = self.get_stock_news(code, limit=5)
            stocks.append(build_stock_entry(item, quote, ind, news))

        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "indices": indices,
            "industry_board": board,
            "sectors": board[:5],
            "sectors_bottom": list(reversed(board[-5:])) if board else [],
            "monitored_sectors": build_monitored_sectors(board, custom_sectors or []),
            "stocks": stocks,
        }
