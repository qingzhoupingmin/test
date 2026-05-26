"""钩子管理器 — 管理用例前置/后置钩子的注册与执行"""
import importlib
from typing import Any, Dict, List, Optional

from loguru import logger


class HookManager:
    """钩子管理器：
    - 按名称注册钩子函数
    - 执行前将当前上下文注入
    """

    _hooks: Dict[str, callable] = {}

    @classmethod
    def register(cls, name: str, func: callable) -> None:
        """注册钩子函数"""
        cls._hooks[name] = func
        logger.debug("注册钩子: {}", name)

    @classmethod
    def register_from_module(cls, module_path: str) -> None:
        """从 Python 模块路径自动注册所有以 hook_ 开头的函数"""
        try:
            module = importlib.import_module(module_path)
            for attr_name in dir(module):
                if attr_name.startswith("hook_"):
                    func = getattr(module, attr_name)
                    if callable(func):
                        cls.register(attr_name, func)
            logger.info("从模块 {} 注册了钩子函数", module_path)
        except ImportError as e:
            logger.warning("无法导入钩子模块: {} | {}", module_path, e)

    @classmethod
    def execute(cls, name: Optional[str], context: Dict[str, Any] = None) -> bool:
        """执行指定名称的钩子，不存在则跳过（视为成功）

        Args:
            name: 钩子名称
            context: 注入的上下文变量（如 variables, response, case 等）
        Returns:
            是否执行成功
        """
        if name is None or name not in cls._hooks:
            return True
        ctx = context or {}
        try:
            cls._hooks[name](**ctx)
            logger.debug("钩子执行成功: {}", name)
            return True
        except Exception as e:
            logger.error("钩子执行失败: {} | {}", name, e)
            return False

    @classmethod
    def get_hook_names(cls) -> List[str]:
        return list(cls._hooks.keys())

    @classmethod
    def clear(cls) -> None:
        cls._hooks.clear()

    @classmethod
    def is_registered(cls, name: str) -> bool:
        return name in cls._hooks