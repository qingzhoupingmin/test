"""示例钩子函数 — 演示前置/后置钩子的典型用法"""
from typing import Any, Dict

from loguru import logger


def hook_login_api(case=None, variables=None, response=None, extract_vars=None, **kwargs):
    """典型的前置登录钩子 — 调用登录接口获取 Token 并注入到变量中"""
    import requests

    try:
        base_url = variables.get("base_url", "")
        login_url = f"{base_url}/api/login"
        login_data = {
            "username": variables.get("username", "admin"),
            "password": variables.get("password", "admin123"),
        }
        resp = requests.post(login_url, json=login_data, timeout=10)
        if resp.status_code == 200:
            token = resp.json().get("data", {}).get("token", "")
            variables["auth_token"] = token
            logger.info("hook_login_api: 登录成功，获取到 Token")
        else:
            logger.warning("hook_login_api: 登录失败, status={}", resp.status_code)
    except Exception as e:
        logger.error("hook_login_api: 异常: {}", e)


def hook_set_headers(case=None, variables=None, **kwargs):
    """设置请求头的前置钩子 — 将 Token 注入到 session 的 headers 中"""
    token = variables.get("auth_token", "")
    if token and case:
        case.headers = case.headers or {}
        case.headers["Authorization"] = f"Bearer {token}"
        logger.info("hook_set_headers: Authorization 头已注入")


def hook_cleanup_test_data(case=None, variables=None, response=None, **kwargs):
    """后置清理钩子 — 删除测试过程中创建的数据"""
    logger.info("hook_cleanup_test_data: 清理测试数据...")


def hook_wait_for_loading(driver=None, **kwargs):
    """UI 前置钩子 — 等待页面 Loading 遮罩消失"""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    if driver:
        try:
            WebDriverWait(driver, 5).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, ".loading-overlay"))
            )
            logger.info("hook_wait_for_loading: Loading 遮罩已消失")
        except Exception:
            logger.debug("hook_wait_for_loading: 未检测到 Loading 遮罩")