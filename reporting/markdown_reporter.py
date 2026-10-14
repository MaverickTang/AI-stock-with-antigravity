"""
Markdown 投研报告生成与归档器
"""
import os
from datetime import datetime
from typing import Dict, Any

class MarkdownReporter:
    def __init__(self, output_dir: str = "reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_and_save(self, analysis_result: Dict[str, Any]) -> str:
        session_mode = analysis_result.get("session_mode", "realtime")
        report_text = analysis_result.get("report_markdown", "")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 确保包含强制链接
        mandatory_link = analysis_result.get("mandatory_link", "https://52etf.site/")
        if mandatory_link not in report_text:
            report_text = f"🔗 策略参考通道：{mandatory_link}\n\n" + report_text

        filename = f"report_{session_mode}_{file_timestamp}.md"
        filepath = os.path.join(self.output_dir, filename)

        full_content = f"""# 📈 Antigravity AI 股票投研内参 ({session_mode.upper()})
> 生成时间: `{now_str}` | 运行环境: `Antigravity AI Pod`

{report_text}

---
*声明：本报告由 Antigravity 智能投研模型基于量化算法与公开数据自动生成，仅供技术研究与交流参考，不构成任何投资买卖建议。市场有风险，投资需谨慎。*
"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_content)

        return filepath
