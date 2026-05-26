"""API 测试引擎 — 调度 API 用例执行、断言、变量提取"""
import json
import re
import time
from typing import Any, Dict, List, Optional

import jsonpath_ng
from loguru import logger

from api.session_manager import SessionManager
from core.assertion_engine import AssertionEngine
from core.case_parser import CaseParser
from core.excel_reader import ExcelReader
from core.hook_manager import HookManager
from core.models import ApiCaseModel, TestResult
from core.variable_manager import VariableManager


class ApiTestEngine:
    """API 测试引擎：加载用例 → 执行请求 → 断言 → 提取变量 → 返回结果"""

    def __init__(
        self,
        session: SessionManager,
        db_helper=None,
    ):
        self.session = session
        self.assertion_engine = AssertionEngine(db_helper=db_helper)
        self.vars = VariableManager()

    def run_case(self, case: ApiCaseModel) -> TestResult:
        """执行单个 API 用例

        Args:
            case: ApiCaseModel 实例
        Returns:
            TestResult 执行结果
        """
        logger.info("━━━ 执行 API 用例: {} | {}", case.case_id, case.case_name)

        # 跳过标记
        if case.skip:
            logger.info("跳过用例: {}", case.case_id)
            return TestResult(case_id=case.case_id, case_name=case.case_name, passed=True)

        # ── 前置钩子 ──
        HookManager.execute(case.pre_hook, {"case": case, "variables": self.vars.get_all()})

        # ── 变量替换 ──
        resolved_url = self._resolve_variables(case.url)
        resolved_headers = self._resolve_dict_variables(case.headers)
        resolved_params = self._resolve_dict_variables(case.params)
        resolved_body = self._resolve_variables(case.body)
        resolved_files = self._resolve_dict_variables(case.files)

        # ── 构建文件上传参数 ──
        upload_files = None
        if resolved_files:
            from utils.file_helper import FileHelper
            upload_files = {}
            for field_name, file_path in resolved_files.items():
                upload_files.update(FileHelper.build_file_payload(field_name, str(file_path)))

        # ── 执行请求 ──
        start_time = time.time()
        response = None
        error_message = ""
        status_code = 0

        try:
            response = self.session.request(
                method=case.method,
                url=resolved_url,
                params=resolved_params,
                json=resolved_body if isinstance(resolved_body, dict) else None,
                data=resolved_body if isinstance(resolved_body, str) else None,
                headers=resolved_headers,
                files=upload_files,
            )
            status_code = response.status_code
        except Exception as e:
            error_message = str(e)
            logger.error("API 请求异常: {}", error_message)

        elapsed_ms = (time.time() - start_time) * 1000

        # ── 响应变量提取 ──
        extract_vars = {}
        if response and response.ok:
            try:
                extract_vars = self._extract_variables(response, case.extract)
                self.vars.set_bulk(extract_vars)
            except Exception as e:
                logger.warning("变量提取失败: {}", e)

        # ── 断言 ──
        assertions_passed = True
        if case.assertions:
            assertions_passed = self.assertion_engine.run(
                assertions=case.assertions,
                response=response,
                response_time_ms=elapsed_ms,
            )

        # ── 后置钩子 ──
        HookManager.execute(
            case.post_hook,
            {
                "case": case,
                "variables": self.vars.get_all(),
                "response": response,
                "extract_vars": extract_vars,
            },
        )

        passed = not error_message and assertions_passed
        if not passed and not error_message:
            error_message = "断言失败"

        result = TestResult(
            case_id=case.case_id,
            case_name=case.case_name,
            passed=passed,
            error_message=error_message,
            response_time_ms=elapsed_ms,
            status_code=status_code,
            response_body=response.json() if response and response.ok else None,
            extract_vars=extract_vars,
        )

        logger.info(
            "用例结果: {} | {} | {}ms",
            "✓ 通过" if passed else "✗ 失败",
            case.case_name,
            f"{elapsed_ms:.0f}",
        )
        return result

    def run_cases(self, cases: List[ApiCaseModel], 
                  dependency_sort: bool = True) -> List[TestResult]:
        """批量执行 API 用例，支持依赖排序和重试"""
        results = []
        executed: Dict[str, TestResult] = {}

        # 简单依赖排序：depends_on 的用例先执行
        if dependency_sort:
            cases = self._sort_by_dependency(cases)

        for case in cases:
            # 检查依赖是否通过
            if case.depends_on and case.depends_on in executed:
                dep_result = executed[case.depends_on]
                if not dep_result.passed:
                    logger.warning("依赖用例 {} 失败，跳过: {}", case.depends_on, case.case_id)
                    results.append(TestResult(
                        case_id=case.case_id,
                        case_name=case.case_name,
                        passed=False,
                        error_message=f"依赖用例失败: {case.depends_on}",
                    ))
                    continue

            # 执行并重试
            max_attempts = case.retry + 1
            result = None
            for attempt in range(max_attempts):
                result = self.run_case(case)
                if result.passed:
                    break
                if attempt < case.retry:
                    logger.info("重试用例 {} ({}/{})", case.case_id, attempt + 1, case.retry)

            results.append(result)
            executed[case.case_id] = result

        return results

    # =================== 内部方法 ===================

    def _resolve_variables(self, value: Any) -> Any:
        """递归替换值中的 {{var_name}} 占位符"""
        if isinstance(value, str):
            return self._resolve_string(value)
        if isinstance(value, dict):
            return {k: self._resolve_variables(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_variables(item) for item in value]
        return value

    def _resolve_string(self, text: str) -> str:
        """替换字符串中的 {{var}} 占位符"""
        def replacer(match):
            var_name = match.group(1)
            # 先查变量管理器，再查内置变量
            val = self.vars.get(var_name)
            if val is not None:
                return str(val)
            # 内置变量
            if var_name == "timestamp":
                return str(int(time.time()))
            if var_name == "uuid":
                import uuid
                return str(uuid.uuid4())
            return match.group(0)
        return re.sub(r"\{\{(\w+)\}\}", replacer, text)

    def _resolve_dict_variables(self, data: dict) -> dict:
        if not data:
            return {}
        resolved = self._resolve_variables(data)
        return resolved if isinstance(resolved, dict) else {}

    def _extract_variables(self, response, extract_rules: Dict[str, str]) -> Dict[str, Any]:
        """从响应中按 jsonpath 提取变量"""
        if not extract_rules or not response:
            return {}
        try:
            body = response.json()
        except json.JSONDecodeError:
            logger.warning("响应非 JSON 格式，无法提取变量")
            return {}

        extracted = {}
        for var_name, jsonpath_expr in extract_rules.items():
            try:
                expr = jsonpath_ng.parse(jsonpath_expr)
                matches = [m.value for m in expr.find(body)]
                if matches:
                    extracted[var_name] = matches[0]
                    logger.debug("提取变量: {} = {}", var_name, matches[0])
                else:
                    logger.warning("jsonpath 未匹配: {} ({})", var_name, jsonpath_expr)
            except Exception as e:
                logger.error("提取变量失败: {} ({}) | {}", var_name, jsonpath_expr, e)

        return extracted

    @staticmethod
    def _sort_by_dependency(cases: List[ApiCaseModel]) -> List[ApiCaseModel]:
        """简易拓扑排序：将带有 depends_on 的用例放到依赖项后面"""
        case_map = {c.case_id: c for c in cases}
        sorted_cases = []
        visited: List[str] = []

        def visit(case):
            if case.case_id in visited:
                return
            if case.depends_on and case.depends_on in case_map:
                visit(case_map[case.depends_on])
            visited.append(case.case_id)
            sorted_cases.append(case)

        for case in cases:
            visit(case)

        return sorted_cases