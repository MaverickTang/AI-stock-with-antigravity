import os
import pandas as pd
import akshare as ak

# 1. 强制清理代理环境变量，确保海外网络环境请求顺利
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

# 你的自选股池 (修正了 30059 为 300059，你可以自行修改)
WATCHLIST = ['603236', '300059', '588200', '513180']

def get_market_indices():
    """获取大盘核心指数 (使用新浪接口)"""
    print("=> 正在获取大盘指数...")
    try:
        index_df = ak.stock_zh_index_spot_sina()
        target_indices = ['上证指数', '深证成指', '创业板指']
        # 筛选我们需要的三大指数
        market_data = index_df[index_df['名称'].isin(target_indices)][['名称', '最新价', '涨跌幅']]
        return market_data.to_dict(orient='records')
    except Exception as e:
        print(f"大盘指数获取失败: {e}")
        return []

def get_hot_sectors():
    """获取热点板块排名 (使用同花顺接口，稳定性高)"""
    print("=> 正在获取热点板块...")
    try:
        sector_df = ak.stock_board_industry_name_ths()
        # 按涨跌幅降序排列，取前 5 名
        sector_df = sector_df.sort_values(by='涨跌幅', ascending=False).head(5)
        return sector_df[['板块', '涨跌幅']].to_dict(orient='records')
    except Exception as e:
        print(f"板块数据获取失败: {e}")
        return []

def get_watchlist_data(watchlist):
    """获取自选股与 ETF 的实时行情及近期新闻"""
    print("=> 正在获取自选股及ETF动态...")
    results = {}
    
    try:
        # 获取 A 股全市场实时行情
        a_stock_df = ak.stock_zh_a_spot()
        a_stock_df['代码'] = a_stock_df['代码'].astype(str)
        
        # 获取 ETF 全市场实时行情
        etf_df = ak.fund_etf_category_sina(symbol="ETF基金")
        etf_df['代码'] = etf_df['代码'].astype(str)
        
        for code in watchlist:
            # 先在股票池中找，找不到再去 ETF 池中找
            spot = a_stock_df[a_stock_df['代码'].str.contains(code)]
            if spot.empty:
                spot = etf_df[etf_df['代码'].str.contains(code)]
                
            if not spot.empty:
                name = spot['名称'].values[0]
                price = spot['最新价'].values[0]
                pct = spot['涨跌幅'].values[0]
                
                # 尝试获取个股/ETF近期新闻 (由于东方财富接口可能有海外限制，加入 try-except 保护)
                news_titles = []
                try:
                    news_df = ak.stock_news_em(symbol=code)
                    # 取最新的 3 条新闻标题
                    news_titles = news_df['新闻标题'].head(3).tolist()
                except:
                    news_titles = ["暂无新闻或接口限制"]
                
                results[code] = {
                    "名称": name,
                    "最新价": price,
                    "涨跌幅": f"{pct}%",
                    "近期新闻": news_titles
                }
            else:
                results[code] = {"错误": "未找到行情数据"}
                
        return results
        
    except Exception as e:
        print(f"自选股数据获取失败: {e}")
        return {}

if __name__ == '__main__':
    print("\n" + "="*50)
    print("【AI 股票助理 - 数据采集引擎启动】")
    print("="*50 + "\n")
    
    # 1. 抓取并打印大盘数据
    indices = get_market_indices()
    print("📊【大盘概况】")
    for idx in indices:
        print(f"  - {idx['名称']}: {idx['最新价']} 点 (今日涨跌: {idx['涨跌幅']}%)")
        
    # 2. 抓取并打印板块数据
    print("\n🔥【领涨热点板块 Top 5】")
    sectors = get_hot_sectors()
    for sec in sectors:
        print(f"  - {sec['板块']}: {sec['涨跌幅']}%")
        
    # 3. 抓取并打印自选股及新闻
    print("\n🎯【自选股 / ETF 跟踪】")
    watchlist_data = get_watchlist_data(WATCHLIST)
    for code, data in watchlist_data.items():
        if "错误" in data:
            print(f"  ❌ 代码 {code}: {data['错误']}")
        else:
            print(f"\n  [{data['名称']}] (代码: {code})")
            print(f"    ▶ 最新价: {data['最新价']} | 涨跌幅: {data['涨跌幅']}")
            print(f"    ▶ 近期资讯:")
            for i, news in enumerate(data['近期新闻']):
                print(f"      {i+1}. {news}")
    
    print("\n" + "="*50)
    print("✅ 原始数据抓取完成！准备就绪，可随时投喂给 AI。")

# import os
# import akshare as ak
# import pandas as pd

# # 强制清理代理环境变量，避免 Mac 底层网络库被劫持
# os.environ.pop("http_proxy", None)
# os.environ.pop("https_proxy", None)
# os.environ.pop("HTTP_PROXY", None)
# os.environ.pop("HTTPS_PROXY", None)

# def query_stock(stock_code):
#     print(f"\n正在通过新浪财经查询股票代码: {stock_code}，请稍候...")
#     try:
#         # 1. 获取 A 股实时行情数据 (使用新浪接口，对海外 IP 友好)
#         spot_df = ak.stock_zh_a_spot()
        
#         # 将代码列转换为字符串，防止因格式问题匹配失败
#         spot_df['代码'] = spot_df['代码'].astype(str)
        
#         # 筛选出用户输入的股票代码
#         # 新浪接口的代码有的带前缀(如 sh600000)，有的不带，这里使用 str.contains 模糊匹配后缀
#         stock_spot = spot_df[spot_df['代码'].str.contains(stock_code)]
        
#         if stock_spot.empty:
#             print("未找到该股票的行情，请检查代码是否正确（例如：平安银行是 000001）。")
#             return

#         # 提取核心行情数据
#         stock_name = stock_spot['名称'].values[0]
#         latest_price = stock_spot['最新价'].values[0]
#         change_amount = stock_spot['涨跌额'].values[0]
#         change_percent = stock_spot['涨跌幅'].values[0]
#         volume = stock_spot['成交量'].values[0]
#         turnover = stock_spot['成交额'].values[0]
        
#         # 3. 打印展示结果
#         print("\n" + "="*40)
#         print(f"【{stock_name}】 (代码: {stock_code})")
#         print(f"最新价格: {latest_price} 元")
#         print(f"今日涨跌幅: {change_percent}% (涨跌额: {change_amount}元)")
#         print(f"今日成交量: {volume} 手")
#         print(f"今日成交额: {turnover} 元")
#         print("="*40 + "\n")
        
#     except Exception as e:
#         print(f"\n查询失败，错误信息: {e}")
#         print("请检查网络状态，或稍后再试。")

# if __name__ == '__main__':
#     print("欢迎使用 Python A股 查询工具！")
#     while True:
#         code = input("请输入 6 位 A股 股票代码 (输入 'q' 退出): ")
        
#         if code.lower() == 'q':
#             print("已退出查询程序。")
#             break
            
#         if len(code) != 6 or not code.isdigit():
#             print("⚠️ 股票代码格式错误，请输入 6 位数字代码！\n")
#             continue
            
#         query_stock(code)