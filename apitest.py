import os
import pandas as pd
import akshare as ak
from openai import OpenAI

# 强制清理代理环境变量
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

# =============== 配置区 ===============
# 将这里替换为你申请到的真实 API Key
API_KEY = "sk-c3a4adf8332747219a2847edbd8cb78a" 
# 假设使用 DeepSeek 的 API 地址，如果用其他模型请替换 base_url
client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com/v1")

WATCHLIST = ['603236', '300059', '588200', '513180']
# ======================================

def get_hot_sectors():
    """修复后的板块获取函数"""
    try:
        sector_df = ak.stock_board_industry_name_ths()
        # 打印一下实际的列名，以防万一
        # print(sector_df.columns) 
        
        # 兼容同花顺可能变化的列名
        target_col = '涨跌幅(%)' if '涨跌幅(%)' in sector_df.columns else '涨跌幅'
        
        # 需要将字符串转为浮点数才能正确排序
        sector_df[target_col] = pd.to_numeric(sector_df[target_col], errors='coerce')
        sector_df = sector_df.sort_values(by=target_col, ascending=False).head(5)
        
        # 组合成字符串
        sectors_str = ", ".join([f"{row['板块']}({row[target_col]}%)" for _, row in sector_df.iterrows()])
        return sectors_str
    except Exception as e:
        return f"获取失败: {e}"

# 假设这里是上一步收集到的所有数据 (此处为了演示，简化为文本变量)
# 实际运行中，你应该把上面抓取函数返回的字典转成这里的字符串
def build_prompt_data():
    hot_sectors = get_hot_sectors()
    
    # 构建投喂给 AI 的上下文
    data_context = f"""
    【当前时间】：早盘
    【链接附带要求】：请在报告开头附带链接：https://52etf.site/
    
    【市场核心数据】：
    - 上证指数: 3934.40 点 (今日涨跌: -0.433%)
    - 深证成指: 13617.67 点 (今日涨跌: -0.77%)
    - 创业板指: 3338.42 点 (今日涨跌: -0.493%)
    
    【当前领涨板块】：
    {hot_sectors}
    
    【自选股实时动态】：
    1. 移远通信(603236): 当前 60.62元，涨跌幅 -0.72%。近期新闻：拟10派4.7元；中报净利润6.02亿元。
    2. 东方财富(300059): 当前 18.97元，涨跌幅 +0.31%。近期新闻：期货概念资金流入。
    3. 科创芯片ETF(588200): 当前 1.106元，涨跌幅 -0.71%。
    4. 恒生科技ETF(513180): 当前 0.549元，涨跌幅 -1.78%。
    """
    return data_context

def generate_ai_report(data_context):
    print("=> 正在请求 AI 生成分析报告，请稍候...")
    
    # 这是你的“灵魂”：给 AI 定下分析纪律
    system_prompt = """
    你是一个专业的 A 股量化交易助理。
    请根据我提供的市场数据和自选股动态，生成一份精简、客观的早盘复盘报告。
    
    【要求】：
    1. 报告必须包含两部分：大盘及板块情绪总结、自选股逐一诊断。
    2. 诊断自选股时，请结合近期的题材（如新闻提及的概念）判断其强弱。
    3. 语气客观，直接给结论，不要使用套话。
    4. 严格遵守附带特定链接的要求。
    """
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat", # 或者你使用的其他模型名称
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"以下是今天早盘的实时数据，请开始生成报告：\n{data_context}"}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 调用失败，请检查 API Key 或网络: {e}"

if __name__ == '__main__':
    context = build_prompt_data()
    report = generate_ai_report(context)
    
    print("\n" + "="*50)
    print(report)
    print("="*50)