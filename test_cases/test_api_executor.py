"""API 用例统一入口 — 从 Excel 加载并执行"""
import os
from pathlib import Path
from typing import List

import pytest
from loguru import logger

from core.runner import TestRunner
from core.excel_reader import ExcelReader
from core.case_parser import CaseParser
from core.models import ApiCaseModel


def discover_api_excel_files(directory: str = "data/cases") -> List[str]:
    """发现目录下所有 Excel 用例文件"""
    base = Path(directory)
    if not base.exists():
        logger.warning("用例目录不存在: {}", directory)
        return []
    files = []
    for f in base.rglob("*"):
        if f.suffix in (".xlsx", ".xls") and not f.name.startswith("~$"):
            files.append(str(f))
    return sorted(files)


EXCEL_FILES = discover_api_excel_files()


def pytest_generate_tests(metafunc):
    """pytest 参数化钩子 — 为每个 Excel 文件生成一个测试"""
    if "excel_file" in metafunc.fixturenames and EXCEL_FILES:
        metafunc.parametrize("excel_file", EXCEL_FILES)


class TestApiExecutor:
    """API 测试统一执行器"""

    def test_api_cases_from_excel(self, excel_file, api_engine, global_config):
        """从 Excel 文件执行所有 API 用例"""
        # 解析 Excel 中的 API 用例（支持数据驱动）
        rows = ExcelReader.read_sheet(excel_file)
        api_cases = []
        for row in rows:
            parsed = CaseParser.parse_multi(row)
            for case in parsed:
                if isinstance(case, ApiCaseModel):
                    api_cases.append(case)

        logger.info("文件 {} 包含 {} 条 API 用例", excel_file, len(api_cases))

        if not api_cases:
            return

        # 通过 runner 执行
        runner = TestRunner()
        results = runner.run_api_cases(api_cases, api_engine)
        failed = [r for r in results if not r.passed]

        if failed:
            fail_msg = "\n".join(
                f"  ✗ [{r.case_id}] {r.case_name}: {r.error_message}" for r in failed
            )
            pytest.fail(f"API 测试有 {len(failed)}/{len(results)} 条失败:\n{fail_msg}")