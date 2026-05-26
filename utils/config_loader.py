"""配置加载器 — YAML + 环境变量注入"""
import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv


class ConfigLoader:
    """框架统一配置加载器，支持：
    - 从 YAML 文件加载配置
    - 深合并多个配置源
    - 环境变量注入 `${VAR:default}` 语法
    """

    _cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def load(cls, path: str, use_cache: bool = True) -> Dict[str, Any]:
        """加载指定 YAML 文件，返回配置字典。

        Args:
            path: YAML 文件路径，相对于项目根目录
            use_cache: 是否缓存
        """
        full_path = Path(path)
        if not full_path.is_absolute():
            # 相对于项目根目录
            project_root = Path(__file__).parent.parent
            full_path = project_root / path

        cache_key = str(full_path.resolve())
        if use_cache and cache_key in cls._cache:
            return cls._cache[cache_key]

        load_dotenv()

        with open(full_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        config = cls._resolve_env_vars(raw)

        if use_cache:
            cls._cache[cache_key] = config
        return config

    @classmethod
    def merge(cls, *configs: Dict[str, Any]) -> Dict[str, Any]:
        """深合并多个配置字典，后面的覆盖前面的。"""
        result: Dict[str, Any] = {}
        for config in configs:
            cls._deep_merge(result, config)
        return result

    @classmethod
    def _deep_merge(cls, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                cls._deep_merge(base[key], value)
            else:
                base[key] = value

    @classmethod
    def _resolve_env_vars(cls, data: Any) -> Any:
        """递归解析值中的 ${VAR:default} 环境变量引用"""
        if isinstance(data, dict):
            return {k: cls._resolve_env_vars(v) for k, v in data.items()}
        if isinstance(data, list):
            return [cls._resolve_env_vars(item) for item in data]
        if isinstance(data, str):
            return cls._resolve_env_string(data)
        return data

    @classmethod
    def _resolve_env_string(cls, value: str) -> str:
        """解析单个字符串中的 ${VAR:default} 模式"""
        pattern = re.compile(r"\$\{(\w+)(?::([^}]*))?\}")

        def replacer(match):
            var_name = match.group(1)
            default = match.group(2)
            env_val = os.environ.get(var_name)
            if env_val is not None:
                return env_val
            if default is not None:
                return default
            raise ValueError(
                f"环境变量 '{var_name}' 未设置，且未提供默认值。"
                f"请在配置中提供默认值或设置环境变量。"
            )

        return pattern.sub(replacer, value)

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()