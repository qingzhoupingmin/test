"""变量管理器 — 全局变量/环境变量/提取变量的三级作用域存储（线程安全）"""
import threading
from typing import Any, Dict

from loguru import logger


class VariableManager:
    """集中管理运行时变量，支持三级作用域：
    - GLOBAL: 全局配置变量（整个 session 有效）
    - SESSION: 会话级提取变量（整个 session 有效，extract + 依赖传递）
    - CASE:   用例级临时变量（内置函数 + 当前用例上下文，用例结束后回收）

    查找顺序：CASE → SESSION → GLOBAL

    线程安全：所有读写操作受 threading.RLock 保护，支持并发场景及 pytest-xdist。
    """

    GLOBAL = "global"
    SESSION = "session"
    CASE = "case"

    _instance: "VariableManager" = None
    _lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._pools: Dict[str, Dict[str, Any]] = {
                        cls.GLOBAL: {},
                        cls.SESSION: {},
                        cls.CASE: {},
                    }
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._pools: Dict[str, Dict[str, Any]] = {
                self.GLOBAL: {},
                self.SESSION: {},
                self.CASE: {},
            }

    # ── 按作用域写入 ──

    def set(self, key: str, value: Any, scope: str = None) -> None:
        """设置变量，默认写入 SESSION 作用域（向后兼容）"""
        scope = scope or self.SESSION
        if scope not in self._pools:
            logger.warning("未知变量作用域: {}，回退到 SESSION", scope)
            scope = self.SESSION
        with self._lock:
            self._pools[scope][key] = value
        logger.debug("变量写入 [{}]: {} = {}", scope, key, value)

    def set_global(self, key: str, value: Any) -> None:
        """写入 GLOBAL 作用域"""
        self.set(key, value, scope=self.GLOBAL)

    def set_session(self, key: str, value: Any) -> None:
        """写入 SESSION 作用域"""
        self.set(key, value, scope=self.SESSION)

    def set_case(self, key: str, value: Any) -> None:
        """写入 CASE 作用域"""
        self.set(key, value, scope=self.CASE)

    def set_bulk(self, mapping: Dict[str, Any], scope: str = None) -> None:
        """批量写入变量"""
        scope = scope or self.SESSION
        if scope not in self._pools:
            scope = self.SESSION
        with self._lock:
            self._pools[scope].update(mapping)

    # ── 查找（CASE → SESSION → GLOBAL） ──

    def get(self, key: str, default: Any = None) -> Any:
        """按 CASE → SESSION → GLOBAL 顺序查找变量"""
        with self._lock:
            for scope in (self.CASE, self.SESSION, self.GLOBAL):
                if key in self._pools.get(scope, {}):
                    return self._pools[scope][key]
        return default

    def get_from_scope(self, key: str, scope: str, default: Any = None) -> Any:
        """从指定作用域获取变量"""
        with self._lock:
            return self._pools.get(scope, {}).get(key, default)

    # ── 查询所有 ──

    def get_all(self) -> Dict[str, Any]:
        """返回合并后的完整变量视图（CASE 覆盖 SESSION 覆盖 GLOBAL）"""
        with self._lock:
            result = {}
            result.update(self._pools[self.GLOBAL])
            result.update(self._pools[self.SESSION])
            result.update(self._pools[self.CASE])
            return result

    def get_scope(self, scope: str) -> Dict[str, Any]:
        """获取指定作用域的全部变量"""
        with self._lock:
            return dict(self._pools.get(scope, {}))

    # ── 清理 ──

    def clear_case(self) -> None:
        """清空 CASE 作用域（每个用例结束后调用）"""
        with self._lock:
            self._pools[self.CASE].clear()

    def clear_session(self) -> None:
        """清空 SESSION 作用域"""
        with self._lock:
            self._pools[self.SESSION].clear()

    def clear_all(self) -> None:
        """清空所有变量"""
        with self._lock:
            for pool in self._pools.values():
                pool.clear()

    @classmethod
    def reset(cls) -> None:
        """重置单例（测试隔离用）"""
        with cls._lock:
            if cls._instance:
                cls._instance._pools = {
                    cls.GLOBAL: {},
                    cls.SESSION: {},
                    cls.CASE: {},
                }
