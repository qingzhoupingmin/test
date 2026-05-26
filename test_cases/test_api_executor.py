"""API 用例统一入口 — 每条用例独立参数化，Allure 报告中各自可见，自动处理依赖链"""
import json
from pathlib import Path
from typing import Dict, List, Tuple

import allure
import pytest
from loguru import logger

from core.excel_reader import ExcelReader
from core.case_parser import CaseParser
from core.models import ApiCaseModel


def _parse_all_api_cases() -> Tuple[List[Tuple[str, ApiCaseModel]], Dict[str, ApiCaseModel]]:
    """解析所有 Excel 文件中的 API 用例，返回 (参数化列表, case_id→用例映射)"""
    all_cases: List[Tuple[str, ApiCaseModel]] = []
    case_map: Dict[str, ApiCaseModel] = {}
    base = Path("data/api")
    if base.exists():
        for f in sorted(base.rglob("*")):
            if f.suffix in (".xlsx", ".xls") and not f.name.startswith("~$"):
                try:
                    sheets = ExcelReader.read_all_sheets(str(f))
                    all_rows = []
                    for sheet_name, rows in sheets.items():
                        for row in rows:
                            row["_source_sheet"] = sheet_name
                        all_rows.extend(rows)
                    for row in all_rows:
                        parsed = CaseParser.parse_multi(row)
                        for case in parsed:
                            if isinstance(case, ApiCaseModel):
                                if case.skip:
                                    logger.info("跳过用例: {} - {}", case.case_id, case.case_name)
                                    continue
                                if case.case_id in case_map:
                                    logger.warning("重复 case_id: {}，后出现的将覆盖", case.case_id)
                                all_cases.append((str(f), case))
                                case_map[case.case_id] = case
                except Exception as e:
                    logger.warning("加载文件失败: {} | {}", f, e)
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
            pytest.skip("没有可执行的 API 测试用例（data/api/ 下无 Excel 文件）")

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
        allure.dynamic.severity(allure.severity_level.NORMAL)

        # 标签
        for tag in target_case.tags:
            allure.dynamic.tag(tag)
        if target_case.depends_on:
            allure.dynamic.tag(f"依赖:{target_case.depends_on}")

        # ── 附件：请求信息 ──
        request_info = []
        request_info.append(f"Method: {target_case.method}")
        request_info.append(f"URL: {target_case.url}")
        if target_case.headers:
            request_info.append(f"Headers: {json.dumps(target_case.headers, ensure_ascii=False, indent=2)}")
        if target_case.params:
            request_info.append(f"Params: {json.dumps(target_case.params, ensure_ascii=False, indent=2)}")
        if target_case.body:
            request_info.append(f"Body: {json.dumps(target_case.body, ensure_ascii=False, indent=2)}")
        if target_case.assertions:
            req_info = [f"  {a.type}: {a.key}={a.value}" for a in target_case.assertions]
            request_info.append(f"预期断言:\n" + "\n".join(req_info))
        allure.attach(
            "\n".join(request_info),
            name="请求详情",
            attachment_type=allure.attachment_type.TEXT,
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

        # ── 断言 ──
        if not result.passed:
            pytest.fail(f"[{result.case_id}] {result.case_name} 失败: {result.error_message}")