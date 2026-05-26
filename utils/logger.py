"""日志工具 — 基于 loguru，同时支持控制台、文件、Allure 输出"""
import sys
from pathlib import Path

from loguru import logger


class LoggerSetup:
    """日志初始化配置，在框架启动时调用一次即可。"""

    _initialized: bool = False

    @classmethod
    def setup(
        cls,
        level: str = "INFO",
        log_dir: str = "logs",
        rotation: str = "1 day",
        retention: str = "15 days",
        format_str: str = None,
    ) -> None:
        if cls._initialized:
            return

        logger.remove()

        # 控制台输出
        console_format = (
            format_str
            or "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
        logger.add(
            sys.stdout,
            format=console_format,
            level=level,
            colorize=True,
        )

        # 文件输出
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_format = format_str or (
            "{time:YYYY-MM-DD HH:mm:ss} | {level} | "
            "{name}:{function}:{line} | {message}"
        )
        logger.add(
            str(log_path / "{time:YYYY-MM-DD}.log"),
            format=file_format,
            level=level,
            rotation=rotation,
            retention=retention,
            encoding="utf-8",
        )

        cls._initialized = True
        logger.info("日志系统初始化完成")

    @classmethod
    def get_logger(cls):
        return logger