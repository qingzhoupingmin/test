"""全局 pytest 配置 — session/function 级别的 fixture 管理"""
import os
import sys
from pathlib import Path

import pytest
from loguru import logger

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))


def pytest_configure(config):
    """pytest 启动时的全局配置"""
    # 标记注册
    config.addinivalue_line("markers", "api: 接口测试用例")
    config.addinivalue_line("markers", "ui: UI 测试用例")
    config.addinivalue_line("markers", "smoke: 冒烟测试")
    config.addinivalue_line("markers", "regression: 回归测试")
    config.addinivalue_line("markers", "p0: P0 优先级")
    config.addinivalue_line("markers", "p1: P1 优先级")
    config.addinivalue_line("markers", "p2: P2 优先级")

    # 配置日志
    logger.add(
        "logs/test_{time:YYYY-MM-DD}.log",
        rotation="500 MB",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    )


@pytest.fixture(scope="session")
def global_config():
    """加载全局配置，整个测试 session 共享"""
    from utils.config_loader import ConfigLoader
    config = ConfigLoader.load_all()
    return config


@pytest.fixture(scope="session")
def env_config(global_config):
    """返回当前环境的配置"""
    env = global_config.get("active_env", "dev")
    return global_config.get("env_config", {}).get(env, {})


@pytest.fixture(scope="session")
def db_helper(global_config):
    """创建数据库连接（session 级复用）"""
    from utils.db_helper import DBHelper
    db_config = global_config.get("database", {})
    if not db_config:
        return None
    helper = DBHelper(db_config)
    yield helper
    helper.close()


@pytest.fixture(scope="session")
def api_session(global_config):
    """创建 API Session（session 级复用）"""
    from api.session_manager import SessionManager
    api_cfg = global_config.get("api", {})
    session = SessionManager(
        base_url=api_cfg.get("base_url", ""),
        timeout=api_cfg.get("timeout", 30),
        retry=api_cfg.get("retry", 0),
        retry_delay=api_cfg.get("retry_delay", 1.0),
    )
    yield session
    session.close()


@pytest.fixture(scope="function")
def variable_manager():
    """每个用例独立变量管理器"""
    from core.variable_manager import VariableManager
    VariableManager.reset()
    return VariableManager()


@pytest.fixture(scope="function")
def api_engine(api_session, db_helper, variable_manager, global_config):
    """API 测试引擎 fixture"""
    from api.api_engine import ApiTestEngine
    from core.hook_manager import HookManager

    # 自动注册钩子
    hooks_module = global_config.get("hooks", {}).get("module", "hooks.sample_hooks")
    HookManager.register_from_module(hooks_module)

    engine = ApiTestEngine(session=api_session, db_helper=db_helper)
    return engine


@pytest.fixture(scope="function")
def ui_driver(global_config):
    """UI 浏览器驱动 fixture（每个用例独立）"""
    from ui.browser_factory import BrowserFactory
    browser_cfg = global_config.get("browser", {})
    driver = BrowserFactory.create_selenium_driver(browser_cfg)
    yield driver
    try:
        driver.quit()
    except Exception:
        pass