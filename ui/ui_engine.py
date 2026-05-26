"""UI 测试引擎 — 调度步骤执行 + 截图 + 断言"""
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from loguru import logger

from core.hook_manager import HookManager
from core.models import UiCaseModel, UiStep, TestResult, AssertionItem
from core.variable_manager import VariableManager


class UiTestEngine:
    """UI 测试引擎：加载用例 → 执行步骤 → 截图 → 断言"""

    ACTION_HANDLERS = {
        "navigate": "_do_navigate",
        "click": "_do_click",
        "input": "_do_input",
        "select": "_do_select",
        "hover": "_do_hover",
        "double_click": "_do_double_click",
        "right_click": "_do_right_click",
        "scroll_to": "_do_scroll_to",
        "switch_frame": "_do_switch_frame",
        "switch_default": "_do_switch_default",
        "switch_window": "_do_switch_window",
        "wait": "_do_wait",
        "wait_element": "_do_wait_element",
        "execute_script": "_do_execute_script",
        "upload_file": "_do_upload_file",
        "press_key": "_do_press_key",
        "clear": "_do_clear",
        "screenshot": "_do_screenshot",
    }

    def __init__(self, driver: WebDriver, screenshot_dir: str = "reports/screenshots"):
        self.driver = driver
        self.screenshot_dir = screenshot_dir
        self.vars = VariableManager()
        os.makedirs(screenshot_dir, exist_ok=True)

    def run_case(self, case: UiCaseModel) -> TestResult:
        """执行单个 UI 用例"""
        logger.info("━━━ 执行 UI 用例: {} | {}", case.case_id, case.case_name)

        if case.skip:
            logger.info("跳过用例: {}", case.case_id)
            return TestResult(case_id=case.case_id, case_name=case.case_name, passed=True)

        # ── 前置钩子 ──
        HookManager.execute(case.pre_hook, {"case": case, "driver": self.driver, "variables": self.vars.get_all()})

        # ── 导航 ──
        if case.page_url:
            try:
                resolved_url = self._resolve_variables(case.page_url)
                self.driver.get(resolved_url)
                logger.info("导航至: {}", resolved_url)
            except Exception as e:
                logger.error("页面导航失败: {}", e)
                return TestResult(case_id=case.case_id, case_name=case.case_name,
                                  passed=False, error_message=str(e))

        error_message = ""
        assertions_passed = True
        step_count = len(case.steps)

        try:
            # ── 执行步骤 ──
            for i, step in enumerate(case.steps):
                logger.info("  步骤 [{}/{}]: {}", i + 1, step_count, step.action)
                self._execute_step(step)

            # ── 等待 ──
            if case.wait_after_ms:
                time.sleep(case.wait_after_ms / 1000.0)

            # ── 断言 ──
            assertions_passed = self._run_ui_assertions(case.assertions)

            # ── 后置钩子 ──
            HookManager.execute(case.post_hook, {"case": case, "driver": self.driver, "variables": self.vars.get_all()})

        except Exception as e:
            error_message = str(e)
            logger.error("UI 步骤执行异常: {}", error_message)
            # 失败截图
            if case.screenshot_on_fail:
                self._take_screenshot(f"{case.case_id}_fail")

        passed = not error_message and (assertions_passed if case.assertions else True)

        result = TestResult(
            case_id=case.case_id,
            case_name=case.case_name,
            passed=passed,
            error_message=error_message,
        )

        logger.info("用例结果: {} | {}", "✓ 通过" if passed else "✗ 失败", case.case_name)
        return result

    def run_cases(self, cases: List[UiCaseModel]) -> List[TestResult]:
        """批量执行 UI 用例"""
        results = []
        for case in cases:
            result = self.run_case(case)
            results.append(result)
        return results

    # =================== 步骤执行 ===================

    def _execute_step(self, step: UiStep) -> None:
        """执行单个 UI 步骤"""
        action = step.action.lower()
        handler_name = self.ACTION_HANDLERS.get(action)
        if handler_name is None:
            raise ValueError(f"未知的 UI 动作: {action}")

        handler = getattr(self, handler_name)
        handler(step)

    def _resolve_selector(self, step: UiStep) -> tuple:
        """解析选择器：iframe 内切换，返回 (By, value)"""
        if step.iframe:
            self._do_switch_frame(UiStep(action="switch_frame", selector=step.iframe))

        if step.selector is None:
            return None, None

        selector = self._resolve_variables(str(step.selector))
        value = self._resolve_variables(str(step.value)) if step.value else None

        # 智能选择器：自动识别类型
        if selector.startswith("//") or selector.startswith("(//"):
            return By.XPATH, selector
        elif selector.startswith("#"):
            return By.ID, selector[1:]
        elif selector.startswith("."):
            return By.CLASS_NAME, selector[1:]
        elif selector.startswith("[") and selector.endswith("]"):
            attr = selector[1:-1]
            if "=" in attr:
                key, val = attr.split("=", 1)
                return By.XPATH, f"//*[@{key}='{val}']"
            return By.XPATH, f"//*[@{attr}]"
        elif selector.startswith("css:"):
            return By.CSS_SELECTOR, selector[4:]
        elif selector.startswith("xpath:"):
            return By.XPATH, selector[6:]
        elif selector.startswith("text:"):
            return By.XPATH, f"//*[contains(text(),'{selector[5:]}')]"
        else:
            return By.CSS_SELECTOR, selector

    def _find_element(self, step: UiStep, timeout: int = 10):
        by, value = self._resolve_selector(step)
        if by is None:
            return None
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )

    # ── 动作实现 ──

    def _do_navigate(self, step: UiStep) -> None:
        url = self._resolve_variables(str(step.value))
        self.driver.get(url)

    def _do_click(self, step: UiStep) -> None:
        el = self._find_element(step)
        el.click()

    def _do_input(self, step: UiStep) -> None:
        el = self._find_element(step)
        el.clear()
        value = self._resolve_variables(str(step.value)) if step.value else ""
        el.send_keys(value)

    def _do_select(self, step: UiStep) -> None:
        from selenium.webdriver.support.ui import Select
        el = self._find_element(step)
        Select(el).select_by_visible_text(str(step.value))

    def _do_hover(self, step: UiStep) -> None:
        from selenium.webdriver.common.action_chains import ActionChains
        el = self._find_element(step)
        ActionChains(self.driver).move_to_element(el).perform()

    def _do_double_click(self, step: UiStep) -> None:
        from selenium.webdriver.common.action_chains import ActionChains
        el = self._find_element(step)
        ActionChains(self.driver).double_click(el).perform()

    def _do_right_click(self, step: UiStep) -> None:
        from selenium.webdriver.common.action_chains import ActionChains
        el = self._find_element(step)
        ActionChains(self.driver).context_click(el).perform()

    def _do_scroll_to(self, step: UiStep) -> None:
        el = self._find_element(step)
        self.driver.execute_script("arguments[0].scrollIntoView(true);", el)

    def _do_switch_frame(self, step: UiStep) -> None:
        if step.value:
            self.driver.switch_to.frame(str(step.value))
        elif step.selector:
            el = self._find_element(step)
            self.driver.switch_to.frame(el)

    def _do_switch_default(self, step: UiStep) -> None:
        self.driver.switch_to.default_content()

    def _do_switch_window(self, step: UiStep) -> None:
        handles = self.driver.window_handles
        idx = int(step.value) if step.value and step.value.isdigit() else -1
        self.driver.switch_to.window(handles[idx])

    def _do_wait(self, step: UiStep) -> None:
        ms = int(step.value) if step.value else 1000
        time.sleep(ms / 1000.0)

    def _do_wait_element(self, step: UiStep) -> None:
        self._find_element(step, timeout=int(step.value) if step.value else 10)

    def _do_execute_script(self, step: UiStep) -> None:
        self.driver.execute_script(self._resolve_variables(str(step.value)))

    def _do_upload_file(self, step: UiStep) -> None:
        el = self._find_element(step)
        el.send_keys(self._resolve_variables(str(step.value)))

    def _do_press_key(self, step: UiStep) -> None:
        from selenium.webdriver.common.keys import Keys
        key = getattr(Keys, str(step.value).upper(), step.value)
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(self.driver).send_keys(key).perform()

    def _do_clear(self, step: UiStep) -> None:
        el = self._find_element(step)
        el.clear()

    # =================== 截图 / 断言 ===================

    def _take_screenshot(self, name: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.png"
        filepath = os.path.join(self.screenshot_dir, filename)
        self.driver.save_screenshot(filepath)
        logger.info("截图保存: {}", filepath)
        return filepath

    def _run_ui_assertions(self, assertions: List[AssertionItem]) -> bool:
        if not assertions:
            return True
        all_passed = True
        for a in assertions:
            atype = a.type.lower()
            try:
                if atype == "element_visible":
                    el = self._find_element(UiStep(action="", selector=a.target), timeout=5)
                    if not el.is_displayed():
                        logger.error("断言失败: 元素不可见 - {}", a.target)
                        all_passed = False
                elif atype == "element_not_visible":
                    try:
                        el = self._find_element(UiStep(action="", selector=a.target), timeout=3)
                        if el.is_displayed():
                            logger.error("断言失败: 元素不应可见 - {}", a.target)
                            all_passed = False
                    except (TimeoutException, NoSuchElementException):
                        pass  # 不可见 = 通过
                elif atype == "text_equals":
                    el = self._find_element(UiStep(action="", selector=a.target), timeout=5)
                    actual = el.text
                    if str(actual) != str(a.value):
                        logger.error("断言失败: text_equals - 期望={} 实际={}", a.value, actual)
                        all_passed = False
                elif atype == "text_contains":
                    el = self._find_element(UiStep(action="", selector=a.target), timeout=5)
                    if str(a.value) not in el.text:
                        logger.error("断言失败: text_contains - 文本中未找到 '{}'", a.value)
                        all_passed = False
                elif atype == "url_contains":
                    if str(a.value) not in self.driver.current_url:
                        logger.error("断言失败: url_contains - '{}' not in '{}'", a.value, self.driver.current_url)
                        all_passed = False
                elif atype == "page_title":
                    if str(a.value) != self.driver.title:
                        logger.error("断言失败: page_title - 期望={} 实际={}", a.value, self.driver.title)
                        all_passed = False
                elif atype == "element_count":
                    by, value = self._resolve_selector(UiStep(action="", selector=a.target))
                    els = self.driver.find_elements(by, value)
                    count = len(els)
                    expected = int(a.value)
                    if count != expected:
                        logger.error("断言失败: element_count - 期望={} 实际={}", expected, count)
                        all_passed = False
            except Exception as e:
                logger.error("UI 断言异常: {} | {}", a.type, e)
                all_passed = False
        return all_passed

    # =================== 变量 ===================

    def _resolve_variables(self, value: Any) -> Any:
        import re
        if isinstance(value, str):
            def replacer(match):
                var_name = match.group(1)
                val = self.vars.get(var_name)
                if val is not None:
                    return str(val)
                if var_name == "timestamp":
                    return str(int(time.time()))
                return match.group(0)
            return re.sub(r"\{\{(\w+)\}\}", replacer, value)
        if isinstance(value, dict):
            return {k: self._resolve_variables(v) for k, v in value.items()}
        return value

    def close(self) -> None:
        self.driver.quit()
        logger.info("浏览器驱动已关闭")