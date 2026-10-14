"""
Antigravity 投研控制台本地 Web 服务
支持中国 A 股红涨绿跌、仅输代码自动补齐、标的与板块子页面下钻、
持仓在线编辑即改即存、提示词与私有材料库 (materials/) 管理、周期研报切换。
"""
import os
import re
import json
import yaml
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Dict, Any

from app_paths import (
    SETTINGS_PATH, WATCHLIST_PATH, PROMPT_PATH, MATERIALS_DIR,
    REPORTS_DIR, HISTORY_DIR, PERIODIC_DIR, WEB_TEMPLATE, LATEST_RESULT_PATH
)
from agents.research_pod import StockResearchPod, detect_periodic_type, detect_periodic_meta
from data_engine.fetcher import MarketDataEngine
from data_engine.indicators import calculate_position_risk
from agents.quant_analyst import analyze_stock, PRIORITY_LABEL
from reporting.markdown_reporter import MarkdownReporter
from reporting.html_dashboard import HtmlDashboardGenerator
from knowledge.store import (
    load_prompt, save_prompt, list_materials, read_material, save_material, delete_material
)

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class WebServerState:
    def __init__(self):
        self.pod = StockResearchPod()
        self.md_reporter = MarkdownReporter(output_dir=REPORTS_DIR)
        self.html_generator = HtmlDashboardGenerator(output_dir=REPORTS_DIR)
        
        self.latest_result = None
        self.last_analysis_time = None
        self._load_or_run_initial()

    def _load_or_run_initial(self):
        # 优先从 latest.json 恢复，避免每次启动必须耗时重新抓取
        if os.path.exists(LATEST_RESULT_PATH):
            try:
                with open(LATEST_RESULT_PATH, "r", encoding="utf-8") as f:
                    self.latest_result = json.load(f)
                    self.last_analysis_time = self.latest_result.get("generated_at")
                    print("✅ [Web Server] 从缓存成功载入最新市场切片！")
                    return
            except Exception:
                pass

        try:
            print("🚀 [Web Server] 正在初始化运行初次市场分析...")
            self.run_analysis(mode="morning")
        except Exception as e:
            print(f"⚠️ [Web Server] 初始分析加载异常: {e}")

    def run_analysis(self, mode="morning"):
        res = self.pod.run_analysis(session_mode=mode)
        self.latest_result = res
        self.last_analysis_time = res.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.md_reporter.generate_and_save(res)
        self.html_generator.generate(res)
        return res

state = WebServerState()

class StockWebRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            if os.path.exists(WEB_TEMPLATE):
                with open(WEB_TEMPLATE, "r", encoding="utf-8") as f:
                    html_content = f.read()
                body = html_content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404, "Template index.html Not Found")
            return

        if path == "/api/status":
            with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
                wl_data = yaml.safe_load(f) or {}

            detected_periodic = detect_periodic_type()
            periodic_meta = detect_periodic_meta()
            catalog = state.pod.get_reports_catalog()

            response_data = {
                "status": "ok",
                "last_analysis_time": state.last_analysis_time,
                "latest_result": state.latest_result,
                "watchlist": wl_data.get("watchlist", []),
                "sectors": wl_data.get("sectors", []),
                "detected_periodic": detected_periodic,
                "periodic_meta": periodic_meta,
                "reports_catalog": catalog,
                "prompt": load_prompt(),
                "materials": list_materials(),
                "mandatory_link": state.pod.settings.get("report", {}).get("mandatory_link", "https://52etf.site/")
            }
            self._send_json(response_data)
            return

        if path == "/api/prompt":
            self._send_json({"status": "ok", "prompt": load_prompt()})
            return

        if path == "/api/materials":
            self._send_json({"status": "ok", "materials": list_materials()})
            return

        if path == "/api/reports":
            catalog = state.pod.get_reports_catalog()
            self._send_json({
                "status": "ok",
                "catalog": catalog,
                "periodic_meta": detect_periodic_meta()
            })
            return

        if path == "/api/periodic/info":
            self._send_json({
                "status": "ok",
                "periodic_meta": detect_periodic_meta()
            })
            return

        self.send_error(404, "API Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_length)

        try:
            payload = json.loads(post_body.decode("utf-8")) if post_body else {}
        except Exception:
            payload = {}

        # ----------------------------------------------------------
        # 1. 股票管理 API
        # ----------------------------------------------------------
        if path == "/api/stock/add":
            # 极简改造：仅需输入纯数字代码，后端自动推导与补齐全量元数据并持久化
            raw_code = str(payload.get("code", "")).strip()
            # 剥离可能误输入的市场前缀 (如 sh600519 -> 600519)
            code = re.sub(r"^(sh|sz|bj)", "", raw_code, flags=re.I).strip()

            if not code or not code.isdigit() or len(code) != 6:
                self._send_json({
                    "status": "error",
                    "message": "请输入6位纯数字股票/ETF代码 (如 600519 或 159915)"
                }, status=400)
                return

            state.pod.reload_config()
            wl = state.pod.watchlist_cfg.get("watchlist", [])
            if any(s.get("code") == code for s in wl):
                self._send_json({
                    "status": "error",
                    "message": f"代码 {code} 已在自选股列表中，无需重复添加"
                }, status=400)
                return

            # 后端自动推导与补齐：
            # 1. 资产类型：以 51、58、15、16 开头识别为 ETF，其余识别为普通 A股；
            # 2. 实时官方名称：通过毫秒级行情接口在 0.1 秒内自动抓取；
            # 3. 板块与默认结构：自动填充所属行业，初始化默认仓位 (未建仓、止损预设 6%)。
            enriched = state.pod.engine.enrich_stock_metadata(code, payload)
            wl.append(enriched)

            # 持久化回写至 config/watchlist.yaml
            saved = state.pod.save_watchlist_config(wl, state.pod.watchlist_cfg.get("sectors", []))
            if not saved:
                self._send_json({"status": "error", "message": "保存至 config/watchlist.yaml 失败"}, status=500)
                return

            # 同步更新当前运行内存中的切片数据，让前端即时渲染雷达卡片
            if state.latest_result and isinstance(state.latest_result.get("snapshot"), dict):
                stocks_list = state.latest_result["snapshot"].setdefault("stocks", [])
                if not any(s.get("code") == code for s in stocks_list):
                    quotes_map = state.pod.engine.get_realtime_quotes([code])
                    q = quotes_map.get(code, {
                        "code": code, "name": enriched["name"], "current_price": 0.0,
                        "change_pct": 0.0, "amount_yi": 0.0, "datetime": "-"
                    })
                    stocks_list.append({
                        "code": code,
                        "name": enriched["name"],
                        "asset_type": enriched["asset_type"],
                        "sector": enriched["sector"],
                        "quote": q,
                        "indicators": {"ma5": "-", "ma20": "-", "trend_alignment": "观察中"},
                        "risk": {
                            "is_holding": False,
                            "cost_price": 0.0,
                            "shares": 0,
                            "stop_loss_pct": 6.0,
                            "take_profit_pct": 15.0,
                            "risk_level": "SAFE"
                        },
                        "news": [],
                        "strategy_note": enriched["strategy_note"]
                    })

            asset_name = "ETF" if enriched["asset_type"] == "etf" else "普通 A股"
            self._send_json({
                "status": "success",
                "message": f"成功添加标的：{enriched['name']} ({code}) · {asset_name} · {enriched['sector']}",
                "stock": enriched,
                "watchlist": wl
            })
            return

        if path == "/api/stock/update":
            # 在专属抽屉子页面修改持仓风控或战法备忘，即时持久化并重新核算盈亏
            code = str(payload.get("code", "")).strip()
            if not code:
                self._send_json({"status": "error", "message": "代码缺失"}, status=400)
                return

            state.pod.reload_config()
            wl = state.pod.watchlist_cfg.get("watchlist", [])
            target_stock = None
            for s in wl:
                if s["code"] == code:
                    if "holding" in payload:
                        s["holding"] = payload["holding"]
                    if "strategy_note" in payload:
                        s["strategy_note"] = payload["strategy_note"]
                    if "sector" in payload:
                        s["sector"] = payload["sector"]
                    target_stock = s
                    break

            if target_stock:
                # 1. 持久化至 config/watchlist.yaml
                state.pod.save_watchlist_config(wl, state.pod.watchlist_cfg.get("sectors", []))

                # 2. 同步运行切片缓存并即时重新核算盈亏与AI研判
                updated_entry = None
                updated_risk = None
                updated_analysis = None

                if state.latest_result and isinstance(state.latest_result.get("snapshot"), dict):
                    stocks_list = state.latest_result["snapshot"].setdefault("stocks", [])
                    matched = next((item for item in stocks_list if item.get("code") == code), None)
                    if matched:
                        if "holding" in payload:
                            matched["holding"] = target_stock["holding"]
                        if "strategy_note" in payload:
                            matched["strategy_note"] = target_stock["strategy_note"]
                        if "sector" in payload:
                            matched["sector"] = target_stock["sector"]

                        # 重新核算当前盈亏与风控水位
                        curr_p = matched.get("quote", {}).get("current_price", 0.0)
                        updated_risk = calculate_position_risk(matched.get("holding", {}), curr_p)
                        matched["risk"] = updated_risk

                        # 重新计算该标的量化诊断与独立买卖建议
                        monitored = state.latest_result["snapshot"].get("monitored_sectors", [])
                        updated_analysis = analyze_stock(matched, monitored)
                        if "stocks" not in state.latest_result.setdefault("analysis", {}):
                            state.latest_result["analysis"]["stocks"] = {}
                        state.latest_result["analysis"]["stocks"][code] = updated_analysis

                        # 同步刷新纪律清单
                        discipline = []
                        for st in stocks_list:
                            sc = st.get("code")
                            sa = state.latest_result["analysis"]["stocks"].get(sc)
                            if sa:
                                cond = sa["actions"][0] if sa.get("actions") else sa.get("decision", "")
                                discipline.append({
                                    "priority": sa.get("priority", 9),
                                    "label": PRIORITY_LABEL.get(sa.get("priority", 9), "⚪"),
                                    "code": sc, "name": st.get("name"),
                                    "decision": sa.get("decision", ""),
                                    "level": sa.get("level", "watch"),
                                    "condition": cond
                                })
                        discipline.sort(key=lambda x: x["priority"])
                        state.latest_result["analysis"]["discipline"] = discipline

                        updated_entry = matched

                self._send_json({
                    "status": "success",
                    "message": f"标的 {code} 仓位与策略已更新，即时核算完成并持久化保存！",
                    "stock": updated_entry or target_stock,
                    "risk": updated_risk,
                    "analysis": updated_analysis,
                    "watchlist": wl
                })
            else:
                self._send_json({"status": "error", "message": "未找到对应标的"}, status=404)
            return

        if path == "/api/stock/delete":
            code = str(payload.get("code", "")).strip()
            state.pod.reload_config()
            wl = [s for s in state.pod.watchlist_cfg.get("watchlist", []) if s["code"] != code]
            state.pod.save_watchlist_config(wl, state.pod.watchlist_cfg.get("sectors", []))

            # 同步更新运行切片缓存
            if state.latest_result and isinstance(state.latest_result.get("snapshot"), dict):
                stocks_list = state.latest_result["snapshot"].get("stocks", [])
                state.latest_result["snapshot"]["stocks"] = [s for s in stocks_list if s.get("code") != code]

            self._send_json({"status": "success", "message": f"标的 {code} 已从自选股中移除并同步至配置文件"})
            return

        if path == "/api/watchlist":
            # 批量持久化保存自选股与板块
            state.pod.reload_config()
            new_wl = payload.get("watchlist")
            new_sec = payload.get("sectors")
            current_wl = state.pod.watchlist_cfg.get("watchlist", []) if new_wl is None else new_wl
            current_sec = state.pod.watchlist_cfg.get("sectors", []) if new_sec is None else new_sec

            for i, it in enumerate(current_wl):
                if MarketDataEngine.needs_enrich(it):
                    current_wl[i] = state.pod.engine.enrich_stock_metadata(it.get("code", ""), it)

            saved = state.pod.save_watchlist_config(current_wl, current_sec)
            if saved:
                self._send_json({"status": "success", "message": "自选配置已成功持久化回写至 config/watchlist.yaml！"})
            else:
                self._send_json({"status": "error", "message": "保存配置文件失败"}, status=500)
            return

        # ----------------------------------------------------------
        # 2. 板块管理 API
        # ----------------------------------------------------------
        if path == "/api/sector/add":
            name = str(payload.get("name", "")).strip()
            if not name:
                self._send_json({"status": "error", "message": "板块名称不能为空"}, status=400)
                return
            sectors = state.pod.watchlist_cfg.get("sectors", [])
            if any(sec["name"] == name for sec in sectors):
                self._send_json({"status": "error", "message": "该板块已存在"}, status=400)
                return
            sectors.append({"name": name, "focus_note": payload.get("focus_note", "")})
            state.pod.save_watchlist_config(state.pod.watchlist_cfg.get("watchlist", []), sectors)
            self._send_json({"status": "success", "message": f"已添加板块：{name}"})
            return

        if path == "/api/sector/update":
            name = str(payload.get("name", "")).strip()
            focus_note = payload.get("focus_note", "")
            if not name:
                self._send_json({"status": "error", "message": "板块名称不能为空"}, status=400)
                return

            state.pod.reload_config()
            sectors = state.pod.watchlist_cfg.get("sectors", [])
            found = False
            for sec in sectors:
                if sec.get("name") == name:
                    sec["focus_note"] = focus_note
                    found = True
                    break
            if not found:
                sectors.append({"name": name, "focus_note": focus_note})

            state.pod.save_watchlist_config(state.pod.watchlist_cfg.get("watchlist", []), sectors)

            # 同步更新运行切片缓存
            if state.latest_result and isinstance(state.latest_result.get("snapshot"), dict):
                monitored = state.latest_result["snapshot"].setdefault("monitored_sectors", [])
                m_sec = next((s for s in monitored if s.get("name") == name or s.get("sector") == name), None)
                if m_sec:
                    m_sec["focus_note"] = focus_note
                else:
                    monitored.append({"name": name, "focus_note": focus_note, "change_pct": 0.0, "net_yi": 0.0})

                if "sectors" in state.latest_result.get("analysis", {}):
                    if name in state.latest_result["analysis"]["sectors"]:
                        pts = state.latest_result["analysis"]["sectors"][name].get("points", [])
                        # 更新 points 中的我的观察逻辑
                        new_pts = [p for p in pts if not p.startswith("我的观察逻辑：")]
                        if focus_note:
                            new_pts.append(f"我的观察逻辑：{focus_note}")
                        state.latest_result["analysis"]["sectors"][name]["points"] = new_pts

            self._send_json({
                "status": "success",
                "message": f"板块【{name}】专属备忘已保存并持久化至 watchlist.yaml！",
                "name": name,
                "focus_note": focus_note,
                "sectors": sectors
            })
            return

        if path == "/api/sector/delete":
            name = str(payload.get("name", "")).strip()
            sectors = [sec for sec in state.pod.watchlist_cfg.get("sectors", []) if sec["name"] != name]
            state.pod.save_watchlist_config(state.pod.watchlist_cfg.get("watchlist", []), sectors)
            self._send_json({"status": "success", "message": f"板块 {name} 已移除"})
            return

        # ----------------------------------------------------------
        # 3. 提示词与材料库 API
        # ----------------------------------------------------------
        if path == "/api/prompt":
            new_prompt = payload.get("prompt", "")
            save_prompt(new_prompt)
            self._send_json({"status": "success", "message": "分析提示词已成功保存！"})
            return

        if path == "/api/materials/read":
            fn = payload.get("filename", "")
            try:
                content = read_material(fn)
                self._send_json({"status": "success", "filename": fn, "content": content})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=500)
            return

        if path == "/api/materials/save":
            fn = payload.get("filename", "")
            content = payload.get("content", "")
            try:
                saved_fn = save_material(fn, content)
                self._send_json({"status": "success", "message": f"材料文件 {saved_fn} 已保存！", "filename": saved_fn})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=500)
            return

        if path == "/api/materials/delete":
            fn = payload.get("filename", "")
            try:
                delete_material(fn)
                self._send_json({"status": "success", "message": f"材料 {fn} 已删除"})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=500)
            return

        # ----------------------------------------------------------
        # 4. 周期报告与历史回溯 API
        # ----------------------------------------------------------
        if path == "/api/reports/load":
            filename = payload.get("filename")
            period = payload.get("period")
            target_path = None

            if filename:
                for folder in (PERIODIC_DIR, HISTORY_DIR, REPORTS_DIR):
                    p = os.path.join(folder, filename)
                    if os.path.exists(p) and os.path.isfile(p):
                        target_path = p
                        break
            elif period:
                # 寻找该周期的最新报告
                p_latest = os.path.join(PERIODIC_DIR, f"{period}_latest.json")
                if os.path.exists(p_latest):
                    target_path = p_latest
                else:
                    catalog = state.pod.get_reports_catalog()
                    items = catalog.get(period, [])
                    if items:
                        fn = items[0]["filename"]
                        for folder in (PERIODIC_DIR, HISTORY_DIR):
                            p = os.path.join(folder, fn)
                            if os.path.exists(p):
                                target_path = p
                                break

            if target_path and os.path.exists(target_path):
                try:
                    with open(target_path, "r", encoding="utf-8") as f:
                        rep_data = json.load(f)
                    state.latest_result = rep_data
                    state.last_analysis_time = rep_data.get("generated_at") or rep_data.get("snapshot", {}).get("generated_at", "--")
                    self._send_json({
                        "status": "success",
                        "message": f"成功载入历史研报：{rep_data.get('session_title', os.path.basename(target_path))}",
                        "latest_result": rep_data,
                        "last_analysis_time": state.last_analysis_time,
                        "is_historical": True,
                        "filename": os.path.basename(target_path)
                    })
                    return
                except Exception as e:
                    self._send_json({"status": "error", "message": f"读取报告文件失败: {e}"}, status=500)
                    return
            else:
                self._send_json({
                    "status": "error",
                    "code": "REPORT_NOT_FOUND",
                    "message": f"未找到【{period or filename}】已归档的历史研报，可点击「立即分析」一键生成最新报告！"
                }, status=404)
                return

        # ----------------------------------------------------------
        # 5. 执行分析 API (支持早盘/午后/周报/月报/季报/智能嗅探)
        # ----------------------------------------------------------
        if path == "/api/analyze":
            session_mode = payload.get("mode", "morning")
            try:
                print(f"⚡ [Web API] 用户触发分析 (请求模式: {session_mode})...")
                res = state.run_analysis(mode=session_mode)
                catalog = state.pod.get_reports_catalog()
                self._send_json({
                    "status": "success",
                    "last_analysis_time": state.last_analysis_time,
                    "latest_result": res,
                    "reports_catalog": catalog,
                    "periodic_meta": detect_periodic_meta()
                })
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=500)
            return

        self.send_error(404, "API Not Found")

def start_server(host="127.0.0.1", port=8888):
    server = ThreadedHTTPServer((host, port), StockWebRequestHandler)
    print(f"\n=======================================================")
    print(f"🌟 Antigravity 股票投研 Web 控制台已启动!")
    print(f"👉 访问地址: http://{host}:{port}")
    print(f"=======================================================\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 正在停止 Web 服务...")
        server.server_close()

if __name__ == "__main__":
    start_server()
