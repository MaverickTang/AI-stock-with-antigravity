#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================
Antigravity AI 股票投研智能内参系统 (Main CLI & Web Engine)
全面整合 Google Antigravity 原生投研大脑、AKShare、持仓风控与 Web 控制台
====================================================================
"""
import os
import sys
import argparse
from datetime import datetime

from agents.research_pod import StockResearchPod
from reporting.markdown_reporter import MarkdownReporter
from reporting.html_dashboard import HtmlDashboardGenerator
from delivery.notifier import MessageNotifier

def run_analysis_cli(mode: str = "morning", custom_stocks: list = None, no_push: bool = False):
    pod = StockResearchPod()
    md_reporter = MarkdownReporter(output_dir="reports")
    html_generator = HtmlDashboardGenerator(output_dir="reports")
    notifier = MessageNotifier(pod.settings.get("delivery", {}))

    start_time = datetime.now()
    res = pod.run_analysis(session_mode=mode, custom_stocks=custom_stocks)

    md_file = md_reporter.generate_and_save(res)
    print(f"\n📄 [Markdown 研报已生成]: {md_file}")

    html_file = html_generator.generate(res)
    print(f"📊 [Generative UI 看板已生成]: {html_file}")

    print("\n" + "=" * 60)
    print(f"📈 【Antigravity 投研内参 - {mode.upper()} 报告预览】")
    print("=" * 60)
    print(res["report_markdown"])
    print("=" * 60)

    if not no_push:
        title = f"AI股票投研内参 ({mode.upper()}) - {start_time.strftime('%m-%d %H:%M')}"
        notifier.dispatch_all(title, res["report_markdown"])

    print("\n✨ 投研流水线执行完毕！")

def main():
    parser = argparse.ArgumentParser(description="Antigravity AI 股票投研智能内参系统")
    parser.add_argument(
        "--web",
        action="store_true",
        help="启动本地交互式 Web 控制台 (支持在浏览器管理自选股与板块)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8888,
        help="Web 控制台运行端口，默认 8888"
    )
    parser.add_argument(
        "--mode",
        choices=["morning", "afternoon", "close", "realtime"],
        default="morning",
        help="分析模式：morning (早盘10:00), afternoon (午后14:00)"
    )
    parser.add_argument(
        "--stock",
        nargs="+",
        help="仅分析指定股票或ETF代码，例如: --stock 603236 300059"
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="禁用外部微信/TG网络推送"
    )

    args = parser.parse_args()

    if args.web:
        from web.server import start_server
        start_server(host="127.0.0.1", port=args.port)
    else:
        # 兼容 close 映射为 afternoon
        session_mode = "afternoon" if args.mode in ["afternoon", "close"] else "morning"
        run_analysis_cli(mode=session_mode, custom_stocks=args.stock, no_push=args.no_push)

if __name__ == "__main__":
    main()