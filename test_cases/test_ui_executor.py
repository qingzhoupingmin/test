"""UI 用例统一入口 — 从 Excel 加载并执行"""
import os
from pathlib import Path
from typing import List

import pytest
from loguru import logger

from core.runner import TestRunner
from core.models import UiCaseModel


def discover_ui_excel_files(directory: str = "data/cases") -> List[str]:
    """发现 UI 用例 Excel 文件（通过 sheet 名区分：sheet 名含 'ui' 或用例类型为 ui）"""
    files = []
    base = Path(directory)
    if not base.exists():
        logger.warning("用例目录不存在: {}", directory)
        return files
    for f in base.rglob("*.xlsx"):
        if f.name.startswith("~$"):
            continue
        # 简单规则：文件名包含 'ui' 的视为 UI 用例
        if "ui" in f.name.lower():
            files.append(str(f))
    return sorted(files)


UI_EXCEL_FILES = discover_ui_excel_files()
if not UI_EXCEL_FILES:
    UI_EXCEL_FILES = []


def pytest_generate_tests(metafunc):
    if "ui_excel_file" in metafunc.fixturenames:
        metafunc.parametrize("ui_excel_file", UI_EXCEL_FILES)


class TestUiExecutor:
    """UI 测试统一执行器"""

    def test_ui_cases_from_excel(self, ui_excel_file, ui_driver, global_config):
        """从 Excel 执行 UI 用例"""
        from core.excel_reader import ExcelReader
        from core.case_parser import CaseParser

        rows = ExcelReader.read_sheet(ui_excel_file)
        ui_cases = []
        for row in rows:
            case = CaseParser.parse(row)
            if isinstance(case, UiCaseModel):
                ui_cases.append(case)

        logger.info("文件 {} 包含 {} 条 UI 用例", ui_excel_file, len(ui_cases))

        if not ui_cases:
            return

        runner = TestRunner()
        results = runner.run_ui_cases(
            ui_cases, ui_driver,
            screenshot_dir=global_config.get("reporting", {}).get("screenshot_dir", "reports/screenshots"),
        )
        failed = [r for r in results if not r.passed]

        if failed:
            fail_msg = "\n".join(
                f"  ✗ [{r.case_id}] {r.case_name}: {r.error_message}" for r in failed
            )
            pytest.fail(f"UI 测试有 {len(failed)}/{len(results)} 条失败:\n{fail_msg}")