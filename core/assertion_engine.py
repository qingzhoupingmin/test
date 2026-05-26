"""断言引擎 — 执行 API / UI / DB 断言并返回通过/失败"""
import re
from typing import Any, Dict, List, Optional

import jsonpath_ng
from jsonschema import validate, ValidationError
from loguru import logger

from core.models import AssertionItem, TestResult


class AssertionEngine:
    """统一断言引擎，支持：
    - API: status_code, jsonpath, contains, response_time, header, schema, db
    - UI: element_visible, text_equals, url_contains, page_title
    - 通用: soft（软断言，仅记录不中断）
    """

    def __init__(self, db_helper=None):
        self.db_helper = db_helper
        self._soft_failures: List[str] = []

    def run(
        self,
        assertions: List[AssertionItem],
        response=None,
        response_time_ms: float = 0.0,
        extra_context: Dict[str, Any] = None,
    ) -> bool:
        """执行断言列表，全部通过返回 True"""
        self._soft_failures.clear()
        ctx = extra_context or {}
        all_passed = True

        for assertion in assertions:
            try:
                result = self._evaluate(assertion, response, response_time_ms, ctx)
                if not result:
                    all_passed = False
            except Exception as e:
                logger.error("断言执行异常: {} | {}", assertion.type, str(e))
                all_passed = False

        if self._soft_failures:
            logger.warning("软断言失败汇总 ({} 条):\n{}", len(self._soft_failures),
                           "\n".join(f"  - {f}" for f in self._soft_failures))

        return all_passed

    def _evaluate(
        self,
        assertion: AssertionItem,
        response,
        response_time_ms: float,
        ctx: Dict[str, Any],
    ) -> bool:
        atype = assertion.type.lower()

        # ===== API 断言 =====
        if atype == "status_code":
            return self._assert_status_code(response, assertion.value)

        elif atype == "jsonpath":
            return self._assert_jsonpath(response, assertion.key, assertion.value)

        elif atype == "contains":
            return self._assert_contains(response, assertion.value)

        elif atype == "response_time":
            return self._assert_response_time(response_time_ms, assertion.max_ms)

        elif atype == "header":
            return self._assert_header(response, assertion.key, assertion.value)

        elif atype == "schema":
            return self._assert_schema(response, assertion.value)

        elif atype == "db":
            return self._assert_db(assertion.query, assertion.value)

        # ===== UI 断言 =====
        elif atype in ("element_visible", "text_equals", "url_contains", "page_title"):
            return self._assert_ui(assertion, ctx)

        # ===== 软断言 =====
        elif atype == "soft":
            return self._assert_soft(assertion, response, response_time_ms, ctx)

        else:
            logger.warning("未知断言类型: {}", assertion.type)
            return False

    # ------------------- 具体断言实现 -------------------

    def _assert_status_code(self, response, expected_value: Any) -> bool:
        actual = response.status_code if response else 0
        expected = int(expected_value)
        passed = actual == expected
        if not passed:
            logger.error("状态码断言失败: 期望={}, 实际={}", expected, actual)
        return passed

    def _assert_jsonpath(self, response, key: str, expected_value: Any) -> bool:
        if response is None:
            logger.error("响应为空，无法执行 jsonpath 断言")
            return False
        try:
            body = response.json() if hasattr(response, "json") else response
            expr = jsonpath_ng.parse(key)
            matches = [m.value for m in expr.find(body)]
            if not matches:
                logger.error("jsonpath 未匹配到值: {}", key)
                return False
            actual = matches[0]
            passed = self._values_match(actual, expected_value)
            if not passed:
                logger.error("jsonpath 断言失败: key={}, 期望={}, 实际={}", key, expected_value, actual)
            return passed
        except Exception as e:
            logger.error("jsonpath 解析失败: {} | {}", key, str(e))
            return False

    def _assert_contains(self, response, expected_value: str) -> bool:
        if response is None:
            return False
        text = response.text if hasattr(response, "text") else str(response)
        passed = str(expected_value) in text
        if not passed:
            logger.error("contains 断言失败: 响应中未找到 '{}'", expected_value)
        return passed

    def _assert_response_time(self, response_time_ms: float, max_ms: Optional[float]) -> bool:
        if max_ms is None:
            return True
        passed = response_time_ms <= max_ms
        if not passed:
            logger.error("响应时间超限: {}ms > {}ms", response_time_ms, max_ms)
        return passed

    def _assert_header(self, response, key: str, expected_value: Any) -> bool:
        if response is None:
            return False
        actual = response.headers.get(key)
        passed = str(actual) == str(expected_value)
        if not passed:
            logger.error("Header 断言失败: key={}, 期望={}, 实际={}", key, expected_value, actual)
        return passed

    def _assert_schema(self, response, schema: Any) -> bool:
        if response is None:
            return False
        try:
            body = response.json() if hasattr(response, "json") else response
            validate(instance=body, schema=schema)
            return True
        except ValidationError as e:
            logger.error("Schema 校验失败: {}", e.message)
            return False
        except Exception as e:
            logger.error("Schema 校验异常: {}", str(e))
            return False

    def _assert_db(self, query: str, expected_value: Any) -> bool:
        if self.db_helper is None:
            logger.warning("DB Helper 未配置，跳过 DB 断言")
            return False
        try:
            result = self.db_helper.query_one(query)
            if result is None:
                logger.error("DB 断言：查询无结果: {}", query)
                return False
            # 取第一个字段值
            actual = list(result.values())[0] if result else None
            passed = self._values_match(actual, expected_value)
            if not passed:
                logger.error("DB 断言失败: SQL={}, 期望={}, 实际={}", query, expected_value, actual)
            return passed
        except Exception as e:
            logger.error("DB 断言异常: {} | {}", query, str(e))
            return False

    def _assert_ui(self, assertion: AssertionItem, ctx: Dict[str, Any]) -> bool:
        """UI 断言由驱动层注入执行（占位，实际在 ui/ 下处理）"""
        logger.warning("UI 断言应在驱动层执行，此处为占位: type={}", assertion.type)
        return False

    def _assert_soft(
        self,
        assertion: AssertionItem,
        response,
        response_time_ms: float,
        ctx: Dict[str, Any],
    ) -> bool:
        """软断言：失败仅记录，不终止"""
        # 复制一份断言并改为非 soft 类型（避免递归）
        sub_assertion = AssertionItem(
            type=assertion.key or "contains",  # key 字段承载子断言类型
            key=None,
            value=assertion.value,
            max_ms=assertion.max_ms,
            not_null=assertion.not_null,
            target=assertion.target,
            comment=assertion.comment,
            query=assertion.query,
        )
        try:
            result = self._evaluate(sub_assertion, response, response_time_ms, ctx)
            if not result:
                msg = assertion.comment or f"软断言失败: {assertion.key}"
                self._soft_failures.append(msg)
                logger.info("软断言失败(仅记录): {}", msg)
            return True  # 软断言不影响整体流程
        except Exception as e:
            msg = f"{assertion.comment}: {str(e)}"
            self._soft_failures.append(msg)
            return True

    # ------------------- 辅助方法 -------------------

    @staticmethod
    def _values_match(actual: Any, expected: Any) -> bool:
        """灵活匹配：支持相等、正则、null、类型匹配"""
        if actual is None and expected is None:
            return True
        if actual is None or expected is None:
            return False

        # 正则匹配（以 ~ 开头）
        if isinstance(expected, str) and expected.startswith("~"):
            pattern = expected[1:]
            return bool(re.search(pattern, str(actual)))

        # 类型转换后再比较
        if isinstance(expected, bool):
            return bool(actual) == expected
        if isinstance(expected, (int, float)):
            try:
                return float(actual) == float(expected)
            except (ValueError, TypeError):
                return str(actual) == str(expected)

        return str(actual) == str(expected)