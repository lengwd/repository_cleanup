"""
git_helper.py
==============
Git 上传助手 — 每次更新后运行，询问是否提交并推送到 Git。

用法:
  python git_helper.py                    # 交互式（推荐）
  python git_helper.py -m "提交信息"       # 跳过提交信息输入
  python git_helper.py --push             # 提交后自动推送（不询问）
  python git_helper.py --dry-run          # 只查看变更，不执行任何操作
"""

import subprocess
import sys
import os
from pathlib import Path


# ── 工具函数 ──────────────────────────────────────────────────────────


def run(cmd: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    """执行命令，可选择捕获输出"""
    kwargs = {}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    return subprocess.run(cmd, **kwargs)


def get_status() -> str:
    """获取 git status 输出"""
    result = run(["git", "status", "--short"], capture=True)
    return result.stdout.strip()


def get_diff_stat() -> str:
    """获取变更文件的统计信息"""
    result = run(["git", "diff", "--stat"], capture=True)
    staged = run(["git", "diff", "--stat", "--cached"], capture=True)
    parts = [s for s in [result.stdout.strip(), staged.stdout.strip()] if s]
    return "\n".join(parts) if parts else "（无变更）"


def get_branch() -> str:
    """获取当前分支名"""
    result = run(["git", "branch", "--show-current"], capture=True)
    return result.stdout.strip()


def has_remote() -> bool:
    """检查是否有远程仓库"""
    result = run(["git", "remote"], capture=True)
    return result.stdout.strip() != ""


def has_changes() -> bool:
    """检查是否有未提交的变更（工作区 + 暂存区）"""
    # 工作区变更
    r1 = run(["git", "diff", "--stat"], capture=True)
    # 暂存区变更
    r2 = run(["git", "diff", "--stat", "--cached"], capture=True)
    return bool(r1.stdout.strip() or r2.stdout.strip())


def has_unpushed() -> bool:
    """检查是否有未推送的提交"""
    branch = get_branch()
    if not branch:
        return False
    # 检查是否有 upstream 分支
    upstream = run(["git", "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"],
                   capture=True)
    if upstream.returncode != 0:
        return False  # 没有 upstream，不算未推送
    result = run(["git", "cherry", "-v", f"origin/{branch}"], capture=True)
    return bool(result.stdout.strip())


def print_header(title: str) -> None:
    """打印带装饰的标题"""
    width = 60
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def confirm(prompt_msg: str, default: bool = True) -> bool:
    """交互式 Y/n 或 y/N 确认"""
    hint = "Y/n" if default else "y/N"
    while True:
        answer = input(f"  {prompt_msg} [{hint}] ").strip().lower()
        if answer == "":
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print(f"  请输入 y 或 n")


# ── 核心流程 ──────────────────────────────────────────────────────────


def show_changes() -> None:
    """显示当前变更概览"""
    branch = get_branch()
    status_text = get_status()
    diff_text = get_diff_stat()

    print(f"  分支: {branch}")
    print()
    if status_text:
        print(f"  📋 变更文件:")
        for line in status_text.split("\n"):
            # 标记不同的状态
            if line.startswith("?"):
                marker = "🆕"
            elif line.startswith("M") or line.startswith(" M"):
                marker = "📝"
            elif line.startswith("D"):
                marker = "🗑️"
            elif line.startswith("R"):
                marker = "🚚"
            elif line.startswith("A"):
                marker = "➕"
            else:
                marker = "  "
            print(f"    {marker}  {line}")
    else:
        print("  ✅ 没有未跟踪或修改的文件")

    print()
    print(f"  📊 变更统计:")
    for line in diff_text.split("\n"):
        print(f"    {line}")


def do_commit(message: str | None = None) -> bool:
    """执行 git add + commit"""
    if message:
        # 直接提交
        r1 = run(["git", "add", "--all"])
        if r1.returncode != 0:
            print("  ❌ git add 失败")
            return False
        r2 = run(["git", "commit", "-m", message])
        if r2.returncode == 0:
            print(f"  ✅ 提交成功: {message}")
            return True
        else:
            print("  ❌ 提交失败（可能是没有变更）")
            return False

    # 交互式提交
    print()
    print("  📝 输入提交信息（空行 = 取消提交，输入 = 直接提交）")
    lines = []
    while True:
        line = input("    > ").strip()
        if not line:
            break
        lines.append(line)

    if not lines:
        print("  ⏭️  已取消提交")
        return False

    msg = "\n".join(lines)
    r1 = run(["git", "add", "--all"])
    if r1.returncode != 0:
        print("  ❌ git add 失败")
        return False
    r2 = run(["git", "commit", "-m", msg])
    if r2.returncode == 0:
        print(f"  ✅ 提交成功")
        return True
    else:
        print("  ❌ 提交失败（可能是没有变更）")
        return False


def do_push() -> bool:
    """执行 git push"""
    if not has_remote():
        print("  ⚠️  没有配置远程仓库，跳过推送")
        return False

    branch = get_branch()
    print(f"  📤 正在推送到 origin/{branch} ...")
    result = run(["git", "push"])
    if result.returncode == 0:
        print(f"  ✅ 推送成功")
        return True
    else:
        print("  ❌ 推送失败，请检查远程仓库配置")
        return False


# ── 主入口 ────────────────────────────────────────────────────────────


def main() -> None:
    # 参数解析
    args = sys.argv[1:]
    auto_message = None
    auto_push = False
    dry_run = False

    for i, arg in enumerate(args):
        if arg == "-m" and i + 1 < len(args):
            auto_message = args[i + 1]
        elif arg == "--push":
            auto_push = True
        elif arg == "--dry-run":
            dry_run = True

    # 检查是否在 git 仓库中
    if not os.path.isdir(".git") and run(["git", "rev-parse", "--git-dir"], capture=True).returncode != 0:
        print("❌ 当前目录不是 Git 仓库，请先 git init")
        sys.exit(1)

    print_header("🔄 Git 上传助手")

    # 第一步：显示变更
    show_changes()

    if dry_run:
        print()
        print("  🔍 --dry-run 模式，未执行任何操作")
        return

    # 第二步：检查是否有变更
    if not has_changes():
        print()
        print("  ✅ 没有未提交的变更")

        # 检查是否有未推送的内容
        if has_unpushed():
            print("  📤 有未推送的提交")
            if not auto_push and confirm("是否推送?", default=True):
                do_push()
            elif auto_push:
                do_push()
        else:
            print("  ✅ 所有内容已同步到远程仓库")

        return

    # 第三步：询问是否提交
    print()
    if not confirm("是否提交这些变更?", default=True):
        print("  ⏭️  已跳过提交")
        return

    success = do_commit(auto_message)
    if not success:
        return

    # 第四步：询问是否推送
    if not has_remote():
        print()
        print("  💡 提示: 没有配置远程仓库")
        print(f"     可用 git remote add origin <url> 添加")
        return

    if auto_push:
        do_push()
        return

    print()
    if confirm("是否推送到远程仓库?", default=True):
        do_push()
    else:
        print("  ⏭️  已跳过推送，下次可手动 git push")

    print()
    print("  ✨ 完成！")


if __name__ == "__main__":
    main()
