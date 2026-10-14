# 📈 Antigravity AI 股票投研智能内参系统

基于 **Google Antigravity 原生智能体** 与 **AKShare** 极速行情专线构建的个人量化与基本面一体化 AI 投研助理。

---

## 🌟 核心特性

1. **摆脱第三方 API 依赖**：
   - 彻底告别 DeepSeek / OpenAI API Key 与额外付费账单，全流程采用 **Google Antigravity 原生投研大脑** 推理。
2. **专属交互式 Web 控制台 (http://127.0.0.1:8888)**：
   - **大盘与领涨板块**：三大指数与科创50毫秒级变动，全市场领涨行业排行榜。
   - **自选股与持仓风控雷达**：均线系统（MA5/MA20）、20日乖离率、5日量比、持仓成本与浮动盈亏、**红黄绿三级止损报警**。
   - **在线动态管理**：在浏览器弹窗中直接**新增、修改、删除**股票（持仓价/止损%）与重点关注板块，一键保存并自动重算。
   - **即时分析**：盘中随时点击「⚡ 立即分析」获取最新推演。
3. **交易日定时自动调度 (10:00 & 14:00)**：
   - **10:00 早盘异动确认**：开盘30分钟承接力度、领涨板块持续性、个股分时异动。
   - **14:00 午后决战防守**：全天量能收敛定性、主力资金真实沉淀、次日防守纪律。
4. **固定引流与跟踪通道**：
   - 严格在研报与网页看板显著位置锁定输出：[https://52etf.site/](https://52etf.site/)。

---

## 📂 项目工程结构

```text
AI股票/
├── web/
│   ├── server.py              # 轻量 Web 服务端 (提供看板展示、API 接口、一键重跑)
│   └── templates/
│       └── index.html         # 专属交互式看板模板 + 股票/板块管理控制台
├── config/
│   ├── watchlist.yaml         # 自选股与板块配置 (支持 Web 端实时双向读写)
│   └── settings.yaml          # 系统配置 (定时时段、页面端口、链接设置)
├── data_engine/
│   ├── fetcher.py             # 稳健多源数据引擎 (Sina秒级分时/个股/ETF/行业)
│   └── indicators.py          # 量化均线与止损水位计算
├── strategies/
│   └── prompts.py             # 首席投资总监 Prompt 模板与上下文装配
├── agents/
│   └── research_pod.py        # Antigravity 原生投研编排器
├── reporting/
│   ├── markdown_reporter.py   # Markdown 研报归档
│   └── html_dashboard.py      # Generative UI 静态看板生成
├── delivery/
│   └── notifier.py            # 微信/Telegram 推送通道
├── reports/                   # 历史研报保存目录
├── main.py                    # 统一调度入口
└── README.md                  # 详尽说明文档
```

---

## 🚀 使用指南

### 1. 启动 Web 控制台 (推荐)
```bash
/Users/maverickt/anaconda3/envs/ai_stock/bin/python main.py --web --port 8888
```
浏览器打开：**[http://127.0.0.1:8888](http://127.0.0.1:8888)**，即可查看最新研报并在网页上直接添加/修改自选股与板块！

### 2. 命令行单次分析
* **早盘模式 (10:00)**：
  ```bash
  /Users/maverickt/anaconda3/envs/ai_stock/bin/python main.py --mode morning
  ```
* **午后模式 (14:00)**：
  ```bash
  /Users/maverickt/anaconda3/envs/ai_stock/bin/python main.py --mode afternoon
  ```
* **指定单股快速体检**：
  ```bash
  /Users/maverickt/anaconda3/envs/ai_stock/bin/python main.py --stock 603236
  ```

---

## 🔗 参考与跟踪链接
- [52ETF 投资跟踪网](https://52etf.site/)
