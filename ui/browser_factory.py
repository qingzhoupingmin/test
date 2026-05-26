"""浏览器工厂 — 统一创建 Selenium / Playwright WebDriver"""
from typing import Any, Dict

from loguru import logger


class BrowserFactory:
    """浏览器驱动工厂，支持两种实现：
    - Selenium: 兼容性最好，支持 IE/Edge 旧版
    - Playwright: 现代浏览器自动化，速度更快
    """

    @staticmethod
    def create_selenium_driver(config: Dict[str, Any]):
        """创建 Selenium WebDriver

        Args:
            config: 浏览器配置字典，包含 type, headless, window_size 等
        Returns:
            selenium.webdriver 实例
        """
        browser_type = config.get("type", "chrome").lower()
        headless = config.get("headless", False)
        window_size = config.get("window_size", "1920x1080")

        if browser_type == "chrome":
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            options = Options()
            if headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            options.add_argument(f"--window-size={window_size}")
            options.add_argument("--disable-dev-shm-usage")
            # 忽略 SSL 证书错误
            options.add_argument("--ignore-certificate-errors")
            # 禁用自动化检测标志
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            driver_path = config.get("driver_path", "")
            if driver_path:
                service = Service(executable_path=driver_path)
                driver = webdriver.Chrome(service=service, options=options)
            else:
                driver = webdriver.Chrome(options=options)

        elif browser_type == "firefox":
            from selenium import webdriver
            from selenium.webdriver.firefox.options import Options
            options = Options()
            if headless:
                options.add_argument("--headless")
            options.add_argument(f"--width={window_size.split('x')[0]}")
            options.add_argument(f"--height={window_size.split('x')[1]}")
            driver = webdriver.Firefox(options=options)

        elif browser_type == "edge":
            from selenium import webdriver
            from selenium.webdriver.edge.options import Options
            from selenium.webdriver.edge.service import Service
            options = Options()
            if headless:
                options.add_argument("--headless=new")
            options.add_argument(f"--window-size={window_size}")
            driver_path = config.get("driver_path", "")
            if driver_path:
                service = Service(executable_path=driver_path)
                driver = webdriver.Edge(service=service, options=options)
            else:
                driver = webdriver.Edge(options=options)
        else:
            raise ValueError(f"不支持的浏览器类型: {browser_type}")

        # 设置隐式等待
        implicit_wait = config.get("implicit_wait", 10)
        driver.implicitly_wait(implicit_wait)

        logger.info("Selenium 浏览器驱动创建成功: {} | headless={}", browser_type, headless)
        return driver

    @staticmethod
    def create_playwright_driver(config: Dict[str, Any]):
        """创建 Playwright 驱动（返回 browser + page）

        Args:
            config: 浏览器配置字典
        Returns:
            (browser, page) 元组
        """
        from playwright.sync_api import sync_playwright

        browser_type = config.get("type", "chromium").lower()
        headless = config.get("headless", False)
        window_size = config.get("window_size", "1920x1080")
        w, h = window_size.split("x") if "x" in window_size else (1920, 1080)

        pw = sync_playwright().start()

        launch_options = {
            "headless": headless,
            "args": ["--no-sandbox", "--disable-setuid-sandbox"],
        }

        if browser_type == "chromium":
            browser = pw.chromium.launch(**launch_options)
        elif browser_type == "firefox":
            browser = pw.firefox.launch(**launch_options)
        elif browser_type == "webkit":
            browser = pw.webkit.launch(**launch_options)
        else:
            pw.stop()
            raise ValueError(f"不支持的浏览器类型: {browser_type}")

        context = browser.new_context(
            viewport={"width": int(w), "height": int(h)},
            ignore_https_errors=True,
        )
        page = context.new_page()

        logger.info("Playwright 浏览器驱动创建成功: {} | headless={}", browser_type, headless)
        return pw, browser, context, page