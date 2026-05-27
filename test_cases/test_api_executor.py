"""API 用例统一入口 — 每条用例独立参数化，Allure 报告中各自可见，自动处理依赖链"""
import json
from pathlib import Path
from typing import Dict, List, Tuple

import allure
import pytest
from loguru import logger

from core.file_reader import FileReader
from core.case_parser import CaseParser
from core.models import ApiCaseModel


def _build_curl_command(case: ApiCaseModel) -> str:
    """根据用例构建可复现的 curl 命令"""
    method = case.method.upper()
    parts = ["curl", "-X", method]

    # headers
    if case.headers:
        for k, v in case.headers.items():
            parts.append(f"-H '{k}: {v}'")

    # body
    if case.body:
        if isinstance(case.body, dict):
            parts.append(f"-d '{json.dumps(case.body, ensure_ascii=False)}'")
        else:
            parts.append(f"-d '{case.body}'")

    # params → query string
    url = case.url
    if case.params:
        from urllib.parse import urlencode
        qs = urlencode(case.params, doseq=True)
        url = f"{url}?{qs}" if "?" not in url else f"{url}&{qs}"

    parts.append(f'"{url}"')
    return " \\\n  ".join(parts)


def _parse_all_api_cases() -> Tuple[List[Tuple[str, ApiCaseModel]], Dict[str, ApiCaseModel]]:
    """解析所有支持的用例文件（Excel/CSV/JSON/YAML），返回 (参数化列表, case_id→用例映射)

    使用 FileReader.read_directory 单次 rglob 遍历，避免手动遍历 6 种文件模式。
    """
    all_cases: List[Tuple[str, ApiCaseModel]] = []
    case_map: Dict[str, ApiCaseModel] = {}
    base = Path("data/api")
    if base.exists():
        rows = FileReader.read_directory(str(base))
        for row in rows:
            source_file = row.get("_source_file", "")
            try:
                parsed = CaseParser.parse_multi(row)
                for case in parsed:
                    if isinstance(case, ApiCaseModel):
                        if case.skip:
                            logger.info("跳过用例: {} - {}", case.case_id, case.case_name)
                            continue
                        if case.case_id in case_map:
                            logger.warning("重复 case_id: {}，后出现的将覆盖", case.case_id)
                        all_cases.append((source_file, case))
                        case_map[case.case_id] = case
            except Exception as e:
                logger.warning("解析用例行失败: source={} | {}", source_file, e)
    return all_cases, case_map


# 模块级加载：收集阶段执行一次
_ALL_CASES, _CASE_MAP = _parse_all_api_cases()


def _resolve_dependency_chain(case: ApiCaseModel) -> List[ApiCaseModel]:
    """解析依赖链，返回按依赖顺序排列的用例列表（前置依赖在前）"""
    chain = []
    visited = set()

    def _resolve(c: ApiCaseModel):
        if c.case_id in visited:
            return
        if c.depends_on and c.depends_on in _CASE_MAP:
            _resolve(_CASE_MAP[c.depends_on])
        visited.add(c.case_id)
        chain.append(c)

    _resolve(case)
    return chain


def pytest_generate_tests(metafunc):
    """pytest 参数化钩子 — 为每条 API 用例生成独立测试"""
    if "api_case" in metafunc.fixturenames:
        if _ALL_CASES:
            ids = [f"{c.case_id}-{c.case_name}" for _, c in _ALL_CASES]
            metafunc.parametrize(
                "excel_file,api_case",
                _ALL_CASES,
                ids=ids,
            )
        else:
            metafunc.parametrize(
                "excel_file,api_case",
                [(None, None)],
                ids=["no-cases"],
            )


class TestApiExecutor:
    """API 测试执行器 — 每条用例独立测试"""

    def test_api_case(self, api_case, excel_file, api_engine, global_config, variable_manager):
        """执行单条 API 用例，自动执行依赖链中的前置用例"""
        if api_case is None:
            pytest.skip("没有可执行的 API 测试用例（data/api/ 下无支持的用例文件）")

        # ── 注入配置变量 ──
        variable_manager.set("base_url", global_config.get("base_url", ""))
        custom = global_config.get("custom", {})
        if isinstance(custom, dict):
            variable_manager.set_bulk(custom)

        # ── 解析依赖链（前置用例先去执行） ──
        chain = _resolve_dependency_chain(api_case)
        dependency_cases = chain[:-1]
        target_case = chain[-1]

        # ── 执行依赖链中的前置用例 ──
        if dependency_cases:
            logger.info("用例 {} 依赖链: {}", target_case.case_id,
                        [c.case_id for c in dependency_cases])
            for dep_case in dependency_cases:
                dep_results = api_engine.run_cases([dep_case], dependency_sort=False)
                dep_result = dep_results[0] if dep_results else None
                if dep_result and not dep_result.passed:
                    pytest.skip(f"依赖用例 {dep_case.case_id} 执行失败: {dep_result.error_message}")

        # ── 执行目标用例 ──
        result = api_engine.run_case(target_case)

        # ── Allure 动态元信息 ──
        allure.dynamic.title(f"[{target_case.case_id}] {target_case.case_name}")

        # 描述：按行展示关键信息
        desc_lines = [
            f"case_id: {target_case.case_id}",
            f"method: {target_case.method}",
            f"url: {target_case.url}",
            f"module: {target_case.module or '(未设置)'}",
            f"source: {excel_file}",
        ]
        allure.dynamic.description("\n".join(desc_lines))

        # Feature 分组（按模块分组，未设置则按 URL 路径第一段分组）
        feature_name = target_case.module or target_case.url.strip("/").split("/")[0].upper()
        allure.dynamic.feature(feature_name)

        # 严重级别：按用例 tags 中的 p0/p1/p2/p3 映射
        severity_map = {
            "p0": allure.severity_level.BLOCKER,
            "p1": allure.severity_level.CRITICAL,
            "p2": allure.severity_level.NORMAL,
            "p3": allure.severity_level.MINOR,
        }
        matched_severity = None
        for tag in target_case.tags:
            if tag.lower() in severity_map:
                matched_severity = severity_map[tag.lower()]
                break
        allure.dynamic.severity(matched_severity or allure.severity_level.NORMAL)

        # 标签
        for tag in target_case.tags:
            allure.dynamic.tag(tag)
        if target_case.depends_on:
            allure.dynamic.tag(f"依赖:{target_case.depends_on}")

        # ── 附件：cURL 命令（一键复现） ──
        allure.attach(
            _build_curl_command(target_case),
            name="cURL 命令",
            attachment_type=allure.attachment_type.TEXT,
        )

        # ── 附件：请求信息（结构化 JSON） ──
        request_payload = {
            "method": target_case.method,
            "url": target_case.url,
            "headers": target_case.headers or {},
            "params": target_case.params or {},
            "body": target_case.body,
            "expected_assertions": [
                {"type": a.type, "key": a.key, "value": a.value}
                for a in target_case.assertions
            ],
        }
        allure.attach(
            json.dumps(request_payload, ensure_ascii=False, indent=2, default=str),
            name="请求详情 (JSON)",
            attachment_type=allure.attachment_type.JSON,
        )

        # ── 附件：响应信息 ──
        allure.attach(
            str(result.status_code) if result.status_code else "N/A",
            name="HTTP 状态码",
            attachment_type=allure.attachment_type.TEXT,
        )
        if result.response_time_ms is not None:
            allure.attach(
                f"{result.response_time_ms:.0f} ms",
                name="响应时间",
                attachment_type=allure.attachment_type.TEXT,
            )
        if result.response_body is not None:
            body_str = json.dumps(result.response_body, ensure_ascii=False, indent=2, default=str)
            allure.attach(body_str, name="响应体 (JSON)", attachment_type=allure.attachment_type.JSON)
        if result.extract_vars:
            allure.attach(
                json.dumps(result.extract_vars, ensure_ascii=False, indent=2, default=str),
                name="提取的变量",
                attachment_type=allure.attachment_type.JSON,
            )

        # ── 断言结果逐条展示 ──
        with allure.step("断言结果"):
            for ai, assertion in enumerate(target_case.assertions, 1):
                a_desc = f"#{ai} [{assertion.type}] {assertion.key or assertion.comment or ''}"
                if assertion.type == "status_code":
                    a_desc += f" → 期望={assertion.value}  实际={result.status_code}"
                elif assertion.type == "response_time":
                    a_desc += f" → ≤{assertion.max_ms}ms  实际={result.response_time_ms:.0f}ms"
                elif assertion.type == "db":
                    a_desc += f" → SQL校验"
                elif assertion.type == "soft":
                    a_desc += f" → 软断言"
                else:
                    a_desc += f" → 期望={assertion.value}"
                with allure.step(a_desc):
                    pass

        # ── 断言 ──
        if not result.passed:
            with allure.step(f"失败详情: {result.error_message}"):
                pass
            pytest.fail(f"[{result.case_id}] {result.case_name} 失败: {result.error_message}")
