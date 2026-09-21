"""app.sandbox 包：沙箱执行 + 黑盒测试运行。"""
from .blackbox import Case, parse_cases, run_cases, value_present
from .runner import Sandbox, RunResult

__all__ = ["Sandbox", "RunResult", "Case", "parse_cases", "run_cases", "value_present"]
