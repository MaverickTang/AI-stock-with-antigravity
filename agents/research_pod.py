"""
Antigravity 投研智囊团主编排器
整合数据抓取、量化指标计算、模块化规则诊断、私有战法材料注入与周期性研报生成
"""
import os
import json
import yaml
from datetime import datetime
from typing import Dict, Any, Optional, List

from app_paths import (
    SETTINGS_PATH, WATCHLIST_PATH, REPORTS_DIR, HISTORY_DIR,
    PERIODIC_DIR, LATEST_RESULT_PATH, AI_CONTEXT_PATH, ensure_dirs
)
from data_engine.fetcher import MarketDataEngine
from agents.quant_analyst import build_analysis, render_markdown
from knowledge.store import load_prompt, build_materials_context


def detect_periodic_type(dt: Optional[datetime] = None) -> Optional[str]:
    """根据日期自动嗅探是否为周期特别报告日"""
    dt = dt or datetime.now()
    month, day, weekday = dt.month, dt.day, dt.weekday()  # weekday: 0=Mon, 4=Fri, 6=Sun
    # 季度第一天
    if day == 1 and month in (1, 4, 7, 10):
        return "quarterly"
    # 每月第一天
    if day == 1:
        return "monthly"
    # 每周五 (若下午收盘)
    if weekday == 4:
        return "weekly"
    return None


SESSION_TITLES = {
    "morning": "早盘情绪确认与异动预警 (10:00)",
    "afternoon": "午后决战推演与次日防守 (14:00)",
    "weekly": "周度全景复盘与下周策略规划 (周五特刊)",
    "monthly": "月度宏观流动性与持仓健康体检 (月度特刊)",
    "quarterly": "季度宏观资产配置与核心逻辑重估 (季度特刊)",
}


class StockResearchPod:
    def __init__(self, settings_path: str = SETTINGS_PATH, watchlist_path: str = WATCHLIST_PATH):
        ensure_dirs()
        self.settings_path = settings_path
        self.watchlist_path = watchlist_path
        self.engine = MarketDataEngine()
        self.reload_config()

    def reload_config(self):
        """重新加载配置，若自选股有缺失字段则自动补齐并回写"""
        with open(self.settings_path, "r", encoding="utf-8") as f:
            self.settings = yaml.safe_load(f) or {}

        with open(self.watchlist_path, "r", encoding="utf-8") as f:
            self.watchlist_cfg = yaml.safe_load(f) or {}

        # 检查是否有未补齐元数据的股票条目
        changed = False
        wl = self.watchlist_cfg.get("watchlist", [])
        for i, item in enumerate(wl):
            if MarketDataEngine.needs_enrich(item):
                wl[i] = self.engine.enrich_stock_metadata(item.get("code", ""), item)
                changed = True

        if changed:
            self.save_watchlist_config(wl, self.watchlist_cfg.get("sectors", []))

    def save_watchlist_config(self, new_watchlist: List[Dict[str, Any]], new_sectors: List[Dict[str, Any]]) -> bool:
        """持久化保存自选股与板块设置"""
        try:
            data_to_save = {
                "watchlist": new_watchlist,
                "sectors": new_sectors
            }
            with open(self.watchlist_path, "w", encoding="utf-8") as f:
                yaml.dump(data_to_save, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            self.watchlist_cfg = data_to_save
            return True
        except Exception as e:
            print(f"❌ 保存自选股配置异常: {e}")
            return False

    def run_analysis(self, session_mode: str = "morning", custom_stocks: Optional[list] = None) -> Dict[str, Any]:
        """
        执行一键投研分析流水线
        session_mode: morning | afternoon | weekly | monthly | quarterly
        """
        self.reload_config()
        title = SESSION_TITLES.get(session_mode, f"投研内参 ({session_mode})")
        print(f"\n🚀 [Antigravity 原生投研引擎] - 模式: {title} - 正在抓取市场切片...")

        target_watchlist = self.watchlist_cfg.get("watchlist", [])
        if custom_stocks:
            target_watchlist = [s for s in target_watchlist if s["code"] in custom_stocks]
            if not target_watchlist:
                target_watchlist = [self.engine.enrich_stock_metadata(c) for c in custom_stocks]

        custom_sectors = self.watchlist_cfg.get("sectors", [])

        # 1. 抓取全市场与自选股切片
        snapshot = self.engine.collect_full_market_snapshot(target_watchlist, custom_sectors=custom_sectors)

        # 2. 运行量化规则诊断 (本地秒级生成模块化结果)
        analysis = build_analysis(snapshot)

        # 3. 装配私有研报材料与提示词上下文
        materials_text = build_materials_context()
        custom_prompt = load_prompt()

        result = {
            "session_mode": session_mode,
            "session_title": title,
            "generated_at": snapshot.get("generated_at"),
            "mandatory_link": self.settings.get("report", {}).get("mandatory_link", "https://52etf.site/"),
            "snapshot": snapshot,
            "analysis": analysis,
            "prompt": custom_prompt,
            "materials_summary": f"已挂载私有材料库 (共 {len(materials_text)} 字符)",
        }

        # 4. 生成 Markdown 渲染文本 (兼容旧接口并用于推送与归档)
        result["report_markdown"] = render_markdown(result)

        # 5. 持久化缓存最新结果
        self._archive_result(result)
        return result

    def _archive_result(self, result: Dict[str, Any]):
        """归档结果文件"""
        try:
            # 写入最新 json
            with open(LATEST_RESULT_PATH, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            # 写入历史归档
            mode = result.get("session_mode", "realtime")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            hist_path = os.path.join(HISTORY_DIR, f"{mode}_{ts}.json")
            with open(hist_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            # 若为周期性研报，额外保存一份在 periodic/ 目录
            if mode in ("weekly", "monthly", "quarterly"):
                period_path = os.path.join(PERIODIC_DIR, f"{mode}_{ts}.json")
                with open(period_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)

            # 导出 AI 上下文文档，供 Antigravity Scheduled Agent 定时直接调用
            with open(AI_CONTEXT_PATH, "w", encoding="utf-8") as f:
                f.write(result["report_markdown"])

        except Exception as e:
            print(f"⚠️ 归档报告异常: {e}")
