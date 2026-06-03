"""
config.py
=========
统一配置管理：API Key、Base URL 等全局设置。

优先级：环境变量 > config.json > 交互输入

环境变量:
  DEEPSEEK_API_KEY     - DeepSeek / OpenAI 兼容 API 密钥
  DEEPSEEK_BASE_URL    - API 端点（默认 https://api.deepseek.com）
"""

import os
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "config.json"


def get_api_key() -> str | None:
    """获取 API Key，优先级：环境变量 > config.json"""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            return cfg.get("api_key")
        except (json.JSONDecodeError, OSError):
            return None
    return None


def get_base_url() -> str:
    """获取 API Base URL"""
    url = os.environ.get("DEEPSEEK_BASE_URL")
    if url:
        return url
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            return cfg.get("base_url", "https://api.deepseek.com")
        except (json.JSONDecodeError, OSError):
            pass
    return "https://api.deepseek.com"


def save_config(api_key: str, base_url: str = "https://api.deepseek.com") -> None:
    """将 API Key 保存到 config.json（仅本地文件权限）"""
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    cfg["api_key"] = api_key
    cfg["base_url"] = base_url
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    # 仅当前用户可读写
    try:
        CONFIG_FILE.chmod(0o600)
    except Exception:
        pass
    print(f"✅ 配置已保存到 {CONFIG_FILE}")


def get_model() -> str:
    """获取模型名称"""
    return os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


def get_or_prompt_api_key() -> tuple[str, str, str]:
    """
    获取或提示用户输入 API 配置。
    Returns:
        (api_key, base_url, model)
    """
    api_key = get_api_key()
    base_url = get_base_url()
    model = get_model()

    if not api_key:
        print("\n" + "=" * 60)
        print("🔑 API 密钥配置")
        print("=" * 60)
        print("需要 DeepSeek / OpenAI 兼容 API 密钥来驱动 AI 分析。")
        print("（密钥仅保存在本地 config.json，不会上传）")
        print()
        api_key = input("请输入 API Key: ").strip()
        if not api_key:
            print("❌ API Key 不能为空")
            return get_or_prompt_api_key()

        save_choice = input("是否保存到 config.json？(Y/n): ").strip().lower()
        if save_choice != "n":
            url_input = input(f"Base URL [回车默认 {base_url}]: ").strip()
            if url_input:
                base_url = url_input
            save_config(api_key, base_url)

        model_input = input(f"模型名称 [回车默认 {model}]: ").strip()
        if model_input:
            model = model_input
    else:
        print(f"🔑 已加载 API Key (端点: {base_url})")

    return api_key, base_url, model
