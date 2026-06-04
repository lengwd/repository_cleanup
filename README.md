# 🚀 GitHub-Ready 老旧代码重组工具

> **一键分析、重组老旧 Python 项目，生成可直接上传 GitHub 的友好目录结构**

## 📖 简介

你手上有一些历史悠久的 Python 项目，代码散乱、目录结构不清晰、没有 README、没有 `.gitignore`，想上传到 GitHub 但觉得拿不出手？

这个工具就是为此而生：

1. **扫描**你的项目目录，了解全貌
2. 调用 **AI（DeepSeek）** 分析代码结构和功能
3. **自动生成**适合 GitHub 的标准目录结构 + 文件迁移方案
4. **创建备份**后执行重组（零风险）
5. 生成 **README.md / .gitignore / requirements.txt**
6. 打印 **GitHub 上传指引**

整个过程**交互式确认**，每一步都由你把控。

## ✨ 功能特性

| 特性 | 说明 |
|------|------|
| 🔍 **自动扫描** | 遍历目录，统计 Python 文件、行数、大小 |
| 📦 **大文件检测** | 自动识别大目录/大文件（>10MB/50MB），给出 Git LFS 建议 |
| 🤖 **AI 架构分析** | DeepSeek 分析代码，识别重复、建议重组方案（自适应读取，小文件全量读、大文件智能截断） |
| 📋 **重组计划生成** | AI 规划新目录结构 + 文件迁移映射 |
| 💾 **自动备份** | 重组前创建时间戳备份，零风险操作 |
| 📝 **自动生成文档** | README.md / .gitignore / .gitattributes / requirements.txt |
| 🎛️ **交互式确认** | 每一步都让你预览和确认，不会盲目执行 |
| 🌐 **GitHub 就绪** | 最终生成的目录结构可直接 `git init` + `git push` |

## 🗂️ 项目结构

```
github-ready-重构工具/
├── main.py                    🎯 主入口 — 交互式 CLI，一键走完完整流程
├── config.py                  🔑 配置管理 — API Key（环境变量 > config.json > 交互输入）
├── analyze_project.py         🔍 项目扫描与 AI 分析
├── restructure_project.py     📋 重组计划生成与展示确认
├── execute_refactor.py        🛠️ 备份与重组执行引擎
├── generate_readme.py         📝 README.md 自动生成
├── requirements.txt           依赖清单
└── README.md                  本文件
```

## 🚀 快速开始

### 环境要求

- Python 3.10+
- DeepSeek / OpenAI 兼容 API Key

### 安装

```bash
# 1. 克隆或下载本工具
# 2. 安装依赖
pip install -r requirements.txt
```

### 基本用法

```bash
python main.py
```

然后按提示操作：

```
📂 请输入要处理的项目路径
   （回车键可浏览当前目录）
   > /path/to/your/old-project

📦 请指定新项目名称（输出目录名，由你决定）
   建议: old-project
   > my-refactored-project
```

### 分步说明

完整流程分为 **5 步**，每步都有交互确认：

| 步骤 | 操作 |
|------|------|
| **第0步** | 配置 API Key（首次输入可保存，之后自动加载） |
| **第1步** | AI 分析项目 → 展示分析摘要（项目名建议、技术栈、重复代码） |
| **第2步** | 生成重组计划 → 预览新目录结构和文件迁移方案 |
| **第3步** | 确认计划 → 支持 Y/n/e（e = 编辑 plan.json 微调） |
| **第4步** | 执行重组 → 模拟运行 → 确认 → 实际执行 |
| **第5步** | 生成 README / .gitignore / requirements.txt → 打印 GitHub 指引 |

### 高级用法：分模块单独运行

```bash
# 仅分析项目结构
python analyze_project.py /path/to/project

# 仅分析并指定代码读取预算（默认 100,000 字符）
python analyze_project.py /path/to/project --max-chars 200000

# 仅生成 README
python generate_readme.py /path/to/project my-project-name "项目描述"

# 查看重组计划（已有 plan.json 时）
python restructure_project.py plan.json
```

## 📦 如何处理大数据

工具会自动检测大目录/大文件（默认阈值：目录 > 50MB，文件 > 10MB），并在分析报告中给出建议：

- **< 50 MB** — 正常上传 Git
- **50 ~ 100 MB** — 建议使用 Git LFS
- **100 ~ 500 MB** — 强烈建议 Git LFS
- **> 500 MB** — 建议不上传 Git，使用 DVC 或云存储

你可以在 `.gitignore` 中排除不需要追踪的数据目录，或在 `.gitattributes` 中配置 LFS 规则。

## ⚙️ 配置说明

### API Key 配置（三选一）

```bash
# 方式1：环境变量（推荐，安全）
export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxx"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export DEEPSEEK_MODEL="deepseek-v4-pro"

# 方式2：首次运行交互输入（自动保存到 config.json）
python main.py  # 按提示输入即可

# 方式3：直接编辑 config.json
# 文件位置：与 main.py 同目录下的 config.json
```

### 其他配置

环境的变量自定义：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | — | API 密钥 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 端点 |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | 模型名称 |

## 🔒 安全说明

- **API Key 仅保存在本地** `config.json`（文件权限 600，仅当前用户可读写）
- **原项目会先备份**再重组，操作可逆
- **所有 AI 调用**只发送代码片段（自适应读取：小文件全量发送、大文件按预算截断），不发送完整数据文件
- 不会向 GitHub 或第三方上传任何数据

## 📄 License

MIT License — 自由使用、修改、分发。
