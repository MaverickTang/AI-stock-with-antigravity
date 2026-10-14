"""
Antigravity Generative UI 投研看板生成器
符合中国 A 股交易红涨绿跌习惯，生成高颜值金融投研 Artifact
"""
import os
import html
from datetime import datetime
from typing import Dict, Any

class HtmlDashboardGenerator:
    def __init__(self, output_dir: str = "reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, analysis_result: Dict[str, Any], save_path: str = None) -> str:
        snapshot = analysis_result.get("snapshot", {})
        session_title = analysis_result.get("session_title", "投研内参")
        report_md = analysis_result.get("report_markdown", "")
        mandatory_link = analysis_result.get("mandatory_link", "https://52etf.site/")
        indices = snapshot.get("indices", [])
        sectors = snapshot.get("sectors", [])
        monitored_sectors = snapshot.get("monitored_sectors", [])
        stocks = snapshot.get("stocks", [])
        now_str = analysis_result.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. 构建指数卡片 (红涨绿跌)
        index_cards_html = ""
        for idx in indices:
            is_up = idx["change_pct"] >= 0
            color_class = "text-rose-500" if is_up else "text-emerald-500"
            bg_badge = "bg-rose-500/10" if is_up else "bg-emerald-500/10"
            sign = "+" if is_up else ""
            index_cards_html += f"""
            <div class="p-4 rounded-xl border border-[var(--border)] bg-[var(--card)] flex flex-col justify-between shadow-sm">
                <div class="flex justify-between items-center mb-2">
                    <span class="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider">{idx['name']}</span>
                    <span class="text-xs px-2 py-0.5 rounded-full font-bold {color_class} {bg_badge}">{sign}{idx['change_pct']}%</span>
                </div>
                <div class="text-2xl font-black {color_class}">{idx['price']}</div>
            </div>
            """

        # 2. 构建领涨行业与重点关注板块 (红涨绿跌)
        sector_pills_html = ""
        display_sectors = monitored_sectors if monitored_sectors else sectors
        for sec in display_sectors:
            chg = sec.get("change_pct", 0.0)
            is_up = chg >= 0
            color_class = "text-rose-500" if is_up else "text-emerald-500"
            sign = "+" if is_up else ""
            sec_name = sec.get("name") or sec.get("sector", "")
            sector_pills_html += f"""
            <div class="flex items-center justify-between px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                <span class="text-xs font-medium text-[var(--foreground)]">{sec_name}</span>
                <span class="text-xs font-bold {color_class}">{sign}{chg}%</span>
            </div>
            """

        # 3. 构建自选股卡片 (红涨绿跌)
        stock_cards_html = ""
        for s in stocks:
            q = s["quote"]
            ind = s["indicators"]
            risk = s["risk"]
            is_up = q["change_pct"] >= 0
            price_color = "text-rose-500" if is_up else "text-emerald-500"
            sign = "+" if is_up else ""

            # 持仓风控徽标 (国内A股规范: 跌破止损标绿闪烁, 达止盈线标红提示)
            if risk.get("is_holding"):
                risk_lvl = risk.get("risk_level", "NORMAL")
                if risk_lvl == "CRITICAL":
                    risk_badge = '<span class="text-xs px-2.5 py-1 rounded-full font-bold bg-emerald-600 text-white animate-pulse shadow-lg shadow-emerald-500/50 ring-2 ring-emerald-400">🚨 跌破止损</span>'
                elif risk_lvl == "WARNING":
                    risk_badge = '<span class="text-xs px-2 py-0.5 rounded-full font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 animate-pulse">⚠️ 逼近止损</span>'
                elif risk_lvl == "PROFIT":
                    risk_badge = '<span class="text-xs px-2 py-0.5 rounded-full font-bold bg-rose-500/20 text-rose-400 border border-rose-500/40">🎉 达止盈线</span>'
                else:
                    risk_badge = '<span class="text-xs px-2 py-0.5 rounded-full font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20">持仓中 (安全)</span>'
                
                # 浮动盈亏颜色: 盈利为红，亏损为绿
                pnl = risk.get("pnl_pct", 0.0)
                pnl_color = "text-rose-500" if pnl >= 0 else "text-emerald-500"
                pnl_sign = "+" if pnl >= 0 else ""
                holding_box = f"""
                <div class="mt-3 pt-3 border-t border-[var(--border)] grid grid-cols-3 gap-2 text-xs">
                    <div><span class="text-[var(--muted-foreground)]">成本:</span> <span class="font-semibold text-[var(--foreground)]">{risk['cost_price']}元</span></div>
                    <div><span class="text-[var(--muted-foreground)]">浮动:</span> <span class="font-bold {pnl_color}">{pnl_sign}{pnl}%</span></div>
                    <div><span class="text-[var(--muted-foreground)]">止损价:</span> <span class="font-semibold text-emerald-500">{risk['stop_loss_price']}元</span></div>
                </div>
                """
            else:
                risk_badge = '<span class="text-xs px-2 py-0.5 rounded-full font-medium bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">自选观察</span>'
                holding_box = '<div class="mt-3 pt-2 border-t border-[var(--border)] text-xs text-[var(--muted-foreground)]">观察仓位 (未建仓)</div>'

            stock_cards_html += f"""
            <div class="p-4 rounded-xl border border-[var(--border)] bg-[var(--card)] shadow-sm flex flex-col justify-between">
                <div>
                    <div class="flex justify-between items-start mb-2">
                        <div>
                            <div class="flex items-center gap-2">
                                <h4 class="text-sm font-bold text-[var(--foreground)]">{s['name']}</h4>
                                <span class="text-xs px-1.5 py-0.5 rounded bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)] font-mono">{s['code']}</span>
                            </div>
                            <span class="text-xs text-[var(--muted-foreground)]">{s['sector']}</span>
                        </div>
                        {risk_badge}
                    </div>

                    <div class="flex items-baseline gap-3 my-2">
                        <span class="text-2xl font-black {price_color}">{q['current_price']}</span>
                        <span class="text-sm font-bold {price_color}">{sign}{q['change_pct']}%</span>
                        <span class="text-xs text-[var(--muted-foreground)] font-mono">额: {q['amount_yi']}亿</span>
                    </div>

                    <div class="grid grid-cols-2 gap-2 text-xs bg-[var(--background)] p-2.5 rounded-lg border border-[var(--border)]">
                        <div><span class="text-[var(--muted-foreground)]">MA5:</span> <span class="font-mono text-[var(--foreground)]">{ind.get('ma5', '-')}</span></div>
                        <div><span class="text-[var(--muted-foreground)]">MA20:</span> <span class="font-mono text-[var(--foreground)]">{ind.get('ma20', '-')}</span></div>
                        <div class="col-span-2"><span class="text-[var(--muted-foreground)]">趋势:</span> <span class="font-medium text-[var(--foreground)]">{ind.get('trend_alignment', '-')}</span></div>
                    </div>
                </div>

                {holding_box}
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Antigravity 智能投研内参</title>
    <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-[var(--background)] text-[var(--foreground)] p-4 md:p-6 min-h-screen font-sans antialiased text-xs md:text-sm">
    <div class="max-w-6xl mx-auto space-y-6">
        
        <!-- 头部 Header -->
        <header class="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-[var(--border)] gap-3">
            <div>
                <div class="flex items-center gap-2">
                    <span class="p-1.5 rounded-lg bg-[var(--primary)] text-[var(--primary-foreground)] font-bold text-sm">AGY</span>
                    <h1 class="text-lg md:text-xl font-bold tracking-tight text-[var(--foreground)]">Antigravity AI 股票投研智能内参</h1>
                    <span class="text-xs px-2.5 py-1 rounded-full font-semibold bg-[var(--primary)]/10 text-[var(--primary)] border border-[var(--primary)]/20">{session_title}</span>
                </div>
                <p class="text-xs text-[var(--muted-foreground)] mt-1">
                    生成时间: <span class="font-mono">{now_str}</span> | 投研引擎: <span class="font-medium text-[var(--foreground)]">Antigravity Native Pod</span> (遵循中国国内红涨绿跌习惯)
                </p>
            </div>
            <div>
                <a href="{mandatory_link}" target="_blank" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--card)] hover:bg-[var(--border)] border border-[var(--border)] text-xs font-medium text-[var(--foreground)] transition-colors">
                    <span>🔗 策略与ETF参考通道</span>
                    <span class="text-[var(--primary)] font-bold font-mono">52etf.site</span>
                </a>
            </div>
        </header>

        <!-- 第一部分：大盘指数卡片 (红涨绿跌) -->
        <section class="space-y-2">
            <h2 class="text-xs font-bold text-[var(--muted-foreground)] uppercase tracking-wider">大盘核心指数 (红涨绿跌)</h2>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                {index_cards_html}
            </div>
        </section>

        <!-- 第二部分：领涨与重点板块 -->
        <section class="space-y-2">
            <h2 class="text-xs font-bold text-[var(--muted-foreground)] uppercase tracking-wider">重点跟踪与领涨行业板块</h2>
            <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                {sector_pills_html}
            </div>
        </section>

        <!-- 第三部分：自选股与持仓风控雷达 -->
        <section class="space-y-2">
            <div class="flex justify-between items-center">
                <h2 class="text-xs font-bold text-[var(--muted-foreground)] uppercase tracking-wider">自选跟踪与持仓风控雷达</h2>
                <span class="text-xs text-[var(--muted-foreground)]">实时量化扫描</span>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                {stock_cards_html}
            </div>
        </section>

        <!-- 第四部分：决策报告 -->
        <section class="p-5 rounded-2xl border border-[var(--border)] bg-[var(--card)] shadow-sm space-y-4">
            <div class="flex items-center justify-between pb-3 border-b border-[var(--border)]">
                <div class="flex items-center gap-2">
                    <span class="text-base">🧠</span>
                    <h2 class="text-sm md:text-base font-bold text-[var(--foreground)]">Antigravity 首席策略师实战研报</h2>
                </div>
                <span class="text-xs text-[var(--muted-foreground)]">Native Engine</span>
            </div>
            <div class="prose max-w-none text-xs md:text-sm text-[var(--foreground)] leading-relaxed whitespace-pre-wrap font-sans">
{report_md}
            </div>
        </section>

        <!-- 页脚声明 -->
        <footer class="pt-4 text-center text-xs text-[var(--muted-foreground)] border-t border-[var(--border)]">
            Antigravity Quantitative Investment Pod &bull; 决策仅供技术参考，据此交易风险自负 &bull; <a href="{mandatory_link}" class="underline text-[var(--primary)]">{mandatory_link}</a>
        </footer>
    </div>
</body>
</html>
"""
        if not save_path:
            file_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dashboard_{file_timestamp}.html"
            save_path = os.path.join(self.output_dir, filename)

        with open(save_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return save_path
