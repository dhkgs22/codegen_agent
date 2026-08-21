"""应用配置：从环境变量 / .env 读取。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv 未安装时静默降级
    pass


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    )
    deepseek_model: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    )
    # 沙箱执行超时（秒）
    sandbox_timeout: int = field(
        default_factory=lambda: int(os.getenv("SANDBOX_TIMEOUT", "20"))
    )
    # Debug Agent 最大修复轮次
    max_fix_rounds: int = field(
        default_factory=lambda: int(os.getenv("MAX_FIX_ROUNDS", "3"))
    )
    llm_timeout: float = field(
        default_factory=lambda: float(os.getenv("LLM_TIMEOUT", "120"))
    )
    # 运行通过后是否自动生成并运行测试（Test Agent），测试失败不影响整体结果
    auto_tests: bool = field(
        default_factory=lambda: os.getenv("AUTO_TESTS", "1").lower() not in ("0", "false", "no")
    )


settings = Settings()
