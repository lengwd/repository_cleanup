"""
generate_readme.py
==================
README.md 自动生成模块。

使用 AI 分析项目代码，自动生成高质量的 README.md 文件。
"""

import os
import json
from pathlib import Path
from openai import OpenAI


def generate_readme(project_path: str,
                    project_name: str,
                    description: str,
                    project_info: dict | None = None,
                    api_key: str | None = None,
                    base_url: str = "https://api.deepseek.com",
                    model: str = "deepseek-chat") -> str:
    """
    为重组后的项目生成 README.md 内容。

    Args:
        project_path: 项目路径（用于读取代码）
        project_name: 项目名称
        description:  简短描述
        project_info: scan_project() 的可选结果（用于提供文件列表）
        api_key, base_url, model: API 配置

    Returns:
        README.md 完整内容
    """
    # 扫描项目文件
    if project_info is None:
        from analyze_project import scan_project
        project_info = scan_project(project_path)

    # 收集代码摘要
    py_files = project_info.get("python_files", [])
    file_snippets = []
    for f in py_files[:20]:  # 最多 20 个文件
        fpath = os.path.join(project_path, f["path"])
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
            lines = content.split("\n")
            # 只取前 30 行 + 关键函数/类定义
            snippet_lines = []
            import_section = True
            for line in lines[:80]:
                if line.startswith(("def ", "class ", "    def ", "    class ")):
                    import_section = False
                if import_section and (line.startswith("import ") or line.startswith("from ") or line == "" or line.startswith("#")):
                    snippet_lines.append(line)
                elif not import_section:
                    if len(snippet_lines) > 40:
                        break
                    snippet_lines.append(line)
            snippet = "\n".join(snippet_lines[:50])
            file_snippets.append({
                "path": f["path"],
                "lines": f["lines"],
                "snippet": snippet,
            })
        except OSError:
            pass

    # 构建 prompt
    file_list_str = "\n".join(
        f"  {f['path']} ({f['lines']} 行)" for f in py_files[:30]
    )

    code_snippets = ""
    for f in file_snippets:
        code_snippets += f"\n### {f['path']}\n```python\n{f['snippet']}\n```\n"

    prompt = f"""你是一个技术文档专家。请为以下 Python 项目生成高质量的 README.md。

## 项目信息
- 名称: {project_name}
- 描述: {description}

## 项目文件结构
{file_list_str}

## 关键代码片段
{code_snippets}

请生成完整的 README.md 内容，包含以下部分（markdown 格式）：

1. **项目标题** — 使用项目名称，加一个 Emoji
2. **一句话简介** — 项目是做什么的
3. **功能特性** — 用 Emoji 列表列出主要功能
4. **项目结构** — 树形目录说明（基于上面的文件列表）
5. **快速开始** — 安装依赖、运行示例
6. **使用说明** — 主要模块的使用方法（基于代码分析）
7. **依赖项** — requirements
8. **License** — MIT License

注意：
- 使用中文编写（专有名词保留英文）
- 不要捏造实际不存在的功能
- 目录结构基于实际文件列表
- 使用 GitHub 友好的 markdown 格式
- 在开头添加项目徽标区域（用 ASCII 艺术字或简单的 markdown）

直接返回 README.md 的内容，不要添加额外的说明。
"""

    if api_key:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=6000,
        )
        return response.choices[0].message.content
    else:
        # 无 API Key 时生成基础 README
        return _generate_basic_readme(project_name, description, py_files)


def _generate_basic_readme(project_name: str,
                           description: str,
                           py_files: list[dict]) -> str:
    """无 AI 时的基础 README 模板"""
    lines = [
        f"# {project_name}",
        "",
        f"> {description}",
        "",
        "## 项目结构",
        "",
        "```",
        f"{project_name}/",
    ]
    for f in py_files:
        lines.append(f"├── {f['path']}")
    lines.append("```")
    lines.append("")
    lines.append("## 安装")
    lines.append("")
    lines.append("```bash")
    lines.append("pip install -r requirements.txt")
    lines.append("```")
    lines.append("")
    lines.append("## License")
    lines.append("")
    lines.append("MIT License")
    return "\n".join(lines)


def save_readme(output_path: str, content: str) -> Path:
    """将 README 内容保存到文件"""
    readme_path = Path(output_path) / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✅  README.md 已生成")
    return readme_path


def generate_and_save(project_path: str,
                       output_path: str,
                       project_name: str,
                       description: str,
                       api_key: str | None = None,
                       base_url: str = "https://api.deepseek.com",
                       model: str = "deepseek-chat") -> Path:
    """便捷函数：生成并保存 README"""
    content = generate_readme(
        project_path=project_path,
        project_name=project_name,
        description=description,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    return save_readme(output_path, content)


# ── 独立运行 ────────────────────────────────────────────────────────


if __name__ == "__main__":
    import sys
    from config import get_api_key, get_base_url, get_model

    path = sys.argv[1] if len(sys.argv) > 1 else input("请输入项目路径: ").strip()
    name = sys.argv[2] if len(sys.argv) > 2 else input("请输入项目名称: ").strip()
    desc = sys.argv[3] if len(sys.argv) > 3 else input("请输入项目描述: ").strip()

    api_key = get_api_key()
    if not api_key:
        api_key = input("请输入 API Key (直接回车则生成基础 README): ").strip() or None
    base_url = get_base_url()
    model = get_model()

    content = generate_readme(
        project_path=path,
        project_name=name,
        description=desc,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    print("\n" + "=" * 60)
    print(content)
    print("=" * 60)

    save = input("\n保存到 README.md？(Y/n): ").strip().lower()
    if save != "n":
        out = Path(path) / "README.md"
        with open(out, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 已保存到: {out}")
