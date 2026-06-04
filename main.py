#!/usr/bin/env python3
"""
GitHub-Ready 项目重组工具
=========================
一键分析、重组老旧 Python 项目，生成 GitHub 友好的目录结构。

用法:
  python main.py

流程:
  1. 配置 API Key（自动检测 / 首次输入可保存）
  2. 输入待处理的项目路径
  3. 指定新项目名称（输出目录名，由你决定）
  4. 自动备份原项目（时间戳后缀，零风险）
  5. AI 扫描并分析项目代码结构
  6. 检测大数据目录并给出处理建议
  7. 展示重组方案，用户确认后执行
  8. 生成 README.md / .gitignore / requirements.txt
  9. 打印 GitHub 上传指引

特点:
  ✅ 保留原项目备份，零风险
  ✅ 输出目录名由你指定
  ✅ 自动识别大文件/大目录
  ✅ 交互式确认，不盲目执行
  ✅ 生成的目录结构适合直接上传 GitHub
"""

import os
import sys
import json
import time
from pathlib import Path

# 确保当前目录在 path 中
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from config import get_or_prompt_api_key, get_base_url, get_model
from analyze_project import (
    scan_project,
    analyze_with_ai,
    detect_large_dirs,
    detect_large_files,
)
from restructure_project import (
    generate_plan,
    confirm_plan,
    save_plan,
)
from execute_refactor import (
    backup_project,
    execute_restructure,
    generate_git_files,
    print_github_guide,
    print_summary,
)
from generate_readme import generate_readme, save_readme


# ═══════════════════════════════════════════════════════════════════
#  Banner
# ═══════════════════════════════════════════════════════════════════


def print_banner():
    print(r"""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   ██████  ██ ████████ ██   ██ ██    ██ ██████           ║
║  ██       ██    ██    ██   ██ ██    ██ ██   ██          ║
║  ██   ███ ██    ██    ███████ ██    ██ ██████           ║
║  ██    ██ ██    ██    ██   ██ ██    ██ ██   ██          ║
║   ██████  ██    ██    ██   ██  ██████  ██   ██          ║
║                                                          ║
║     GitHub-Ready 老旧项目重组工具                          ║
║     分析 → 备份 → 重组 → README → GitHub 就绪             ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
""")


# ═══════════════════════════════════════════════════════════════════
#  交互输入
# ═══════════════════════════════════════════════════════════════════


def prompt_project_path() -> str:
    """提示用户输入项目路径，回车列出当前目录供选择"""
    print()
    path = input("📂 请输入要处理的项目路径\n"
                 "   （直接回车可浏览当前目录）\n"
                 "   > ").strip()

    if not path:
        cwd = Path.cwd()
        print(f"\n📋 当前目录: {cwd}")
        items = [p for p in cwd.iterdir() if p.is_dir() and not p.name.startswith(".")]
        if items:
            print("子目录:")
            for i, item in enumerate(items, 1):
                try:
                    size = sum(f.stat().st_size for f in item.rglob("*")
                               if f.is_file()) / 1024 / 1024
                    print(f"  [{i}] {item.name}/  ({size:.1f} MB)")
                except OSError:
                    print(f"  [{i}] {item.name}/")
            print()
            idx = input("选择编号或输入完整路径: ").strip()
            if idx.isdigit():
                idx_num = int(idx)
                if 1 <= idx_num <= len(items):
                    path = str(items[idx_num - 1])
                else:
                    path = idx if idx else "."
            else:
                path = idx if idx else "."
        else:
            print("  （无子目录）")
            path = input("请输入完整项目路径: ").strip()
    return path


def prompt_output_name(default_name: str) -> str:
    """提示用户指定输出目录名"""
    print()
    name = input(f"📦 请指定新项目名称（输出目录名，由你决定）\n"
                 f"   建议: {default_name}\n"
                 f"   > ").strip()
    if not name:
        name = default_name
    # 清理不安全的文件名字符
    name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return name


# ═══════════════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════════════


def main():
    print_banner()

    # ── 0. API 配置 ──
    api_key, base_url, model = get_or_prompt_api_key()

    # ── 1. 项目路径 ──
    project_path = prompt_project_path()
    project_path = os.path.abspath(project_path)

    if not os.path.isdir(project_path):
        print(f"\n❌ 路径不存在或不是目录: {project_path}")
        retry = input("重新输入？(Y/n): ").strip().lower()
        if retry != "n":
            return main()
        sys.exit(1)

    # ── 2. 扫描项目 ──
    print(f"\n📂 扫描项目: {project_path}")
    project_info = scan_project(project_path)
    print(f"   找到 {project_info['py_file_count']} 个 Python 文件，"
          f"共 {project_info['total_files']} 个文件，"
          f"总大小 {project_info['total_size_mb']} MB")

    # 检测大数据
    print("\n🔍 检测大目录 / 大文件...")
    large_dirs = detect_large_dirs(project_path)
    large_files = detect_large_files(project_path)
    large_info_parts = []
    if large_dirs:
        for d in large_dirs:
            large_info_parts.append(
                f"大目录: {d['path']} = {d['size_mb']} MB ({d['file_count']} 文件)"
            )
            print(f"   📁 {d['path']}: {d['size_mb']} MB {d['suggestion']}")
    if large_files:
        for f in large_files:
            large_info_parts.append(f"大文件: {f['path']} = {f['size_mb']} MB")
            print(f"   📄 {f['path']}: {f['size_mb']} MB {f['suggestion']}")
    project_info["large_data_info"] = "\n".join(large_info_parts) if large_info_parts else "无"

    # 收集需要跳过的大文件/目录（不复制到新项目，改记录到清单）
    large_skip_paths: set[str] = set()
    for f in large_files:
        large_skip_paths.add(f["path"])
    for d in large_dirs:
        large_skip_paths.add(d["path"] + "/")  # 带 / 后缀，做前缀匹配
    if large_skip_paths:
        print(f"\n⏭️  检测到 {len(large_skip_paths)} 个大文件/目录，"
              f"将跳过复制并记录到 _LARGE_FILES_MANIFEST.md")
        skip_confirm = input("  是否跳过这些大文件？(Y/n): ").strip().lower()
        if skip_confirm == "n":
            large_skip_paths = set()
            print("   ⏩ 不跳过，将全部复制到新项目")

    # ── 3. 输出名称 ──
    default_name = os.path.basename(project_path).replace(" ", "-").lower()
    output_name = prompt_output_name(default_name)
    output_path = os.path.join(os.path.dirname(project_path), output_name)

    if os.path.exists(output_path):
        print(f"\n⚠️  输出目录已存在: {output_path}")
        overwrite = input("  是否覆盖？(y/N): ").strip().lower()
        if overwrite != "y":
            print("❌ 已取消")
            sys.exit(1)
        # 清空目录
        import shutil
        shutil.rmtree(output_path)

    print(f"\n✅ 配置确认:")
    print(f"   源项目:   {project_path}")
    print(f"   输出目录: {output_path}")
    print(f"   AI 模型:  {model}")
    print()

    # ── 4. 备份 ──
    print("💾 备份原项目...")
    backup_path = os.path.join(
        os.path.dirname(project_path),
        f"{os.path.basename(project_path)}_backup_{int(time.time())}"
    )
    choice = input("是否创建备份？(Y/n): ").strip().lower()
    if choice != "n":
        backup_project(project_path, backup_path)
    else:
        print("⏩ 跳过备份")
        backup_path = None

    print()
    input("按回车继续到 AI 分析...")

    # ── 5. AI 分析 ──
    print("\n" + "=" * 60)
    print("🔍 第1步：AI 分析项目架构")
    print("=" * 60)
    print(f"🤖 调用 {model} 进行架构分析（这需要一些时间）...")
    ai_reply = analyze_with_ai(project_info, api_key, base_url, model)

    # 显示分析结果摘要
    ai_json = None
    try:
        ai_json = json.loads(ai_reply)
        print(f"\n📋 分析摘要:")
        print(f"   项目名称建议: {ai_json.get('project_name', 'N/A')}")
        print(f"   功能描述:     {ai_json.get('description', 'N/A')[:100]}")
        tech = ai_json.get('tech_stack', [])
        if tech:
            print(f"   技术栈:       {', '.join(tech[:8])}")
        dup = ai_json.get('duplicate_files', [])
        if dup:
            print(f"   发现重复代码: {len(dup)} 处")
    except json.JSONDecodeError:
        print("  ⚠️  AI 返回格式非标准 JSON，将尝试提取关键信息")
    print()

    input("按回车继续到下一步...")

    # ── 6. 生成重组计划 ──
    print("\n" + "=" * 60)
    print("📋 第2步：生成重组计划")
    print("=" * 60)
    print("🤖 AI 正在规划新目录结构...")

    plan = generate_plan(ai_reply, project_info, output_name, api_key, base_url, model)

    # 保存计划
    plan_dir = os.path.join(os.path.dirname(project_path), f".{output_name}_plan")
    plan_path = save_plan(plan, plan_dir)
    print(f"   计划已保存到: {plan_path}")

    # ── 7. 展示并确认 ──
    print("\n" + "=" * 60)
    print("👀 第3步：确认重组计划")
    print("=" * 60)

    confirmed, plan = confirm_plan(plan)
    if not confirmed:
        print("\n❌ 已取消重组")
        if backup_path:
            print(f"💾 原项目备份位于: {backup_path}")
        sys.exit(0)

    # ── 8. 执行重组 ──
    print("\n" + "=" * 60)
    print("🛠️  第4步：执行重组")
    print("=" * 60)

    # 模拟运行
    print("\n🔍 模拟运行（预览改动，不实际操作）...")
    stats_dry = execute_restructure(plan, project_path, output_path,
                                       dry_run=True,
                                       skip_paths=large_skip_paths)

    print(f"\n模拟完成，预计:")
    print(f"   移动/复制: {stats_dry['moved']} 个文件")
    print(f"   创建新文件: {stats_dry['created']} 个")
    print(f"   合并文件:   {stats_dry['merged']} 组")
    if stats_dry.get('skipped'):
        print(f"   跳过（大文件）: {stats_dry['skipped']} 个")

    final_confirm = input("\n确认执行以上操作？(Y/n): ").strip().lower()
    if final_confirm == "n":
        print("❌ 已取消")
        if backup_path:
            print(f"💾 原项目备份位于: {backup_path}")
        sys.exit(0)

    stats = execute_restructure(plan, project_path, output_path,
                                   dry_run=False,
                                   skip_paths=large_skip_paths)

    # ── 9. 生成文档和配置 ──
    print("\n" + "=" * 60)
    print("📝 第5步：生成文档和配置文件")
    print("=" * 60)

    # 提取描述
    description = plan.get("description", "")
    if not description and ai_json:
        description = ai_json.get("description", "")

    # README.md
    print("  🤖 生成 README.md...")
    readme_content = generate_readme(
        project_path=output_path,
        project_name=output_name,
        description=description,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    save_readme(output_path, readme_content)

    # requirements.txt（如果计划中没有创建）
    has_req = any(
        c.get("path", "").lower().endswith("requirements.txt")
        for c in plan.get("files_to_create", [])
    )
    if not has_req:
        req_path = Path(output_path) / "requirements.txt"
        if not req_path.exists():
            imports = _scan_imports(output_path)
            _write_requirements(req_path, imports)

    # .gitignore 和 .gitattributes
    generate_git_files(output_path, plan)

    # ── 10. 完成 ──
    print_summary(output_path, plan, stats)
    print_github_guide(output_path, plan)

    # 大目录提醒
    if large_dirs:
        print("\n📦 已检测到的大数据目录（请确认 .gitignore 是否已排除）:")
        for d in large_dirs:
            print(f"  📁 {d['path']} -> {d['size_mb']} MB ({d['suggestion']})")

    if backup_path:
        print(f"\n💾 原项目备份: {backup_path}")

    print("\n✅ 全部完成！")


# ═══════════════════════════════════════════════════════════════════
#  辅助：检测依赖并生成 requirements.txt
# ═══════════════════════════════════════════════════════════════════


def _scan_imports(project_path: str) -> list[str]:
    """扫描项目中的 import，返回常见第三方库列表"""
    common_packages = {
        "numpy", "pandas", "torch", "tensorflow", "keras", "sklearn",
        "scikit-learn", "matplotlib", "seaborn", "plotly", "flask",
        "django", "fastapi", "requests", "beautifulsoup4", "scrapy",
        "opencv-python", "pillow", "nltk", "transformers", "tqdm",
        "click", "typer", "rich", "pydantic", "sqlalchemy",
        "redis", "pymongo", "psycopg2", "mysqlclient", "celery",
        "xgboost", "catboost", "lightgbm", "optuna",
        "streamlit", "gradio",
        "pytest", "mypy", "black", "flake8",
        "openai", "anthropic", "langchain",
    }
    found = set()
    for dirpath, _, filenames in os.walk(project_path):
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            try:
                with open(os.path.join(dirpath, fname), "r",
                          encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith("import ") or line.startswith("from "):
                            parts = line.split()
                            if len(parts) > 1:
                                pkg = parts[1].split(".")[0]
                                if pkg in common_packages:
                                    found.add(pkg)
            except OSError:
                continue

    # 过滤标准库
    stdlib = {"pathlib", "shutil", "os", "sys", "json", "re", "math",
              "datetime", "collections", "functools", "itertools", "typing",
              "abc", "copy", "glob", "hashlib", "inspect", "io",
              "logging", "multiprocessing", "operator", "random",
              "string", "subprocess", "tempfile", "threading", "traceback",
              "uuid", "warnings", "weakref"}
    return sorted(p for p in found if p not in stdlib)


def _write_requirements(req_path: Path, imports: list[str]) -> None:
    """写入 requirements.txt"""
    version_hints = {
        "numpy": "numpy>=1.24.0",
        "pandas": "pandas>=2.0.0",
        "scikit-learn": "scikit-learn>=1.3.0",
        "sklearn": "scikit-learn>=1.3.0",
        "xgboost": "xgboost>=2.0.0",
        "catboost": "catboost>=1.2.0",
        "lightgbm": "lightgbm>=4.0.0",
        "torch": "torch>=2.0.0",
        "tensorflow": "tensorflow>=2.13.0",
        "flask": "flask>=3.0.0",
        "fastapi": "fastapi>=0.100.0",
        "requests": "requests>=2.31.0",
        "tqdm": "tqdm>=4.66.0",
        "optuna": "optuna>=3.4.0",
        "openai": "openai>=1.0.0",
        "matplotlib": "matplotlib>=3.7.0",
        "seaborn": "seaborn>=0.13.0",
        "pydantic": "pydantic>=2.0.0",
        "sqlalchemy": "sqlalchemy>=2.0.0",
        "rich": "rich>=13.0.0",
        "click": "click>=8.1.0",
        "pytest": "pytest>=7.4.0",
    }
    lines = ["# 自动生成的依赖文件",
             f"# 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    for pkg in imports:
        if pkg in version_hints:
            lines.append(version_hints[pkg])
        else:
            lines.append(pkg)
    lines.append("")
    with open(req_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  ✅  requirements.txt ({len(imports)} 个依赖)")


# ═══════════════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
