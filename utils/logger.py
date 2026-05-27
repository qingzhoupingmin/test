"""日志工具 — 基于 loguru，同时支持控制台、文件、Allure 输出，含敏感字段脱敏"""
import re
import sys
from pathlib import Path
from typing import Set

from loguru import logger


# ── 敏感字段脱敏 ──

_SENSITIVE_KEYS: Set[str] = {
    "password", "passwd", "secret", "token", "access_token", "api_key",
    "authorization", "credential", "private_key", "sign", "signature",
    "accessKey", "secretKey", "ak", "sk", "idcard", "phone", "mobile",
    "email", "bankcard", "cert", "license",
}

_SENSITIVE_PATTERNS = [
    (re.compile(r'(password|passwd|secret|token|access_token|api_key|apikey)\s*[:=]\s*["\']?([^"\'&\s,]+)["\']?', re.IGNORECASE), r'\1=***'),
    (re.compile(r'(authorization|auth)\s*[:=]\s*["\']?(Bearer\s+)?([^\s"\'&,]+)["\']?', re.IGNORECASE), r'\1=Bearer ***'),
    (re.compile(r'1[3-9]\d{9}'), r'1**********'),   # 手机号
    (re.compile(r'\d{17}[\dXx]|\d{15}'), r'******'),  # 身份证号
]


def mask_sensitive(text: str) -> str:
    """对日志文本中的敏感信息进行脱敏处理"""
    if not isinstance(text, str):
        return text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _sensitive_patcher(record):
    """loguru patcher — 在日志输出前对 message 进行脱敏"""
    record["message"] = mask_sensitive(record["message"])


# ── LoggerSetup ──

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
        enable_mask: bool = True,
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

        # 全局敏感字段脱敏 patcher
        if enable_mask:
            logger.configure(patcher=_sensitive_patcher)

        cls._initialized = True
        logger.info("日志系统初始化完成（脱敏: {}）", "开" if enable_mask else "关")

    @classmethod
    def get_logger(cls):
        return logger
