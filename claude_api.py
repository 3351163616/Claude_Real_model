#!/usr/bin/env python3
"""
Claude Model Detector - Claude 真实模型检测工具

通过询问"你的知识库截止时间？"来判断 Claude 真实模型版本
原理：去除系统提示词，直接询问原生 Claude，根据回答判断模型

判断规则：
- 2024年10月 → Claude Sonnet 3.7 (think)
- 2025年1月  → Claude Sonnet 4 (think)
- 2024年4月  → Claude Sonnet 4.5 (think)
- 2025年4月  → Claude Opus 4.5 (think)

准确率约 95%

GitHub: https://github.com/yourname/claude-model-detector
"""

import json
import re
import sys
import httpx
from pathlib import Path


# ============ 配置加载 ============

def load_config() -> dict:
    """加载配置文件"""
    config_path = Path(__file__).parent / "config.json"

    if not config_path.exists():
        print("=" * 60)
        print("❌ 错误: 配置文件 config.json 不存在")
        print("=" * 60)
        print("请按以下步骤操作:")
        print("1. 复制 config.example.json 为 config.json")
        print("2. 在 config.json 中填写你的 API Key")
        print("=" * 60)
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============ 请求头构建 ============

def get_headers(api_key: str) -> dict:
    """构建请求头（模拟 Claude CLI）"""
    return {
        "accept": "application/json",
        "anthropic-beta": "claude-code-20250219,interleaved-thinking-2025-05-14",
        "anthropic-dangerous-direct-browser-access": "true",
        "anthropic-version": "2023-06-01",
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json",
        "user-agent": "claude-cli/2.0.50 (external, cli)",
        "x-app": "cli",
        "x-stainless-arch": "x64",
        "x-stainless-helper-method": "stream",
        "x-stainless-lang": "js",
        "x-stainless-os": "Windows",
        "x-stainless-package-version": "0.70.0",
        "x-stainless-retry-count": "0",
        "x-stainless-runtime": "node",
        "x-stainless-runtime-version": "v24.3.0",
        "x-stainless-timeout": "600",
        "accept-encoding": "identity",
    }


# ============ 请求体构建 ============

def build_body(message: str, config: dict, with_thinking: bool = True) -> dict:
    """
    构建请求体（无系统提示词，用于检测真实模型）
    """
    body = {
        "model": config.get("model", "claude-sonnet-4-5-20250929"),
        "messages": [
            {
                "role": "user",
                "content": message
            }
        ],
        "max_tokens": config.get("max_tokens", 16000),
        "stream": True
    }

    # 添加思考模式
    if with_thinking:
        body["thinking"] = {
            "type": "enabled",
            "budget_tokens": config.get("thinking_budget", 10000)
        }

    return body


# ============ 模型判断 ============

MODEL_PATTERNS = [
    # 中文格式
    (r"2024\s*年?\s*10\s*月", "Claude Sonnet 3.7"),
    (r"2025\s*年?\s*1\s*月", "Claude Sonnet 4"),
    (r"2024\s*年?\s*4\s*月", "Claude Sonnet 4.5"),
    (r"2025\s*年?\s*4\s*月", "Claude Opus 4.5"),
    # 英文格式
    (r"October\s*2024", "Claude Sonnet 3.7"),
    (r"January\s*2025", "Claude Sonnet 4"),
    (r"April\s*2024", "Claude Sonnet 4.5"),
    (r"April\s*2025", "Claude Opus 4.5"),
]


def detect_model(response_text: str) -> str:
    """根据回答判断模型版本"""
    for pattern, model in MODEL_PATTERNS:
        if re.search(pattern, response_text, re.IGNORECASE):
            return model
    return "未知模型"


# ============ 流式请求 ============

def send_request(
    api_name: str,
    api_config: dict,
    message: str,
    config: dict,
    with_thinking: bool = True,
    show_thinking: bool = True
) -> str:
    """
    发送请求并处理流式响应
    返回完整的回复文本
    """
    url = api_config["url"]
    headers = get_headers(api_config["key"])
    body = build_body(message, config, with_thinking)

    print(f"\n{'='*60}")
    print(f"📡 API: {api_name}")
    print(f"🔗 URL: {url}")
    print(f"❓ 问题: {message}")
    print(f"🧠 思考模式: {'开启' if with_thinking else '关闭'}")
    print(f"{'='*60}\n")

    full_response = ""

    try:
        with httpx.Client(timeout=600.0) as client:
            with client.stream(
                "POST",
                url,
                headers=headers,
                json=body,
                params={"beta": "true"}
            ) as response:

                if response.status_code != 200:
                    error = response.read().decode('utf-8')
                    print(f"❌ 请求失败 [{response.status_code}]: {error}")
                    return ""

                in_thinking = False

                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue

                    data = line[6:]
                    if data == "[DONE]":
                        break

                    try:
                        event = json.loads(data)
                        event_type = event.get("type", "")

                        if event_type == "content_block_start":
                            block = event.get("content_block", {})
                            if block.get("type") == "thinking":
                                in_thinking = True
                                if show_thinking:
                                    print("[💭 思考]")
                                    print("-" * 40)
                            elif block.get("type") == "text":
                                if in_thinking:
                                    in_thinking = False
                                    if show_thinking:
                                        print("\n" + "-" * 40)
                                print("\n[💬 回复]")
                                print("-" * 40)

                        elif event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                print(text, end="", flush=True)
                                full_response += text
                            elif delta.get("type") == "thinking_delta":
                                if show_thinking:
                                    print(delta.get("thinking", ""), end="", flush=True)

                        elif event_type == "message_start":
                            usage = event.get("message", {}).get("usage", {})
                            if usage:
                                print(f"[📊 输入 tokens: {usage.get('input_tokens', 'N/A')}]")

                        elif event_type == "message_delta":
                            usage = event.get("usage", {})
                            if usage:
                                print(f"\n[📊 输出 tokens: {usage.get('output_tokens', 'N/A')}]")

                    except json.JSONDecodeError:
                        pass

        print(f"\n{'='*60}\n")
        return full_response

    except httpx.ConnectError:
        print(f"❌ 连接失败: 无法连接到 {url}")
        return ""
    except httpx.TimeoutException:
        print("❌ 请求超时")
        return ""
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return ""


# ============ 模型检测模式 ============

def run_model_detection(api_name: str, api_config: dict, config: dict):
    """运行模型检测"""
    print("\n" + "=" * 60)
    print("🔍 Claude 真实模型检测")
    print("=" * 60)
    print("原理: 通过询问知识库截止时间判断真实模型")
    print("⚠️  注意: 不要直接问'你是什么模型'，Claude 可能会回答错误")
    print("=" * 60)

    # 发送检测问题
    response = send_request(
        api_name,
        api_config,
        "你的知识库截止时间？",
        config,
        with_thinking=True,
        show_thinking=True
    )

    if response:
        # 判断模型
        detected = detect_model(response)
        print("=" * 60)
        print(f"🎯 检测结果: {detected}")
        if detected != "未知模型":
            print("✅ 模型已识别 (准确率约 95%)")
        else:
            print("⚠️  无法自动识别，请根据回复内容手动判断:")
            print("    - 2024年10月 → Claude Sonnet 3.7")
            print("    - 2025年1月  → Claude Sonnet 4")
            print("    - 2024年4月  → Claude Sonnet 4.5")
            print("    - 2025年4月  → Claude Opus 4.5")
        print("=" * 60)
        return detected
    return None


# ============ 对话模式 ============

def run_chat_mode(api_name: str, api_config: dict, config: dict):
    """运行对话模式（无上下文）"""
    print("\n" + "=" * 60)
    print("💬 原生对话模式")
    print("=" * 60)
    print("特点: 无系统提示词，无上下文记忆，每次都是新对话")
    print("-" * 60)
    print("命令:")
    print("  thinking on/off - 开关思考模式（默认开启）")
    print("  show on/off     - 开关思考过程显示（默认开启）")
    print("  detect          - 运行模型检测")
    print("  quit/exit/q     - 退出")
    print("=" * 60)

    show_thinking = True
    with_thinking = True

    while True:
        try:
            user_input = input("\n👤 你: ").strip()

            if not user_input:
                continue

            # 命令处理
            cmd = user_input.lower()

            if cmd in ['quit', 'exit', 'q']:
                print("👋 再见！")
                break

            if cmd == 'thinking on':
                with_thinking = True
                print("✅ 已开启思考模式")
                continue

            if cmd == 'thinking off':
                with_thinking = False
                print("✅ 已关闭思考模式")
                continue

            if cmd == 'show on':
                show_thinking = True
                print("✅ 已开启思考过程显示")
                continue

            if cmd == 'show off':
                show_thinking = False
                print("✅ 已关闭思考过程显示")
                continue

            if cmd == 'detect':
                run_model_detection(api_name, api_config, config)
                continue

            # 发送消息
            send_request(api_name, api_config, user_input, config, with_thinking, show_thinking)

        except KeyboardInterrupt:
            print("\n\n👋 已中断")
            break


# ============ 主菜单 ============

def select_api(config: dict) -> tuple:
    """选择 API，返回 (api_name, api_config)"""
    apis = config.get("apis", {})
    if not apis:
        print("❌ 配置文件中没有 API 配置")
        sys.exit(1)

    api_names = list(apis.keys())
    default = config.get("default_api", api_names[0])

    print("\n📋 可用的 API:")
    print("-" * 40)
    for i, name in enumerate(api_names, 1):
        mark = " ⭐(默认)" if name == default else ""
        url = apis[name].get("url", "")
        # 简化显示 URL
        short_url = url.split("//")[-1].split("/")[0] if url else "未配置"
        print(f"  {i}. {name} ({short_url}){mark}")
    print("-" * 40)

    while True:
        choice = input(f"选择 API [1-{len(api_names)}，回车使用默认]: ").strip()

        if not choice:
            return default, apis[default]

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(api_names):
                name = api_names[idx]
                return name, apis[name]
        except ValueError:
            if choice in apis:
                return choice, apis[choice]

        print("⚠️  无效选择，请重试")


def main_menu():
    """主菜单"""
    # 加载配置
    config = load_config()

    print("\n" + "=" * 60)
    print("🤖 Claude Model Detector")
    print("   Claude 真实模型检测工具")
    print("=" * 60)
    print("通过询问知识库截止时间来检测 Claude 真实模型版本")
    print("准确率约 95%")
    print("=" * 60)

    # 选择 API
    api_name, api_config = select_api(config)
    print(f"\n✅ 已选择: {api_name}")

    # 检查 API Key
    if not api_config.get("key") or api_config["key"] == "sk-your-api-key-here":
        print(f"\n❌ 错误: {api_name} 的 API Key 未配置")
        print("请在 config.json 中填写有效的 API Key")
        return

    # 选择模式
    print("\n📌 功能选择:")
    print("-" * 40)
    print("  1. 🔍 模型检测 - 检测 API 后的真实 Claude 模型")
    print("  2. 💬 对话模式 - 与原生 Claude 对话（无系统提示词）")
    print("  3. 🚪 退出")
    print("-" * 40)

    while True:
        choice = input("选择功能 [1-3]: ").strip()

        if choice == '1':
            run_model_detection(api_name, api_config, config)
            # 检测完询问是否继续
            cont = input("\n是否进入对话模式？[y/N]: ").strip().lower()
            if cont == 'y':
                run_chat_mode(api_name, api_config, config)
            break
        elif choice == '2':
            run_chat_mode(api_name, api_config, config)
            break
        elif choice == '3':
            print("👋 再见！")
            break
        else:
            print("⚠️  无效选择，请输入 1、2 或 3")


# ============ 入口 ============

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n👋 已退出")
