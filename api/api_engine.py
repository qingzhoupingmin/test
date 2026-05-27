"""API 测试引擎 — 调度 API 用例执行、断言、变量提取"""
import json
import re
import time
from typing import Any, Dict, List, Optional

import allure
import jsonpath_ng
from loguru import logger

from api.session_manager import SessionManager
from core.assertion_engine import AssertionEngine
from core.case_parser import CaseParser
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

        response = None
        error_message = ""
        status_code = 0
        elapsed_ms = 0.0
        extract_vars = {}
        assertions_passed = True

        try:
            # ── 前置钩子 ──
            HookManager.execute(case.pre_hook, {"case": case, "variables": self.vars.get_all()})

            # ── 变量替换 ──
            with allure.step("变量解析与替换"):
                resolved_url = self._resolve_variables(case.url)
                resolved_headers = self._resolve_dict_variables(case.headers)
                resolved_params = self._resolve_dict_variables(case.params)
                resolved_body = self._resolve_variables(case.body)
                resolved_files = self._resolve_dict_variables(case.files)
                if case.extract:
                    allure.attach(
                        json.dumps(case.extract, ensure_ascii=False, indent=2),
                        name="提取规则",
                        attachment_type=allure.attachment_type.JSON,
                    )

            # ── 构建文件上传参数 ──
            upload_files = None
            if resolved_files:
                from utils.file_helper import FileHelper
                upload_files = {}
                for field_name, file_path in resolved_files.items():
                    upload_files.update(FileHelper.build_file_payload(field_name, str(file_path)))

            # ── 执行请求 ──
            with allure.step(f"发送 {case.method} 请求"):
                start_time = time.time()
                try:
                    request_kwargs, resolved_headers = self._build_request_kwargs(
                        resolved_body, case.payload_type, resolved_headers, upload_files
                    )
                    response = self.session.request(
                        method=case.method,
                        url=resolved_url,
                        params=resolved_params,
                        headers=resolved_headers,
                        **request_kwargs,
                    )
                    status_code = response.status_code
                except Exception as e:
                    error_message = str(e)
                    logger.error("API 请求异常: {}", error_message)
                elapsed_ms = (time.time() - start_time) * 1000

            # ── 响应变量提取 ──
            if response and response.ok:
                with allure.step("响应变量提取"):
                    try:
                        extract_vars = self._extract_variables(response, case.extract)
                        self.vars.set_bulk(extract_vars)
                        if extract_vars:
                            allure.attach(
                                json.dumps(extract_vars, ensure_ascii=False, indent=2, default=str),
                                name="提取结果",
                                attachment_type=allure.attachment_type.JSON,
                            )
                    except Exception as e:
                        logger.warning("变量提取失败: {}", e)

            # ── 断言 ──
            if case.assertions:
                with allure.step(f"执行断言 ({len(case.assertions)} 条)"):
                    assertions_passed = self.assertion_engine.run(
                        assertions=case.assertions,
                        response=response,
                        response_time_ms=elapsed_ms,
                        status_code=status_code,
                        extra_context={"status_code": status_code},
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
                response_body=(response.json() if response.ok else response.text) if response else None,
                extract_vars=extract_vars,
            )

            logger.info(
                "用例结果: {} | {} | {}ms",
                "✓ 通过" if passed else "✗ 失败",
                case.case_name,
                f"{elapsed_ms:.0f}",
            )
            return result

        finally:
            # ── 后置钩子（try-finally 保证异常时也会执行） ──
            try:
                HookManager.execute(
                    case.post_hook,
                    {
                        "case": case,
                        "variables": self.vars.get_all(),
                        "response": response,
                        "extract_vars": extract_vars,
                    },
                )
            except Exception as e:
                logger.warning("后置钩子执行失败: {}", e)

            # ── 用例结束：回收 CASE 变量 ──
            self.vars.clear_case()

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

    @staticmethod
    def _build_request_kwargs(
        body: Any,
        payload_type: Optional[str],
        headers: Dict[str, str],
        files: Optional[Dict[str, Any]],
    ) -> tuple:
        """根据 payload_type 构建 requests.request 所需的关键字参数。

        处理五种 payload 类型：
        - JSON:       json=body (body 为 dict 或 list，自动设 Content-Type: application/json)
        - FORM:       data=body (body 为 dict，requests 自动编码为 application/x-www-form-urlencoded)
        - XML:        data=body (body 为 str，设置 Content-Type: application/xml)
        - MULTIPART:  data=body, files=files (body 为 dict 时传表单字段)
        - None/默认:  自动推断 body 类型 (dict/list→json, str→data)

        Args:
            body: 解析后的请求体
            payload_type: 请求体类型（JSON/FORM/XML/MULTIPART），None 时自动推断
            headers: 已解析的请求头字典（会被原地修改以添加 Content-Type）
            files: 文件上传参数字典

        Returns:
            (kwargs_dict, headers_dict) 传入 self.session.request(**kwargs)
        """
        pt = (payload_type or "").strip().upper()
        kwargs = {}
        if files:
            kwargs["files"] = files

        if body is None or body == "":
            return kwargs, headers

        if pt == "JSON":
            # JSON 请求体：支持 dict 和 list 类型
            if isinstance(body, (dict, list)):
                kwargs["json"] = body
            elif isinstance(body, str):
                try:
                    kwargs["json"] = json.loads(body)
                except json.JSONDecodeError:
                    kwargs["data"] = body
            else:
                kwargs["json"] = body
        elif pt == "FORM":
            # x-www-form-urlencoded
            if isinstance(body, dict):
                kwargs["data"] = body
            elif isinstance(body, str):
                kwargs["data"] = body
            else:
                kwargs["data"] = body
        elif pt == "XML":
            headers["Content-Type"] = "application/xml"
            kwargs["data"] = body if isinstance(body, str) else str(body)
        elif pt == "MULTIPART":
            # multipart/form-data：body 为 dict 时传 data，有 files 则一起
            if isinstance(body, dict):
                kwargs["data"] = body
            elif isinstance(body, str):
                kwargs["data"] = body
            elif body is not None:
                kwargs["data"] = body
        else:
            # 自动推断
            if isinstance(body, (dict, list)):
                kwargs["json"] = body
            elif isinstance(body, str):
                kwargs["data"] = body
            elif body is not None:
                kwargs["data"] = body

        return kwargs, headers

    def _resolve_variables(self, value: Any) -> Any:
        """递归替换值中的 {{var_name}} 占位符"""
        if isinstance(value, str):
            return self._resolve_string(value)
        if isinstance(value, dict):
            return {k: self._resolve_variables(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_variables(item) for item in value]
        return value

    # 内置函数注册表
    _BUILTIN_FUNCTIONS = {
        "timestamp": lambda: str(int(time.time())),
        "timestamp_ms": lambda: str(int(time.time() * 1000)),
        "uuid": lambda: __import__("uuid").uuid4().hex,
        "random_string": lambda n=8: "".join(
            __import__("random").choices(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ", k=int(n)
            )
        ),
        "random_int": lambda a=0, b=10000: str(__import__("random").randint(int(a), int(b))),
        "date_now": lambda fmt="%Y-%m-%d": __import__("datetime").datetime.now().strftime(str(fmt)),
        "phone": lambda: "1" + "".join(
            __import__("random").choices("3456789", k=1)
        ) + "".join(__import__("random").choices("0123456789", k=8)),
    }

    def _resolve_string(self, text: str) -> str:
        """替换字符串中的占位符，支持三种语法：
        - {{var}}          变量引用（CASE → SESSION → GLOBAL 查找）
        - ${func()}        内置函数调用（可选参数，如 ${random_string(8)}）
        - ${var:default}   带默认值的变量引用
        """
        # 第一步：匹配 ${func(args)} 和 ${var:default}
        pattern_dynamic = re.compile(
            r"\$\{(\w+)(?:\(([^)]*)\))?(?::([^}]*))?\}"
        )

        def replacer_dynamic(match):
            name = match.group(1)      # 变量名或函数名
            args = match.group(2)      # 函数参数（可选）
            default = match.group(3)   # 默认值（可选）

            # 情况1：内置函数调用（带参数或空括号）${func()} 或 ${func(args)}
            if args is not None:
                func = self._BUILTIN_FUNCTIONS.get(name)
                if func:
                    try:
                        stripped = args.strip()
                        if stripped == "":
                            return func()
                        params = [p.strip().strip("\"'") for p in stripped.split(",")]
                        return func(*params)
                    except (ValueError, TypeError) as e:
                        logger.warning("内置函数 {} 调用失败: {}", name, e)
                        return match.group(0)
                # 不是内置函数，回退到变量查找
                val = self.vars.get(name)
                if val is not None:
                    return str(val)
                return match.group(0)

            # 情况2：带默认值的变量引用 ${var:default}
            if default is not None:
                val = self.vars.get(name)
                if val is not None:
                    return str(val)
                return default

            # 情况3：无参数内置函数调用 ${func()}
            func = self._BUILTIN_FUNCTIONS.get(name)
            if func:
                try:
                    return func()
                except Exception as e:
                    logger.warning("内置函数 {} 调用失败: {}", name, e)

            # 情况4：普通变量引用 ${var}
            val = self.vars.get(name)
            if val is not None:
                return str(val)
            return match.group(0)

        # 第二步：匹配 {{var}} 语法
        pattern_curly = re.compile(r"\{\{(\w+)\}\}")

        def replacer_curly(match):
            var_name = match.group(1)
            val = self.vars.get(var_name)
            if val is not None:
                return str(val)
            return match.group(0)

        # 先处理 ${...} 再处理 {{...}}（避免嵌套冲突）
        text = pattern_dynamic.sub(replacer_dynamic, text)
        text = pattern_curly.sub(replacer_curly, text)
        return text

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