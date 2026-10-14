"""
项目统一路径定义 (全部基于项目根目录的绝对路径，保证从任意工作目录 / 定时任务启动都能正确读写)
"""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

CONFIG_DIR = os.path.join(ROOT, "config")
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.yaml")
WATCHLIST_PATH = os.path.join(CONFIG_DIR, "watchlist.yaml")
PROMPT_PATH = os.path.join(CONFIG_DIR, "custom_prompt.txt")

MATERIALS_DIR = os.path.join(ROOT, "materials")

REPORTS_DIR = os.path.join(ROOT, "reports")
HISTORY_DIR = os.path.join(REPORTS_DIR, "history")
PERIODIC_DIR = os.path.join(REPORTS_DIR, "periodic")
INSIGHTS_DIR = os.path.join(REPORTS_DIR, "ai_insights")
INSIGHTS_ARCHIVE_DIR = os.path.join(INSIGHTS_DIR, "archive")
LATEST_RESULT_PATH = os.path.join(REPORTS_DIR, "latest.json")
AI_CONTEXT_PATH = os.path.join(REPORTS_DIR, "ai_context.md")
AI_INSIGHTS_LATEST = os.path.join(INSIGHTS_DIR, "latest.json")

WEB_TEMPLATE = os.path.join(ROOT, "web", "templates", "index.html")


def ensure_dirs():
    for d in (CONFIG_DIR, MATERIALS_DIR, REPORTS_DIR, HISTORY_DIR, PERIODIC_DIR,
              INSIGHTS_DIR, INSIGHTS_ARCHIVE_DIR):
        os.makedirs(d, exist_ok=True)
