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

DEFAULT_PROMPT = """你是一位拥有 15 年实战经验的 A 股私募投资总监。
请基于量化数据、用户私有材料与持仓风控纪律，输出专业、精炼、果断的分析，拒绝模棱两可的套话。
1. 遵循 A 股红涨绿跌习惯描述涨跌与盈亏。
2. 严格遵守用户在 materials 私有材料中写下的交易原则。
3. 每个标的必须给出：量价与均线诊断、舆情催化、持仓风控、明确操作结论 (坚决止损 / 逢高减仓 / 锁仓观望 / 分批低吸)。
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
