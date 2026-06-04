"""
restructure_project.py
======================
重组计划生成与展示模块。

功能:
  1. generate_plan()    - 根据 AI 分析结果 + 用户指定的输出名，生成完整重组计划
  2. parse_ai_plan()    - 解析 AI 返回的 JSON 为结构化计划
  3. show_plan_summary() - 友好展示计划内容，供用户确认
  4. refine_plan()      - 允许用户微调计划（简单交互）
"""

import json
import os
from pathlib import Path
from openai import OpenAI


# ── 生成计划 ──────────────────────────────────────────────────────


def generate_plan(analysis_text: str,
                  project_info: dict,
                  output_name: str,
                  api_key: str,
                  base_url: str = "https://api.deepseek.com",
                  model: str = "deepseek-v4-pro") -> dict:
    """
    将 AI 分析结果 + 用户指定的输出名 → DeepSeek 生成详细重组计划。

    Args:
        analysis_text: analyze_with_ai() 的原始返回（JSON 字符串）
        project_info: scan_project() 的结果
        output_name: 用户指定的输出目录名
        api_key, base_url, model: API 配置

    Returns:
        重组计划 dict，结构见 parse_ai_plan()
    """
    # 尝试直接解析已有的 analysis_text
    try:
        parsed = json.loads(analysis_text) if isinstance(analysis_text, str) else analysis_text
        # 检查关键字段
        if "file_moves" in parsed and "suggested_structure" in parsed:
            # 直接使用，注入 output_name
            parsed["project_name"] = output_name
            return _normalize_plan(parsed, project_info, output_name)
    except (json.JSONDecodeError, TypeError):
        pass

    # 需要 AI 进一步生成
    client = OpenAI(api_key=api_key, base_url=base_url)

    py_files = project_info.get("python_files", [])
    file_list = "\n".join(f"  {f['path']} ({f['lines']} 行, {f['size_kb']} KB)" for f in py_files)

    prompt = f"""你是一个Python项目重构专家。基于以下分析结果和文件列表，生成一个完整的项目重组计划。

输出目录名称由用户指定为: **{output_name}**

## 📋 项目文件列表
{file_list}

## 📊 分析结果参考
{analysis_text[:3000] if isinstance(analysis_text, str) else json.dumps(analysis_text, ensure_ascii=False)[:3000]}

请生成严格 JSON 格式的重组计划：

{{
    "project_name": "{output_name}",
    "description": "简短项目描述",

    "structure": {{
        "src": ["src/module1", "src/module2"],
        "data": ["data/raw", "data/processed"],
        "tests": [],
        "docs": []
    }},

    "file_moves": [
        {{"from": "原文件路径", "to": "新文件路径", "reason": "移动原因"}}
    ],

    "files_to_create": [
        {{"path": "新文件路径（如 README.md）", "content": "文件内容"}}
    ],

    "files_to_delete": [
        "冗余文件路径"
    ],

    "files_to_merge": [
        {{"sources": ["文件1", "文件2"], "target": "合并后路径", "reason": "合并原因"}}
    ],

    "large_data_advice": [
        {{"path": "数据目录", "size_mb": 100, "action": "建议操作"}}
    ],

    "gitignore_patterns": ["__pycache__/", "*.pyc"],
    "git_lfs_patterns": ["*.csv", "*.pkl"]
}}

注意：
- file_moves 中的 "from" 是原项目中的相对路径
- file_moves 中的 "to" 是输出项目中的相对路径（以 {output_name}/ 开头）
- 所有 Python 文件必须被移动，不能遗漏
- files_to_create 只包含需要创建的新文件（README.md, requirements.txt, .gitignore, setup.py/pyproject.toml, 各目录 __init__.py）
- 对于 files_to_create 中的新文件，请给出合理的初始内容
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=16000,
            response_format={"type": "json_object"},
        )
    except Exception:
        # 降级：API 不支持 response_format 时重试
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=16000,
        )

    plan_str = response.choices[0].message.content
    plan = json.loads(plan_str)
    plan["project_name"] = output_name
    return _normalize_plan(plan, project_info, output_name)


def _normalize_plan(plan: dict, project_info: dict, output_name: str) -> dict:
    """规范化计划结构，补全默认字段"""
    defaults = {
        "project_name": output_name,
        "description": "",
        "structure": {"src": [], "data": [], "tests": [], "docs": []},
        "file_moves": [],
        "files_to_create": [],
        "files_to_delete": [],
        "files_to_merge": [],
        "large_data_advice": [],
        "gitignore_patterns": [
            "__pycache__/", "*.py[cod]", "*.egg-info/",
            "dist/", "build/", ".env", "venv/", ".venv/",
            ".vscode/", ".idea/", ".DS_Store", "Thumbs.db",
            ".ipynb_checkpoints/",
        ],
        "git_lfs_patterns": ["*.csv", "*.pkl", "*.bin", "*.h5"],
    }
    for key, val in defaults.items():
        plan.setdefault(key, val)

    # 确保 project_name 一致
    plan["project_name"] = output_name
    return plan


# ── 展示计划 ──────────────────────────────────────────────────────


def show_plan_summary(plan: dict) -> None:
    """友好展示重组计划"""
    name = plan.get("project_name", "unknown")
    desc = plan.get("description", "")

    print("\n" + "=" * 60)
    print(f"📋 重组计划预览")
    print("=" * 60)
    print(f"📦 项目名称: {name}")
    if desc:
        print(f"📝 描述:     {desc}")

    # 结构预览
    structure = plan.get("structure", {})
    if structure:
        print(f"\n📁 目标结构:")
        _print_structure_tree(name, structure)

    # 文件移动
    moves = plan.get("file_moves", [])
    print(f"\n📄 文件移动 ({len(moves)} 项):")
    if len(moves) <= 20:
        for m in moves:
            print(f"   {m.get('from', '?')}  →  {m.get('to', '?')}")
            if m.get("reason"):
                print(f"      ↳ {m['reason']}")
    else:
        for m in moves[:10]:
            print(f"   {m.get('from', '?')}  →  {m.get('to', '?')}")
        print(f"   ... 还有 {len(moves) - 10} 项（请查看完整计划文件）")

    # 合并文件
    merges = plan.get("files_to_merge", [])
    if merges:
        print(f"\n🔗 文件合并 ({len(merges)} 项):")
        for m in merges:
            sources = ", ".join(m.get("sources", []))
            print(f"   合并: [{sources}]")
            print(f"      → {m.get('target', '?')}")
            print(f"      ↳ {m.get('reason', '')}")

    # 新文件
    creates = plan.get("files_to_create", [])
    if creates:
        print(f"\n🆕 创建新文件 ({len(creates)} 项):")
        for c in creates:
            content_preview = c.get("content", "")
            preview = content_preview[:80].replace("\n", " ") + ("..." if len(content_preview) > 80 else "")
            print(f"   + {c.get('path', '?')}  ({preview})")

    # 删除文件
    deletes = plan.get("files_to_delete", [])
    if deletes:
        print(f"\n🗑️  建议删除 ({len(deletes)} 项):")
        for d in deletes:
            print(f"   ✕ {d}")

    # 大数据建议
    large = plan.get("large_data_advice", [])
    if large:
        print(f"\n📦 大数据处理建议:")
        for item in large:
            print(f"   {item.get('path', '?')} ({item.get('size_mb', '?')} MB)")
            print(f"   → {item.get('action', '')}")

    # Git 配置
    gitignore = plan.get("gitignore_patterns", [])
    lfs = plan.get("git_lfs_patterns", [])
    if gitignore:
        print(f"\n🔒 .gitignore 规则 ({len(gitignore)} 条)")
    if lfs:
        print(f"📎 Git LFS 规则 ({len(lfs)} 条)")

    print("\n" + "=" * 60)


def _print_structure_tree(root_name: str, structure: dict, indent: str = "") -> None:
    """打印结构树"""
    print(f"{indent}{root_name}/")
    indent += "    "
    categories = []
    for key, val in structure.items():
        if isinstance(val, list):
            categories.append((key, val))
        elif isinstance(val, dict):
            categories.append((key, val))
        else:
            print(f"{indent}├── {key}")

    for i, (key, val) in enumerate(categories):
        is_last = i == len(categories) - 1
        connector = "└── " if is_last else "├── "
        if isinstance(val, list):
            print(f"{indent}{connector}{key}/")
            sub_indent = indent + ("    " if is_last else "│   ")
            for j, item in enumerate(val):
                sub_con = "└── " if j == len(val) - 1 else "├── "
                print(f"{sub_indent}{sub_con}{item}")
        elif isinstance(val, dict):
            print(f"{indent}{connector}{key}/")
            sub_indent = indent + ("    " if is_last else "│   ")
            _print_structure_tree("", val, sub_indent)


# ── 计划确认 ──────────────────────────────────────────────────────


def confirm_plan(plan: dict) -> tuple[bool, dict]:
    """
    用户交互确认计划。

    Returns:
        (confirmed: bool, may_be_modified_plan: dict)
    """
    show_plan_summary(plan)

    print()
    choice = input("是否执行此重组计划？\n"
                   "  [Y] 是，开始执行\n"
                   "  [n] 否，取消\n"
                   "  [e] 编辑（高级：手动修改 plan.json 后继续）\n"
                   "请选择 (Y/n/e): ").strip().lower()

    if choice == "n":
        return False, plan
    elif choice == "e":
        return _edit_plan_interactive(plan)
    else:
        return True, plan


def _edit_plan_interactive(plan: dict) -> tuple[bool, dict]:
    """保存计划到文件，让用户编辑后重新加载"""
    plan_path = Path.cwd() / "_plan_to_review.json"
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"\n✏️  计划已保存到: {plan_path}")
    print("请编辑此文件，然后按回车继续...")
    input("编辑完成后按回车继续: ")

    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            modified = json.load(f)
        print("✅ 计划已更新")
        show_plan_summary(modified)
        ok = input("确认使用修改后的计划？(Y/n): ").strip().lower()
        if ok == "n":
            return False, plan
        return True, modified
    except (json.JSONDecodeError, OSError) as e:
        print(f"❌ 读取计划文件失败: {e}")
        return False, plan


# ── 保存计划 ──────────────────────────────────────────────────────


def save_plan(plan: dict, output_dir: str) -> Path:
    """将计划保存到输出目录"""
    out = Path(output_dir) / "_restructure_plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    return out


# ── 独立运行 ────────────────────────────────────────────────────────


if __name__ == "__main__":
    import sys
    from config import get_api_key, get_base_url, get_model

    plan_file = sys.argv[1] if len(sys.argv) > 1 else None
    if plan_file and Path(plan_file).exists():
        with open(plan_file) as f:
            sample_plan = json.load(f)
    else:
        sample_plan = {
            "project_name": "demo-project",
            "description": "演示项目",
            "structure": {"src": ["src/main"], "tests": []},
            "file_moves": [],
            "files_to_create": [
                {"path": "README.md", "content": "# Demo\n"},
                {"path": "requirements.txt", "content": ""},
            ],
            "files_to_delete": [],
            "files_to_merge": [],
            "large_data_advice": [],
            "gitignore_patterns": ["__pycache__/"],
            "git_lfs_patterns": [],
        }
    show_plan_summary(sample_plan)
