"""
analyze_project.py
==================
项目扫描与 AI 分析模块。

功能:
  1. scan_project()       - 扫描目录结构、文件大小、行数
  2. detect_large_dirs()  - 检测大目录/大文件（用于 Git LFS 提示）
  3. analyze_with_ai()    - 将代码片段发给 DeepSeek 做架构分析
  4. analyze_project()    - 上面三合一的便捷入口
"""

import os
import json
from pathlib import Path
from openai import OpenAI

# 默认排除的目录/文件
EXCLUDE_DIRS = {
    "__pycache__", ".git", ".svn", ".idea", ".vscode",
    "node_modules", "venv", ".venv", "env", ".env",
    "wandb", "runs", "logs", "dist", "build", "*.egg-info",
}
EXCLUDE_EXTENSIONS = {".pyc", ".pyo", ".so", ".dll", ".dylib"}
# 大目录阈值（MB）
LARGE_DIR_THRESHOLD_MB = 50
# 大文件阈值（MB）
LARGE_FILE_THRESHOLD_MB = 10


# ── 扫描 ──────────────────────────────────────────────────────────


def scan_project(project_path: str) -> dict:
    """
    扫描项目目录，返回结构化信息。

    Returns:
        {
            "project_path": str,
            "total_files": int,
            "total_size_mb": float,
            "python_files": [{"path": relative, "size_kb": float, "lines": int}],
            "other_files": [{"path": relative, "size_kb": float}],
            "all_dirs": [relative, ...],
            "dir_tree": str (文本树)
        }
    """
    root = Path(project_path).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"路径不存在或不是目录: {project_path}")

    py_files = []
    other_files = []
    all_dirs = set()
    total_size = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # 排除不需要的目录（原地修改 dirnames 以阻止 os.walk 进入）
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]

        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir != ".":
            all_dirs.add(rel_dir)

        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                fsize = os.path.getsize(fpath)
            except OSError:
                continue
            total_size += fsize
            rel_path = os.path.relpath(fpath, root)

            ext = os.path.splitext(fname)[1].lower()
            if fname.endswith(".py"):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        lines = sum(1 for _ in f)
                except OSError:
                    lines = 0
                py_files.append({
                    "path": rel_path,
                    "size_kb": round(fsize / 1024, 2),
                    "lines": lines,
                })
            elif ext not in EXCLUDE_EXTENSIONS:
                other_files.append({
                    "path": rel_path,
                    "size_kb": round(fsize / 1024, 2),
                })

    # 排序
    py_files.sort(key=lambda x: x["path"])
    other_files.sort(key=lambda x: x["path"])

    # 目录树文本
    dir_tree = _build_dir_tree(root, py_files + other_files)

    return {
        "project_path": str(root),
        "total_files": len(py_files) + len(other_files),
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "py_file_count": len(py_files),
        "python_files": py_files,
        "other_files": other_files,
        "all_dirs": sorted(all_dirs),
        "dir_tree": dir_tree,
    }


def _build_dir_tree(root: Path, all_files: list[dict]) -> str:
    """构建简单的目录树文本"""
    root_str = str(root)
    lines = [f"{root.name}/"]
    # 收集所有目录
    dirs: dict[str, list[str]] = {}
    for f in all_files:
        p = f["path"]
        d = os.path.dirname(p) if os.path.dirname(p) else "."
        dirs.setdefault(d, []).append(os.path.basename(p))

    sorted_dirs = sorted(dirs.keys())
    for i, d in enumerate(sorted_dirs):
        is_last_dir = i == len(sorted_dirs) - 1
        prefix = "└── " if is_last_dir else "├── "
        if d == ".":
            # 根目录下的文件
            for j, fname in enumerate(sorted(dirs[d])):
                connector = "└── " if j == len(dirs[d]) - 1 else "├── "
                lines.append(f"{'    ' if is_last_dir else '│   '}{connector}{fname}")
        else:
            lines.append(f"{prefix}{d}/")
            sub_files = sorted(dirs[d])
            for j, fname in enumerate(sub_files):
                connector = "└── " if j == len(sub_files) - 1 else "├── "
                indent = "    " if is_last_dir else "│   "
                lines.append(f"{indent}{'    ' if is_last_dir else '│   '}{connector}{fname}")
    return "\n".join(lines)


# ── 大目录检测 ─────────────────────────────────────────────────────


def detect_large_dirs(project_path: str,
                      threshold_mb: int = LARGE_DIR_THRESHOLD_MB) -> list[dict]:
    """
    检测超过阈值的大目录。

    Returns:
        [{"path": relative, "size_mb": float, "file_count": int, "suggestion": str}, ...]
    """
    root = Path(project_path).resolve()
    large_dirs = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            continue

        total_size = 0
        file_count = 0
        for fname in filenames:
            try:
                total_size += os.path.getsize(os.path.join(dirpath, fname))
                file_count += 1
            except OSError:
                pass

        size_mb = total_size / 1024 / 1024
        if size_mb > threshold_mb and file_count > 1:
            suggestion = _suggest_for_size(size_mb)
            large_dirs.append({
                "path": rel_dir,
                "size_mb": round(size_mb, 2),
                "file_count": file_count,
                "suggestion": suggestion,
            })

    large_dirs.sort(key=lambda x: x["size_mb"], reverse=True)
    return large_dirs


def detect_large_files(project_path: str,
                       threshold_mb: int = LARGE_FILE_THRESHOLD_MB) -> list[dict]:
    """检测超过阈值的大文件"""
    root = Path(project_path).resolve()
    large_files = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                size = os.path.getsize(fpath)
            except OSError:
                continue
            size_mb = size / 1024 / 1024
            if size_mb > threshold_mb:
                rel = os.path.relpath(fpath, root)
                large_files.append({
                    "path": rel,
                    "size_mb": round(size_mb, 2),
                    "suggestion": _suggest_for_size(size_mb),
                })
    return large_files


def _suggest_for_size(size_mb: float) -> str:
    if size_mb > 500:
        return "⚠️  极大文件/目录，建议不上传 Git，使用 DVC 或云存储"
    if size_mb > 100:
        return "📦 建议使用 Git LFS 跟踪，或添加到 .gitignore"
    if size_mb > 50:
        return "📦 建议使用 Git LFS 跟踪"
    return "📁 较大，考虑是否需要上传"


# ── AI 分析 ───────────────────────────────────────────────────────


def analyze_with_ai(project_info: dict,
                    api_key: str,
                    base_url: str = "https://api.deepseek.com",
                    model: str = "deepseek-v4-pro",
                    max_chars: int = 100000) -> str:
    """
    将项目信息发给 DeepSeek，获取架构分析结果。

    自适应读取：
      在 max_chars 字符预算内，按文件行数升序（小文件优先）读取，
      预算够则全量读取，预算不够则截断当前文件并停止。
      这样小项目可以读到全部代码，大项目也能在预算内覆盖最多文件。

    Returns:
        AI 的原始回复文本（含 JSON）。
    """
    client = OpenAI(api_key=api_key, base_url=base_url)

    py_files = project_info["python_files"]
    file_summary_parts = []
    remaining = max_chars

    # 按行数升序排列（小文件优先），在预算内覆盖尽可能多的文件
    for f in sorted(py_files, key=lambda x: x["lines"]):
        if remaining <= 0:
            break

        fpath = os.path.join(project_info["project_path"], f["path"])
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
        except OSError:
            content = ""

        header = f"\n### 文件: {f['path']} ({f['lines']} 行, {f['size_kb']} KB)\n```python\n"
        footer = "\n```"
        overhead = len(header) + len(footer)

        if overhead >= remaining:
            # 连 header 都放不下了，跳过
            continue

        if overhead + len(content) <= remaining:
            # 预算充足 → 全量读取
            snippet = content
            remaining -= overhead + len(content)
        else:
            # 预算不够完整文件 → 截断，读完本次就结束
            available = remaining - overhead
            lines = content.split("\n")
            snippet_lines = []
            char_count = 0
            for line in lines:
                take = len(line) + 1  # +1 for newline
                if char_count + take > available:
                    break
                snippet_lines.append(line)
                char_count += take
            omitted = len(lines) - len(snippet_lines)
            snippet = "\n".join(snippet_lines)
            if omitted > 0:
                snippet += f"\n# ... (省略 {omitted} 行)"
            remaining = 0

        file_summary_parts.append(f"{header}{snippet}{footer}")

    file_summary = "\n".join(file_summary_parts)
    print(f"  📖 已读取 {len(file_summary_parts)}/{len(py_files)} 个 Python 文件"
          f"（字符预算 {max_chars:,}，已用 {max_chars - remaining:,}）")
    dir_tree = project_info.get("dir_tree", "")
    large_data = project_info.get("large_data_info", "无")

    prompt = f"""你是一个Python项目架构专家。请分析以下项目的代码结构。

## 📁 项目目录树
```
{dir_tree}
```

## 📊 项目概览
- 总文件数: {project_info['total_files']}
- Python文件数: {project_info['py_file_count']}
- 总大小: {project_info['total_size_mb']} MB

## 🗃️ 大目录/大文件提示（需重点关注）
{large_data}

## 📄 Python 文件代码片段
{file_summary}

请提供：

1. **项目名称建议** — 适合 GitHub 的英文名称（短横线命名）
2. **项目功能描述** — 2~3 句话说明项目做什么
3. **核心技术栈** — 依赖的主要库/框架
4. **重复代码识别** — 哪些文件功能相似可以合并
5. **建议目录结构** — 适合 GitHub 的标准 Python 项目结构（用树形文本表示）
6. **文件迁移映射** — 每个原文件应移动到新结构的哪个位置
7. **可删除的冗余文件** — 无用的测试、备份、临时文件
8. **大数据处理建议** — 对超过 10MB 的目录给出具体上传策略

请以 **严格的 JSON 格式** 返回结果，不要包裹 markdown 代码块。格式如下：
{{
    "project_name": "建议的项目名",
    "description": "项目功能描述",
    "tech_stack": ["库1", "库2"],
    "duplicate_files": [{{"files": ["a.py", "b.py"], "reason": "重复原因", "merge_into": "合并后的文件路径"}}],
    "suggested_structure": {{
        "project_root": "new-project-name",
        "tree_text": "目录树文本",
        "directories": ["dir1", "dir2"]
    }},
    "file_moves": [
        {{"from": "原路径", "to": "新路径", "reason": "移动原因"}}
    ],
    "files_to_delete": ["冗余文件路径"],
    "files_to_create": [
        {{"path": "新文件路径", "reason": "为什么创建"}}
    ],
    "large_data_advice": [
        {{"path": "数据目录", "size_mb": 123, "action": "建议操作"}}
    ],
    "gitignore_patterns": ["模式1", "模式2"],
    "git_lfs_patterns": ["*.csv", "*.pkl"]
}}
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=8000,
            response_format={"type": "json_object"},
        )
    except Exception:
        # 降级：API 不支持 response_format 时重试
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=8000,
        )
    return response.choices[0].message.content


# ── 合一入口 ───────────────────────────────────────────────────────


def analyze_project(project_path: str,
                    api_key: str,
                    base_url: str = "https://api.deepseek.com",
                    model: str = "deepseek-v4-pro",
                    max_chars: int = 100000) -> tuple[dict, dict, str]:
    """
    扫描 + 大目录检测 + AI 分析（自适应读取）。

    Args:
        project_path: 项目路径
        api_key: API 密钥
        base_url: API 地址
        model: 模型名
        max_chars: 代码读取的字符预算（默认 100k，小项目可全量读取）

    Returns:
        (project_info, large_items, ai_reply)
    """
    print(f"📂 扫描项目: {project_path}")
    project_info = scan_project(project_path)
    print(f"   找到 {project_info['py_file_count']} 个 Python 文件，"
          f"共 {project_info['total_files']} 个文件，"
          f"总大小 {project_info['total_size_mb']} MB")

    print("\n🔍 检测大目录/大文件...")
    large_dirs = detect_large_dirs(project_path)
    large_files = detect_large_files(project_path)

    # 组装大文件信息
    large_info_parts = []
    if large_dirs:
        large_info_parts.append("【大目录】")
        for d in large_dirs:
            large_info_parts.append(f"  - {d['path']}: {d['size_mb']} MB ({d['file_count']} 文件) {d['suggestion']}")
            print(f"   📁 {d['path']}: {d['size_mb']} MB {d['suggestion']}")
    if large_files:
        large_info_parts.append("【大文件】")
        for f in large_files:
            large_info_parts.append(f"  - {f['path']}: {f['size_mb']} MB {f['suggestion']}")
            print(f"   📄 {f['path']}: {f['size_mb']} MB {f['suggestion']}")

    project_info["large_data_info"] = "\n".join(large_info_parts) if large_info_parts else "无"

    print(f"\n🤖 AI 分析中（{model}，代码字符预算 {max_chars:,}）...")
    ai_reply = analyze_with_ai(project_info, api_key, base_url, model, max_chars)
    print("   ✅ AI 分析完成")

    large_items = {
        "large_dirs": large_dirs,
        "large_files": large_files,
    }
    return project_info, large_items, ai_reply


# ── 独立运行 ────────────────────────────────────────────────────────


if __name__ == "__main__":
    import sys
    from config import get_api_key, get_base_url, get_model

    path = sys.argv[1] if len(sys.argv) > 1 else input("请输入项目路径: ").strip()
    api_key = get_api_key()
    if not api_key:
        api_key = input("请输入 DeepSeek API Key: ").strip()
    base_url = get_base_url()
    model = get_model()

    info, large, ai = analyze_project(path, api_key, base_url, model)
    print("\n" + "=" * 60)
    print("AI 分析结果:")
    print(ai)
    print("=" * 60)

    # 保存结果
    out_path = Path.cwd() / "analysis_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"project_info": info, "large_items": large, "ai_analysis": ai},
                  f, ensure_ascii=False, indent=2)
    print(f"\n✅ 完整结果已保存到: {out_path}")
