"""变量管理器 — 全局变量/环境变量/提取变量的统一存储"""
from typing import Any, Dict


class VariableManager:
    """集中管理运行时变量，支持：
    - 环境配置变量注入
    - 用例提取变量
    - 参数化数据变量
    - 内置变量（如 {{timestamp}}）
    """

    _instance: "VariableManager" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._variables: Dict[str, Any] = {}
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._variables: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._variables[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._variables.get(key, default)

    def set_bulk(self, mapping: Dict[str, Any]) -> None:
        self._variables.update(mapping)

    def get_all(self) -> Dict[str, Any]:
        return dict(self._variables)

    def clear(self) -> None:
        self._variables.clear()

    @classmethod
    def reset(cls) -> None:
        """重置单例（测试隔离用）"""
        if cls._instance:
            cls._instance._variables = {}