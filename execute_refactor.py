"""
execute_refactor.py
====================
备份与重组执行模块。

功能:
  1. backup_project()      - 创建原项目的时间戳备份
  2. execute_restructure() - 按计划执行文件移动/复制/创建/删除
  3. generate_git_files()  - 生成 .gitignore, .gitattributes
  4. print_summary()       - 打印执行结果和 GitHub 上传指引
"""

import os
import shutil
import json
import time
from pathlib import Path


# ── 备份 ──────────────────────────────────────────────────────────


def backup_project(project_path: str,
                   backup_dir: str | None = None) -> str:
    """
    创建原项目备份。

    Args:
        project_path: 原项目路径
        backup_dir: 备份存放目录，默认在项目同级目录创建

    Returns:
        备份路径
    """
    src = Path(project_path).resolve()
    if not src.is_dir():
        raise NotADirectoryError(f"项目路径不存在: {project_path}")

    if backup_dir is None:
        backup_dir = src.parent / f"{src.name}_backup_{int(time.time())}"
    else:
        backup_dir = Path(backup_dir)
        if not backup_dir.is_absolute():
            backup_dir = src.parent / backup_dir

    if backup_dir.exists():
        print(f"⚠️  备份目录已存在，跳过: {backup_dir}")
        return str(backup_dir)

    print(f"📦 正在备份: {src}  →  {backup_dir}")
    shutil.copytree(src, backup_dir,
                    ignore=shutil.ignore_patterns(
                        "__pycache__", "*.pyc", ".git",
                        ".gitattributes",  # 保证备份干净
                    ))
    print(f"✅ 备份完成: {backup_dir}")
    return str(backup_dir)


# ── 执行重组 ──────────────────────────────────────────────────────


def execute_restructure(plan: dict,
                        source_path: str,
                        output_path: str,
                        dry_run: bool = False) -> dict:
    """
    按计划执行项目重组。

    Args:
        plan: 重组计划 dict
        source_path: 原项目路径
        output_path: 输出项目路径
        dry_run: 如果 True，只打印不执行

    Returns:
        执行统计: {"moved": int, "created": int, "deleted": int, "merged": int, "errors": int}
    """
    src_root = Path(source_path).resolve()
    out_root = Path(output_path).resolve()
    stats = {"moved": 0, "created": 0, "deleted": 0, "merged": 0, "errors": 0}
    errors_list = []

    if not dry_run:
        out_root.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"{'🔍 模拟运行' if dry_run else '🚀 执行重组'}")
    print(f"{'=' * 60}")
    print(f"源目录: {src_root}")
    print(f"目标目录: {out_root}")
    if dry_run:
        print("（模拟模式，不会实际改动文件）")
    print()

    # ── 1. 创建目录结构 ──
    structure = plan.get("structure", {})
    _create_directory_structure(out_root, structure, dry_run)

    # ── 2. 移动/复制文件 ──
    file_moves = plan.get("file_moves", [])
    for move in file_moves:
        from_path = move.get("from", "")
        to_path = move.get("to", "")
        if not from_path or not to_path:
            continue

        src_file = src_root / from_path
        dst_file = out_root / to_path

        if not src_file.exists():
            print(f"  ⚠️  源文件不存在: {from_path}")
            stats["errors"] += 1
            errors_list.append(f"源文件不存在: {from_path}")
            continue

        if dry_run:
            print(f"  📄  {from_path}")
            print(f"       → {to_path}")
            stats["moved"] += 1
            continue

        try:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            print(f"  ✅  {from_path}")
            print(f"       → {to_path}")
            stats["moved"] += 1
        except OSError as e:
            print(f"  ❌  移动失败 {from_path}: {e}")
            stats["errors"] += 1
            errors_list.append(str(e))

    # ── 3. 创建新文件 ──
    files_to_create = plan.get("files_to_create", [])
    for item in files_to_create:
        file_path = item.get("path", "")
        content = item.get("content", "")
        if not file_path:
            continue

        dst_file = out_root / file_path
        if dry_run:
            preview = content[:60].replace("\n", " ") + ("..." if len(content) > 60 else "")
            print(f"  🆕  + {file_path}  ({preview})")
            stats["created"] += 1
            continue

        try:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            with open(dst_file, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  ✅  + {file_path}")
            stats["created"] += 1
        except OSError as e:
            print(f"  ❌  创建失败 {file_path}: {e}")
            stats["errors"] += 1
            errors_list.append(str(e))

    # ── 4. 合并文件 ──
    merges = plan.get("files_to_merge", [])
    for merge in merges:
        sources = merge.get("sources", [])
        target = merge.get("target", "")
        reason = merge.get("reason", "")
        if not sources or not target:
            continue

        if dry_run:
            print(f"  🔗  合并 {len(sources)} 个文件 → {target}  ({reason})")
            stats["merged"] += 1
            continue

        # 合并：将源文件内容聚合到一个新文件中
        dst_file = out_root / target
        merged_content = []
        merged_content.append(f"# -*- coding: utf-8 -*-\n")
        merged_content.append(f"# 合并说明: {reason}\n")
        merged_content.append(f"# 源文件: {', '.join(sources)}\n\n")

        for src_path in sources:
            src_file = src_root / src_path
            if src_file.exists():
                try:
                    with open(src_file, "r", encoding="utf-8") as f:
                        code = f.read()
                    merged_content.append(f"\n# --- 来自 {src_path} ---\n")
                    merged_content.append(code)
                except OSError as e:
                    merged_content.append(f"\n# --- 无法读取 {src_path}: {e} ---\n")
            else:
                merged_content.append(f"\n# --- {src_path} (原始文件未找到) ---\n")

        try:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            with open(dst_file, "w", encoding="utf-8") as f:
                f.write("\n".join(merged_content))
            print(f"  ✅  🔗 合并完成: {target}  ({reason})")
            stats["merged"] += 1
        except OSError as e:
            print(f"  ❌  合并失败 {target}: {e}")
            stats["errors"] += 1
            errors_list.append(str(e))

    # ── 5. 删除冗余文件（在原项目中标记，不自动删除） ──
    deletes = plan.get("files_to_delete", [])
    if deletes:
        print(f"\n🗑️  建议删除的冗余文件（{len(deletes)} 项，未自动删除）:")
        for d in deletes:
            full_path = src_root / d
            exists = "✅" if full_path.exists() else "❌"
            print(f"   {exists} {d}")

    # ── 6. 生成 __init__.py ──
    if not dry_run:
        _ensure_init_files(out_root)
        print("  ✅  已补充各目录 __init__.py")

    # ── 统计 ──
    if not dry_run:
        print(f"\n{'=' * 60}")
        print(f"📊 执行统计:")
        print(f"   移动/复制: {stats['moved']} 个文件")
        print(f"   创建新文件: {stats['created']} 个")
        print(f"   合并文件:   {stats['merged']} 组")
        if stats['errors']:
            print(f"   错误:       {stats['errors']} 个")
            for e in errors_list:
                print(f"     - {e}")

    return stats


def _create_directory_structure(root: Path, structure: dict, dry_run: bool) -> None:
    """根据计划创建目录结构"""
    dirs_to_create = []

    def _collect_dirs(prefix: str, node) -> None:
        if isinstance(node, list):
            for item in node:
                if isinstance(item, str):
                    dirs_to_create.append(os.path.join(prefix, item))
        elif isinstance(node, dict):
            for key, val in node.items():
                sub = os.path.join(prefix, key)
                if isinstance(val, (list, dict)):
                    _collect_dirs(sub, val)
                else:
                    dirs_to_create.append(sub)

    for key, val in structure.items():
        if isinstance(val, (list, dict)):
            _collect_dirs(key, val)
        else:
            dirs_to_create.append(key)

    for d in dirs_to_create:
        full = root / d
        if dry_run:
            print(f"  📁  + {d}/")
        else:
            full.mkdir(parents=True, exist_ok=True)


def _ensure_init_files(root: Path) -> None:
    """为所有包含 .py 文件的子目录补充 __init__.py（如果缺失）"""
    for dirpath, _, filenames in os.walk(root):
        has_py = any(f.endswith(".py") for f in filenames)
        if has_py:
            init_file = Path(dirpath) / "__init__.py"
            if not init_file.exists():
                with open(init_file, "w") as f:
                    f.write("# -*- coding: utf-8 -*-\n")


# ── 生成 Git 配置 ──────────────────────────────────────────────────


def generate_git_files(output_path: str, plan: dict) -> None:
    """生成 .gitignore 和 .gitattributes"""
    out_root = Path(output_path)

    # .gitignore
    gitignore_patterns = plan.get("gitignore_patterns", [])
    if not gitignore_patterns:
        gitignore_patterns = [
            "# Python",
            "__pycache__/",
            "*.py[cod]",
            "*.egg-info/",
            "dist/",
            "build/",
            "",
            "# 环境",
            ".env",
            "venv/",
            ".venv/",
            "",
            "# IDE",
            ".vscode/",
            ".idea/",
            "",
            "# OS",
            ".DS_Store",
            "Thumbs.db",
            "",
            "# Jupyter",
            ".ipynb_checkpoints/",
            "",
            "# 大文件（根据实际情况调整）",
            "*.pkl",
            "*.h5",
            "data/raw/",
        ]

    # 合并大的 data advice 中的路径
    for advice in plan.get("large_data_advice", []):
        path = advice.get("path", "")
        action = advice.get("action", "")
        if "不上传" in action or "忽略" in action:
            pattern = path.rstrip("/") + "/"
            if pattern not in gitignore_patterns:
                gitignore_patterns.append(f"\n# 大数据（建议不上传）")
                gitignore_patterns.append(pattern)

    gitignore_path = out_root / ".gitignore"
    with open(gitignore_path, "w", encoding="utf-8") as f:
        f.write("\n".join(gitignore_patterns))
    print(f"  ✅  .gitignore ({len(gitignore_patterns)} 条规则)")

    # .gitattributes
    lfs_patterns = plan.get("git_lfs_patterns", [])
    if lfs_patterns:
        gitattr_path = out_root / ".gitattributes"
        lines = ["# Git LFS 追踪规则"]
        lines.extend(f"{p} filter=lfs diff=lfs merge=lfs -text" for p in lfs_patterns)
        with open(gitattr_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  ✅  .gitattributes ({len(lfs_patterns)} 条 LFS 规则)")


# ── 打印 GitHub 指引 ──────────────────────────────────────────────


def print_github_guide(output_path: str, plan: dict) -> None:
    """打印 GitHub 上传指引"""
    name = plan.get("project_name", "my-project")
    description = plan.get("description", "")

    # 检测大目录建议
    large_advice = plan.get("large_data_advice", [])

    print("\n" + "=" * 60)
    print("🌐 GitHub 上传指引")
    print("=" * 60)
    print(f"""
你的重组项目已位于: {output_path}

上传到 GitHub:
{'-' * 40}
  cd {output_path}
  git init
  git add .
  git commit -m "Initial commit: {description}"

  # 在 GitHub 上创建仓库后:
  git remote add origin https://github.com/你的用户名/{name}.git
  git branch -M main
  git push -u origin main

{'-' * 40}
""")

    if large_advice:
        print("📦 大数据处理提醒:")
        for item in large_advice:
            print(f"  - {item.get('path', '?')} ({item.get('size_mb', '?')} MB)")
            print(f"    {item.get('action', '')}")
        print()

    print("💡 如果 .gitignore 已排除了某些大文件，直接 push 即可。")
    print("💡 对于需要追踪的大文件，先安装 Git LFS:")
    print("    git lfs install")
    print("    git lfs track \"*.csv\" \"*.pkl\"")


def print_summary(output_path: str, plan: dict, stats: dict) -> None:
    """打印最终摘要"""
    name = plan.get("project_name", "unknown")

    print("\n" + "★" * 60)
    print(f"🎉  重组完成！")
    print("★" * 60)
    print(f"""
  📦 项目:    {name}
  📂 位置:    {output_path}
  📄 移动文件: {stats.get('moved', 0)} 个
  🆕 创建文件: {stats.get('created', 0)} 个
  🔗 合并文件: {stats.get('merged', 0)} 组
  ❌ 错误:    {stats.get('errors', 0)} 个

请检查输出目录，确认结构正确后上传 GitHub。
""")


# ── 独立运行 ────────────────────────────────────────────────────────


if __name__ == "__main__":
    import sys
    from config import get_api_key, get_base_url, get_model

    # 演示用法
    print("execute_refactor.py - 直接运行需要提供 plan.json")
    print("请通过 main.py 使用完整的重组流程")
