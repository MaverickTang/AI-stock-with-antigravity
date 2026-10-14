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
    """
    资产类型自动判定：
    以 51、58、15、16 开头自动识别为 ETF，其余识别为普通 A股
    """
    code_str = str(code).strip()
    if code_str.startswith(("51", "58", "15", "16")):
        return "etf"
    return "stock"


def infer_etf_sector(name: str, code: str = "") -> str:
    """根据 ETF 官方名称或代码智能推导所属板块/分类"""
    n = name or ""
    if any(k in n for k in ["半导体", "芯片", "集成电路"]):
        return "半导体芯片 / 科技成长"
    if any(k in n for k in ["恒生", "港股", "中概", "海外", "纳斯达克", "标普"]):
        return "港股科技 / 海外互联网"
    if any(k in n for k in ["创业板", "创成长", "创50"]):
        return "创业板 / 科技创新"
    if any(k in n for k in ["科创", "科创50", "科创100"]):
        return "科创板 / 硬科技"
    if any(k in n for k in ["沪深300", "300"]):
        return "核心资产 / 沪深300"
    if any(k in n for k in ["中证500", "500"]):
        return "中盘成长 / 中证500"
    if any(k in n for k in ["中证1000", "1000", "2000"]):
        return "小盘成长 / 中证1000"
    if any(k in n for k in ["红利", "低波", "价值"]):
        return "红利低波 / 价值防御"
    if any(k in n for k in ["证券", "券商", "非银", "金融科技"]):
        return "证券 / 互联网金融"
    if any(k in n for k in ["医药", "医疗", "创新药", "生物"]):
        return "医药生物 / 创新药"
    if any(k in n for k in ["新能源", "光伏", "电池", "储能", "碳中和"]):
        return "新能源 / 光伏储能"
    if any(k in n for k in ["白酒", "酒", "消费", "食品", "饮料"]):
        return "大消费 / 白酒食品"
    if any(k in n for k in ["军工", "国防", "航空", "航天"]):
        return "国防军工 / 高端装备"
    if any(k in n for k in ["有色", "黄金", "稀土", "矿业", "金属"]):
        return "有色金属 / 贵金属"
    if any(k in n for k in ["银行"]):
        return "大金融 / 银行"
    if any(k in n for k in ["通信", "5G", "算力", "通信设备"]):
        return "通信设备 / 算力基础设施"
    if any(k in n for k in ["AI", "人工智能", "计算机", "软件", "大数据"]):
        return "计算机 / 人工智能"
    if any(k in n for k in ["游戏", "传媒", "动漫", "影视"]):
        return "传媒娱乐 / 游戏"
    if any(k in n for k in ["地产", "房地产", "基建", "建筑"]):
        return "房地产 / 传统基建"
    if any(k in n for k in ["电力", "煤炭", "石油", "石化", "能源"]):
        return "能源动力 / 资源采掘"
    if any(k in n for k in ["汽车", "智能车"]):
        return "汽车制造 / 智能驾驶"
    return "指数ETF / 行业基金"


def infer_stock_sector(name: str, code: str = "") -> str:
    """备用股票板块推导 (当东财行业接口未返回时使用)"""
    n = name or ""
    if any(k in n for k in ["茅台", "五粮液", "汾酒", "泸州老窖", "酒"]):
        return "白酒 / 饮料制造"
    if any(k in n for k in ["东财", "财富", "证券", "中信", "华泰", "招商"]):
        return "证券 / 互联网金融"
    if any(k in n for k in ["通信", "移远", "中际", "新易盛", "天孚", "光迅"]):
        return "通信设备 / 光模块"
    if any(k in n for k in ["中芯", "华虹", "北方华创", "海光", "寒武纪", "微电子", "芯片"]):
        return "半导体 / 先进制程"
    if any(k in n for k in ["银行", "招商银行", "平安银行", "工商", "建设"]):
        return "大金融 / 银行"
    if any(k in n for k in ["宁德", "比亚迪", "隆基", "通威", "阳光电源"]):
        return "新能源 / 动力电池"
    if any(k in n for k in ["药", "生物", "恒瑞", "迈瑞", "药明"]):
        return "医药生物 / 创新医疗"
    return "A股制造业 / 综合"


def fast_fetch_name_and_sector(code: str, asset_type: str) -> Dict[str, str]:
    """
    通过行情接口在 0.1 秒级毫秒抓取官方名称，并自动填充所属行业
    """
    code_str = str(code).strip()
    sym = format_symbol_for_sina(code_str)
    official_name = ""
    sector = ""

    headers = {
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    # 1. 0.1秒级新浪行情接口直连
    try:
        url = f"https://hq.sinajs.cn/list={sym}"
        resp = requests.get(url, headers=headers, timeout=1.0)
        resp.encoding = "gbk"
        m = re.search(r'var hq_str_\w+="([^"]*)";', resp.text)
        if m and m.group(1):
            parts = m.group(1).split(",")
            if parts and parts[0]:
                official_name = parts[0].strip()
    except Exception:
        pass

    # 2. 腾讯行情接口备选 (若新浪返回空或失败)
    if not official_name:
        try:
            tx_url = f"http://qt.gtimg.cn/q={sym}"
            resp = requests.get(tx_url, headers=headers, timeout=1.0)
            resp.encoding = "gbk"
            if "~" in resp.text:
                parts = resp.text.split("~")
                if len(parts) > 1 and parts[1]:
                    official_name = parts[1].strip()
        except Exception:
            pass

    # 3. 所属行业自动推导与抓取
    if asset_type == "etf":
        sector = infer_etf_sector(official_name, code_str)
    else:
        # 普通 A 股：优先通过东方财富秒级行情接口获取官方所属行业 (f127)
        try:
            market_id = "1" if code_str.startswith(("6", "5", "9")) else "0"
            em_url = f"http://push2.eastmoney.com/api/qt/stock/get?invt=2&fltt=1&fields=f58,f127&secid={market_id}.{code_str}"
            resp = requests.get(em_url, headers=headers, timeout=1.0)
            if resp.status_code == 200:
                data = resp.json().get("data") or {}
                if not official_name and data.get("f58"):
                    official_name = str(data.get("f58")).strip()
                f127 = data.get("f127")
                if f127 and f127 not in ("-", "None", ""):
                    sector = str(f127).strip()
        except Exception:
            pass

        if not sector:
            sector = infer_stock_sector(official_name, code_str)

    return {
        "name": official_name or f"标的_{code_str}",
        "sector": sector or ("指数/行业ETF" if asset_type == "etf" else "A股"),
    }


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
        """
        极简添加改造核心：
        1. 资产类型自动判定：以 51、58、15、16 开头自动识别为 ETF，其余识别为普通 A股；
        2. 实时名称匹配：通过行情接口在 0.1 秒内自动抓取官方名称 (如 600519 自动识别为 贵州茅台)；
        3. 板块与默认结构：自动填充所属行业，初始化默认仓位 (默认未建仓、止损线预设 6%)。
        """
        code_str = str(code).strip()
        item = dict(existing_item or {})
        item["code"] = code_str

        # 1. 资产类型自动判定
        asset_type = infer_asset_type(code_str)
        item["asset_type"] = item.get("asset_type") or asset_type

        # 2. 实时名称与行业匹配 (0.1秒级高速行情接口)
        has_real_name = bool(item.get("name") and not str(item.get("name", "")).startswith("标的_"))
        has_real_sector = bool(item.get("sector") and item.get("sector") not in ("待补充 (可在详情页修改)", "行业ETF", "A股"))

        # 如果已有报价缓存且包含官方名称，优先使用
        if quote and quote.get("name"):
            item["name"] = quote["name"]
            has_real_name = True

        if not has_real_name or not has_real_sector:
            info = fast_fetch_name_and_sector(code_str, item["asset_type"])
            if not has_real_name:
                item["name"] = info["name"]
            if not has_real_sector:
                item["sector"] = info["sector"]

        item.setdefault("name", f"标的_{code_str}")
        if not item.get("sector"):
            item["sector"] = "指数ETF" if item["asset_type"] == "etf" else "A股"

        # 3. 初始化默认仓位 (默认未建仓、止损线预设 6.0%)
        h = item.get("holding") if isinstance(item.get("holding"), dict) else {}
        h.setdefault("is_holding", False)
        h.setdefault("cost_price", 0.0)
        h.setdefault("shares", 0)
        h.setdefault("stop_loss_pct", 6.0)
        h.setdefault("take_profit_pct", 15.0)
        item["holding"] = h

        # 4. 默认策略备忘结构
        if not item.get("strategy_note"):
            if item["asset_type"] == "etf":
                item["strategy_note"] = "指数ETF配置标的，顺势跟踪均线支撑，严格执行6%止损纪律。"
            else:
                item["strategy_note"] = "跟踪5日/20日均线支撑与量能异动，未建仓观察中，严格执行6%止损纪律。"

        return item

    @staticmethod
    def needs_enrich(item: Dict[str, Any]) -> bool:
        return (not item.get("name")
                or str(item.get("name", "")).startswith("标的_")
                or not item.get("asset_type")
                or not isinstance(item.get("holding"), dict)
                or "strategy_note" not in item
                or not item.get("sector")
                or item.get("sector") in ("待补充 (可在详情页修改)", "行业ETF", "A股"))

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
