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
# AI 分析代码读取字符预算（默认 300k，约覆盖 100+ 个文件各读一部分）
MAX_CHARS = 300000


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


# ── 大文件深度分类 ──────────────────────────────────────────────────

# 扩展名 → (类别标签, 中文描述)
_FILE_CATEGORIES = {
    # 模型检查点
    ".ckpt":        ("checkpoint", "模型检查点"),
    ".pt":          ("checkpoint", "PyTorch 模型权重"),
    ".pth":         ("checkpoint", "PyTorch 模型权重"),
    ".safetensors": ("checkpoint", "SafeTensors 模型权重"),
    ".bin":         ("checkpoint", "模型权重 (常见于 HuggingFace)"),
    # 训练好的模型文件
    ".pkl":         ("model",     "序列化模型/对象"),
    ".h5":          ("model",     "HDF5 模型/数据"),
    ".hdf5":        ("model",     "HDF5 模型/数据"),
    ".keras":       ("model",     "Keras 模型"),
    ".tflite":      ("model",     "TFLite 模型"),
    ".onnx":        ("model",     "ONNX 模型"),
    ".pb":          ("model",     "TensorFlow 模型"),
    # 数据集
    ".csv":         ("dataset",   "CSV 数据"),
    ".jsonl":       ("dataset",   "JSONL 数据"),
    ".parquet":     ("dataset",   "Parquet 数据"),
    ".npy":         ("dataset",   "NumPy 数组"),
    ".npz":         ("dataset",   "NumPy 压缩数据"),
    ".tfrecord":    ("dataset",   "TFRecord 数据"),
    ".arrow":       ("dataset",   "Arrow 数据 (常见于 HuggingFace Datasets)"),
    # 媒体文件
    ".jpg":         ("media",     "图片"),
    ".jpeg":        ("media",     "图片"),
    ".png":         ("media",     "图片"),
    ".mp4":         ("media",     "视频"),
    ".avi":         ("media",     "视频"),
    ".wav":         ("media",     "音频"),
    ".mp3":         ("media",     "音频"),
}

# 已知可下载的模型/数据集 → 下载来源
_KNOWN_DOWNLOADS = [
    # (文件名/路径片段, 名称, 下载来源)
    ("pytorch_model.bin",      "HuggingFace 预训练模型",    "https://huggingface.co/"),
    ("model.safetensors",      "HuggingFace 预训练模型",    "https://huggingface.co/"),
    ("tf_model.h5",            "HuggingFace 预训练模型",    "https://huggingface.co/"),
    ("resnet",                 "ResNet 预训练模型",         "https://pytorch.org/vision/stable/models.html"),
    ("resnext",                "ResNeXt 预训练模型",        "https://pytorch.org/vision/stable/models.html"),
    ("vgg",                    "VGG 预训练模型",            "https://pytorch.org/vision/stable/models.html"),
    ("vit",                    "ViT 预训练模型",            "https://huggingface.co/models"),
    ("yolo",                   "YOLO 模型",                 "https://github.com/ultralytics/ultralytics"),
    ("bert",                   "BERT 预训练模型",           "https://huggingface.co/google-bert"),
    ("gpt2",                   "GPT-2 预训练模型",          "https://huggingface.co/gpt2"),
    ("gpt",                    "GPT 预训练模型",            "https://huggingface.co/openai-gpt"),
    ("llama",                  "LLaMA 预训练模型",          "https://huggingface.co/meta-llama"),
    ("whisper",                "Whisper 模型",              "https://github.com/openai/whisper"),
    ("clip",                   "CLIP 模型",                 "https://huggingface.co/openai/clip-vit-base-patch32"),
    ("sam",                    "SAM 分割模型",              "https://github.com/facebookresearch/sam"),
    ("coco",                   "COCO 数据集",               "https://cocodataset.org/"),
    ("imagenet",               "ImageNet 数据集",           "https://www.image-net.org/"),
    ("mnist",                  "MNIST 数据集",              "https://yann.lecun.com/exdb/mnist/"),
    ("cifar10",                "CIFAR-10 数据集",           "https://www.cs.toronto.edu/~kriz/cifar.html"),
    ("cifar100",               "CIFAR-100 数据集",          "https://www.cs.toronto.edu/~kriz/cifar.html"),
    ("squad",                  "SQuAD 数据集",              "https://rajpurkar.github.io/SQuAD-explorer/"),
    ("glove",                  "GloVe 词向量",              "https://nlp.stanford.edu/projects/glove/"),
    ("word2vec",               "Word2Vec 词向量",           "https://code.google.com/archive/p/word2vec/"),
    ("efficientnet",           "EfficientNet 预训练模型",   "https://pytorch.org/vision/stable/models.html"),
    ("mobilenet",              "MobileNet 预训练模型",      "https://pytorch.org/vision/stable/models.html"),
    ("densenet",               "DenseNet 预训练模型",       "https://pytorch.org/vision/stable/models.html"),
    ("inception",              "Inception 预训练模型",      "https://pytorch.org/vision/stable/models.html"),
    ("unet",                   "UNet 模型",                 "https://github.com/milesial/Pytorch-UNet"),
    ("swin",                   "Swin Transformer 模型",     "https://github.com/microsoft/Swin-Transformer"),
]


def classify_large_file(file_info: dict, project_path: str) -> dict:
    """
    对单个大文件进行深度分类分析。

    Returns:
        在 file_info 基础上补充:
        - category: 类别标签 (checkpoint / model / dataset / media / other)
        - category_desc: 中文描述
        - is_downloadable: 是否可以从网上下载
        - download_name: 可下载对象的名称
        - download_source: 下载来源 URL
        - is_checkpoint_group: checkpoint 所属组名 (None 表示不是 checkpoint)
        - is_checkpoint_keeper: 是否为该组应保留的 checkpoint
    """
    name = os.path.basename(file_info["path"])
    ext = os.path.splitext(name)[1].lower()
    full_path = file_info["path"].replace("\\", "/")

    result = dict(file_info)  # 浅拷贝
    result["category"] = "other"
    result["category_desc"] = "其他文件"
    result["is_downloadable"] = False
    result["download_name"] = None
    result["download_source"] = None
    result["is_checkpoint_group"] = None
    result["is_checkpoint_keeper"] = None

    # 1. 按扩展名分类
    if ext in _FILE_CATEGORIES:
        cat, desc = _FILE_CATEGORIES[ext]
        result["category"] = cat
        result["category_desc"] = desc
    else:
        # 通过文件名模式猜测
        lower = name.lower()
        if any(kw in lower for kw in ["checkpoint", "epoch", "model_", "weight"]):
            result["category"] = "checkpoint"
            result["category_desc"] = "模型检查点 (按名称推测)"

    # 2. 检查是否是已知可下载的模型/数据集
    norm_path = full_path.lower()
    for fragment, dname, source in _KNOWN_DOWNLOADS:
        if fragment in norm_path:
            result["is_downloadable"] = True
            result["download_name"] = dname
            result["download_source"] = source
            break

    return result


def analyze_checkpoints(classified_files: list[dict]) -> list[dict]:
    """
    对 checkpoint 类文件分组分析，标记哪些应保留。

    分组规则：按目录分组 + 按文件名校验。
    保留规则：名字含 best / final / latest 的保留；
              有 epoch/step 编号的只保留编号最大的；
              单文件组直接保留。
    """
    # 过滤出 checkpoint，按目录分组
    ckpt_groups: dict[str, list[dict]] = {}
    for f in classified_files:
        if f.get("category") != "checkpoint":
            continue
        path = f["path"].replace("\\", "/")
        group_key = os.path.dirname(path) or "/"
        ckpt_groups.setdefault(group_key, []).append(f)

    # 对每组进行分析
    for group_dir, files in ckpt_groups.items():
        if len(files) == 1:
            # 单文件 → 总是保留
            files[0]["is_checkpoint_group"] = group_dir
            files[0]["is_checkpoint_keeper"] = True
            continue

        # 多文件 → 识别 keepers
        keepers: set[int] = set()
        seen_names = set()

        for i, f in enumerate(files):
            fname = os.path.basename(f["path"]).lower()
            f["is_checkpoint_group"] = group_dir

            # 命名包含 best / final / latest → 保留
            if any(kw in fname for kw in ["best", "final", "latest"]):
                keepers.add(i)

        # 按编号模式找最大号（epoch_*, step_*, checkpoint-*）
        import re
        epoch_groups: dict[str, list[tuple[int, int]]] = {}
        for i, f in enumerate(files):
            if i in keepers:
                continue
            fname = os.path.basename(f["path"]).lower()
            # 匹配 epoch_N / step_N / checkpoint-N / _N.ckpt 等
            for pattern in [
                r"epoch[_\s]*(\d+)", r"step[_\s]*(\d+)",
                r"checkpoint[_\s-]*(\d+)", r"_(\d+)\.\w+$",
            ]:
                m = re.search(pattern, fname)
                if m:
                    num = int(m.group(1))
                    base = re.sub(r"_\d+", "_XX", fname, count=1)
                    epoch_groups.setdefault(base, []).append((num, i))
                    break

        # 每组编号只保留最大的
        for base, entries in epoch_groups.items():
            entries.sort(key=lambda x: x[0], reverse=True)
            keepers.add(entries[0][1])  # 最大号保留

        # 如果 keepers 为空 → 全部保留（安全兜底）
        if not keepers:
            keepers = set(range(len(files)))

        for i, f in enumerate(files):
            f["is_checkpoint_keeper"] = i in keepers

    return classified_files


def analyze_large_files_deep(large_files: list[dict],
                             project_path: str) -> list[dict]:
    """
    对大文件列表进行深度分析：分类、识别可下载项、分析 checkpoint。

    Args:
        large_files: detect_large_files() 的结果
        project_path: 项目路径

    Returns:
        经过 enrich 的文件列表，每项新增:
        category, category_desc, is_downloadable,
        download_name, download_source,
        is_checkpoint_group, is_checkpoint_keeper
    """
    # 第一步：逐个分类
    classified = [classify_large_file(f, project_path) for f in large_files]

    # 第二步：checkpoint 分组分析
    classified = analyze_checkpoints(classified)

    return classified


# ── AI 分析 ───────────────────────────────────────────────────────


def analyze_with_ai(project_info: dict,
                    api_key: str,
                    base_url: str = "https://api.deepseek.com",
                    model: str = "deepseek-v4-pro",
                    max_chars: int = 300000) -> str:
    """
    将项目信息发给 DeepSeek，获取架构分析结果。

    自适应读取：
      两阶段策略：
        阶段1 — 小文件优先全量读取
        阶段2 — 如果全量读不完，剩余预算在所有未读文件之间平分，
                确保每个文件至少贡献开头若干行，让 AI 看到全貌。

    Returns:
        AI 的原始回复文本（含 JSON）。
    """
    client = OpenAI(api_key=api_key, base_url=base_url)

    py_files = project_info["python_files"]
    file_summary_parts: list[str] = []
    remaining = max_chars

    # 按行数升序排列（小文件优先）
    sorted_files = sorted(py_files, key=lambda x: x["lines"])

    # ── 阶段1：小文件优先全量读取 ──
    pending = []  # 未读文件索引（阶段2处理）
    for idx, f in enumerate(sorted_files):
        header = (f"\n### 文件: {f['path']} ({f['lines']} 行, {f['size_kb']} KB)"
                  f"\n```python\n")
        footer = "\n```"
        overhead = len(header) + len(footer)

        if overhead >= remaining:
            pending.append(idx)
            continue

        # 先尝试读文件内容
        fpath = os.path.join(project_info["project_path"], f["path"])
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
        except OSError:
            content = ""

        total = overhead + len(content)
        if total <= remaining:
            # 全量放入
            file_summary_parts.append(f"{header}{content}{footer}")
            remaining -= total
        else:
            # 放不下了 → 先存起来，阶段2统一截断分配
            pending.append(idx)

    # ── 阶段2：剩余预算平分给所有未读文件，每个至少截取开头 ──
    if pending and remaining > 0:
        # 每个文件有固定开销（header + footer），从剩余中扣除
        overheads = []
        for idx in pending:
            f = sorted_files[idx]
            h = (f"\n### 文件: {f['path']} ({f['lines']} 行, {f['size_kb']} KB)"
                 f"\n```python\n")
            overheads.append(len(h) + 4)  # +4 for \n```\n

        total_overhead = sum(overheads)
        if total_overhead >= remaining:
            # 连 header 都放不下所有文件 → 能放几个是几个
            budget_per_file = 0
        else:
            budget_per_file = (remaining - total_overhead) // len(pending)

        for i, idx in enumerate(pending):
            f = sorted_files[idx]
            fpath = os.path.join(project_info["project_path"], f["path"])
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                    content = fp.read()
            except OSError:
                content = ""

            header = (f"\n### 文件: {f['path']} ({f['lines']} 行, {f['size_kb']} KB)"
                      f"\n```python\n")
            footer = "\n```"

            if budget_per_file <= 0:
                # 只放 header + 首行（示意）
                lines = content.split("\n")
                snippet = (lines[0] + "\n# ... (预算不足，仅展示首行)"
                           if lines else "")
            else:
                lines = content.split("\n")
                snippet_lines = []
                char_count = 0
                for line in lines:
                    take = len(line) + 1
                    if char_count + take > budget_per_file:
                        break
                    snippet_lines.append(line)
                    char_count += take
                omitted = len(lines) - len(snippet_lines)
                snippet = "\n".join(snippet_lines)
                if omitted > 0:
                    snippet += f"\n# ... (省略 {omitted} 行)"

            file_summary_parts.append(f"{header}{snippet}{footer}")

    file_summary = "\n".join(file_summary_parts)
    read_count = len(file_summary_parts)
    print(f"  📖 已读取 {read_count}/{len(py_files)} 个 Python 文件"
          f"（字符预算 {max_chars:,}，已用 {max_chars - remaining:,}）")
    if pending:
        print(f"      其中 {len(pending)} 个因预算不足截断读取")
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
                    max_chars: int = 300000) -> tuple[dict, dict, str]:
    """
    扫描 + 大目录检测 + AI 分析（自适应读取）。

    Args:
        project_path: 项目路径
        api_key: API 密钥
        base_url: API 地址
        model: 模型名
        max_chars: 代码读取的字符预算（默认 300k，全量读完 100+ 文件也绰绰有余）

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
