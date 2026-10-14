"""
Antigravity 投研控制台本地 Web 服务
支持中国 A 股红涨绿跌、仅输代码自动补齐、标的与板块子页面下钻、
持仓在线编辑即改即存、提示词与私有材料库 (materials/) 管理、周期研报切换。
"""
import os
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
from agents.research_pod import StockResearchPod, detect_periodic_type
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

            response_data = {
                "status": "ok",
                "last_analysis_time": state.last_analysis_time,
                "latest_result": state.latest_result,
                "watchlist": wl_data.get("watchlist", []),
                "sectors": wl_data.get("sectors", []),
                "detected_periodic": detected_periodic,
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
            # 返回历史与周期性研报列表
            periodic_files = []
            if os.path.exists(PERIODIC_DIR):
                for fn in sorted(os.listdir(PERIODIC_DIR), reverse=True):
                    if fn.endswith(".json"):
                        periodic_files.append(fn)
            self._send_json({"status": "ok", "periodic_reports": periodic_files})
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
            # 仅需输入纯代码，自动补齐
            code = str(payload.get("code", "")).strip()
            if not code:
                self._send_json({"status": "error", "message": "股票代码不能为空"}, status=400)
                return

            wl = state.pod.watchlist_cfg.get("watchlist", [])
            if any(s["code"] == code for s in wl):
                self._send_json({"status": "error", "message": f"代码 {code} 已在自选股列表中"}, status=400)
                return

            # 自动补全
            enriched = state.pod.engine.enrich_stock_metadata(code, payload)
            wl.append(enriched)
            state.pod.save_watchlist_config(wl, state.pod.watchlist_cfg.get("sectors", []))
            self._send_json({"status": "success", "message": f"成功添加标的：{enriched['name']}({code})", "stock": enriched})
            return

        if path == "/api/stock/update":
            # 在子页面直接修改并保存持仓与战法
            code = str(payload.get("code", "")).strip()
            if not code:
                self._send_json({"status": "error", "message": "代码缺失"}, status=400)
                return

            wl = state.pod.watchlist_cfg.get("watchlist", [])
            found = False
            for s in wl:
                if s["code"] == code:
                    if "holding" in payload:
                        s["holding"] = payload["holding"]
                    if "strategy_note" in payload:
                        s["strategy_note"] = payload["strategy_note"]
                    if "sector" in payload:
                        s["sector"] = payload["sector"]
                    found = True
                    break

            if found:
                state.pod.save_watchlist_config(wl, state.pod.watchlist_cfg.get("sectors", []))
                self._send_json({"status": "success", "message": f"标的 {code} 仓位与策略已更新！"})
            else:
                self._send_json({"status": "error", "message": "未找到对应标的"}, status=404)
            return

        if path == "/api/stock/delete":
            code = str(payload.get("code", "")).strip()
            wl = [s for s in state.pod.watchlist_cfg.get("watchlist", []) if s["code"] != code]
            state.pod.save_watchlist_config(wl, state.pod.watchlist_cfg.get("sectors", []))
            self._send_json({"status": "success", "message": f"标的 {code} 已移除"})
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
            sectors = state.pod.watchlist_cfg.get("sectors", [])
            for sec in sectors:
                if sec["name"] == name:
                    sec["focus_note"] = payload.get("focus_note", "")
                    break
            state.pod.save_watchlist_config(state.pod.watchlist_cfg.get("watchlist", []), sectors)
            self._send_json({"status": "success", "message": f"板块 {name} 备注已更新"})
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
        # 4. 执行分析 API (支持早盘/午后/周报/月报/季报)
        # ----------------------------------------------------------
        if path == "/api/analyze":
            session_mode = payload.get("mode", "morning")
            try:
                print(f"⚡ [Web API] 用户触发分析 (模式: {session_mode})...")
                res = state.run_analysis(mode=session_mode)
                self._send_json({
                    "status": "success",
                    "last_analysis_time": state.last_analysis_time,
                    "latest_result": res
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
