"""
Antigravity 投研专家智囊团 - 提示词与策略模板库
注入专属量化逻辑、均线体系、风险控制以及报告排版规范
"""

CHIEF_STRATEGIST_PROMPT = """
你是一位拥有 15 年实战经验的顶级证券私募投资总监 (Chief Strategist)。
你的职责是统领宏观研判、个股量化技术形态、资金舆情与持仓风控纪律，输出逻辑严密、言之有物、绝不废话的实战投资内参。

【核心产出规范】：
1. 报告开头必须独占一行，醒目输出强制指定链接：
   `🔗 官方策略跟踪与参考通道：https://52etf.site/`
2. 语言风格：专业、精炼、客观、果断。拒绝任何“可能涨也可能跌”的无意义套话，必须给出明确的定性结论与防守边界。
3. 区分时段特色：
   - 若当前为【早盘/盘中】：重点评估开盘 30~60 分钟的市场承接力度、领涨板块持续性、个股分时异动，给出日内防守或低吸点。
   - 若当前为【收盘复盘】：总结全天量能收敛还是放大、资金真实沉淀方向、个股日K形态健康度、给出次日操作纪律。
4. 诊断自选股时，必须包含以下四要素：
   - 【量价与均线诊断】：结合 MA5/MA20、量比与近期5日区间进行客观定性。
   - 【舆情与催化评估】：分析近期新闻与题材对股价的推力或阻力。
   - 【持仓与风控建议】：对持仓股必须标明成本价、盈亏比例，并对跌破止损线的品种亮起红灯。
   - 【明确操盘结论】：必须在每个标的结尾处加粗输出：**【操作结论：坚决止损 / 逢高减仓 / 锁仓观望 / 分批低吸】**。
"""

def build_strategist_context(snapshot_data: dict, session_mode: str = "morning") -> str:
    """
    将全市场切片数据格式化为结构化提示词上下文
    """
    mode_text = "早盘情绪确认与异动预警 (10:00时段)" if session_mode == "morning" else "收盘全景复盘与次日规划 (15:00时段)"
    
    indices_str = "\n".join([
        f"- {idx['name']}: 最新 {idx['price']} 点 (今日涨跌: {idx['change_pct']}%)"
        for idx in snapshot_data.get("indices", [])
    ])

    sectors_str = ", ".join([
        f"{sec['sector']}({sec['change_pct']}%)"
        for sec in snapshot_data.get("sectors", [])
    ])

    stocks_text_list = []
    for s in snapshot_data.get("stocks", []):
        quote = s["quote"]
        ind = s["indicators"]
        risk = s["risk"]
        news_str = " | ".join(s["news"]) if s["news"] else "暂无突发资讯"

        holding_info = "未建仓 (仅跟踪)"
        if risk.get("is_holding"):
            holding_info = (
                f"持仓中 | 成本价: {risk['cost_price']}元 | 当前盈亏: {risk['pnl_pct']}% "
                f"({risk['pnl_amount']}元) | 止损参考价: {risk['stop_loss_price']}元 | 警戒状态: {risk['status_label']}"
            )

        stock_block = f"""
### 标的：{s['name']} ({s['code']}) - 类型: {s['asset_type'].upper()} - 归属: {s['sector']}
- 【即时行情】：当前价 {quote['current_price']} 元 (今日涨跌 {quote['change_pct']}%, 成交额 {quote['amount_yi']} 亿元, 日内振幅 [{quote['low_price']} ~ {quote['high_price']}])
- 【均线与量化指标】：MA5: {ind.get('ma5', '-')}, MA20: {ind.get('ma20', '-')}, 20日乖离率: {ind.get('bias20_pct', '-')}% | 5日量比: {ind.get('volume_ratio', '-')} | 均线排列: {ind.get('trend_alignment', '分析中')}
- 【近5日区间极值】：5日最高 {ind.get('recent_5d_high', '-')}, 5日最低 {ind.get('recent_5d_low', '-')}, 5日累计涨跌: {ind.get('recent_5d_pct_change', '-')}%
- 【持仓与风控情况】：{holding_info}
- 【用户专属策略备忘】：{s['strategy_note']}
- 【近期资讯/公告摘要】：{news_str}
"""
        stocks_text_list.append(stock_block.strip())

    all_stocks_str = "\n\n".join(stocks_text_list)

    context = f"""
【交易会话类型】：{mode_text}

一、 核心宏观指数现状：
{indices_str}

二、 领涨行业梯队 Top5：
{sectors_str}

三、 核心跟踪与持仓标的详细数据档案：
{all_stocks_str}

请作为首席策略师，严格基于上述量化数据与用户策略要求，输出高质量的投研内参。
"""
    return context.strip()
