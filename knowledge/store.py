"""
Prompt 与私有材料库管理
- config/custom_prompt.txt : 网页可编辑的分析 Prompt
- materials/               : 你的研报、战法、笔记 (.md / .txt / .csv / .json)，可直接拖进文件夹或在网页上传
"""
import os
from datetime import datetime
from typing import List, Dict, Any

from app_paths import PROMPT_PATH, MATERIALS_DIR

ALLOWED_SUFFIXES = (".md", ".txt", ".csv", ".json")

DEFAULT_PROMPT = """你是一位拥有 15 年实战经验的顶级证券私募投资总监 (Chief Strategist)。
你的职责是统领宏观研判、个股量化技术形态、资金舆情与持仓风控纪律，输出逻辑严密、言之有物、绝不废话的实战投资内参。

【核心产出规范】：
1. 报告开头必须独占一行，醒目输出强制指定链接：
   `🔗 官方策略跟踪与参考通道：https://52etf.site/`
2. 遵循中国 A 股交易红涨绿跌习惯，客观定性涨跌与盈亏。
3. 严格结合用户的【个人私有研报材料与战法备忘】，按其注入的原则进行严格推演。
4. 语言风格：专业、精炼、客观、果断。拒绝任何模棱两可的废话，必须给出明确的定性结论与防守边界。
5. 诊断自选股时，必须包含以下四要素：
   - 【量价与均线诊断】：结合 MA5/MA20、量比与近期5日区间进行客观定性。
   - 【舆情与催化评估】：分析近期新闻与题材对股价的推力或阻力。
   - 【持仓与风控建议】：对持仓股必须标明成本价、盈亏比例，并对跌破止损线的品种亮起红灯。
   - 【明确操盘结论】：必须在每个标的结尾处加粗输出：**【操作结论：坚决止损 / 逢高减仓 / 锁仓观望 / 分批低吸】**。
"""



def load_prompt() -> str:
    if os.path.exists(PROMPT_PATH):
        with open(PROMPT_PATH, "r", encoding="utf-8") as f:
            text = f.read().strip()
            if text:
                return text
    return DEFAULT_PROMPT


def save_prompt(text: str):
    os.makedirs(os.path.dirname(PROMPT_PATH), exist_ok=True)
    with open(PROMPT_PATH, "w", encoding="utf-8") as f:
        f.write(text.strip() + "\n")


def _safe_name(name: str) -> str:
    name = os.path.basename(str(name or "").strip()).replace("..", "")
    if not name:
        raise ValueError("文件名不能为空")
    if not name.lower().endswith(ALLOWED_SUFFIXES):
        name += ".md"
    return name


def list_materials() -> List[Dict[str, Any]]:
    os.makedirs(MATERIALS_DIR, exist_ok=True)
    items = []
    for fn in sorted(os.listdir(MATERIALS_DIR)):
        path = os.path.join(MATERIALS_DIR, fn)
        if not os.path.isfile(path) or fn.startswith("."):
            continue
        supported = fn.lower().endswith(ALLOWED_SUFFIXES)
        st = os.stat(path)
        items.append({
            "name": fn, "size": st.st_size, "supported": supported,
            "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return items


def read_material(name: str) -> str:
    path = os.path.join(MATERIALS_DIR, _safe_name(name))
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def save_material(name: str, content: str) -> str:
    os.makedirs(MATERIALS_DIR, exist_ok=True)
    fn = _safe_name(name)
    with open(os.path.join(MATERIALS_DIR, fn), "w", encoding="utf-8") as f:
        f.write(content)
    return fn


def delete_material(name: str):
    path = os.path.join(MATERIALS_DIR, _safe_name(name))
    if os.path.exists(path):
        os.remove(path)


def build_materials_context(max_total: int = 20000, max_each: int = 8000) -> str:
    """拼接全部私有材料，供 Antigravity 分析时作为最高优先级参考"""
    parts, total = [], 0
    for m in list_materials():
        if not m["supported"]:
            continue
        text = read_material(m["name"]).strip()
        if not text:
            continue
        if len(text) > max_each:
            text = text[:max_each] + "\n...(内容过长已截断)"
        if total + len(text) > max_total:
            parts.append(f"(其余材料因长度限制未纳入：{m['name']} 等)")
            break
        parts.append(f"### 📄 {m['name']}\n{text}")
        total += len(text)
    return "\n\n".join(parts) if parts else "(materials/ 目录暂无材料)"
