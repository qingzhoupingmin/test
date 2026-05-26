"""统一测试运行器 — 协调 Excel 解析、用例执行、报告输出"""
import os
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from core.case_parser import CaseParser
from core.excel_reader import ExcelReader
from core.models import ApiCaseModel, TestResult, UiCaseModel
from core.variable_manager import VariableManager


class TestRunner:
    """统一测试运行器，支持：
    - 从 Excel 文件加载用例
    - 按模块/标签过滤
    - API / UI 用例自动分发
    - 汇总生成测试报告数据结构
    """

    def __init__(self):
        self.results: List[TestResult] = []

    def load_cases_from_excel(
        self,
        file_path: str,
        sheet_name: Optional[str] = None,
    ) -> List[Any]:
        """加载 Excel 文件中的所有用例并解析为模型对象"""
        rows = ExcelReader.read_sheet(file_path, sheet_name)
        cases = []
        for row in rows:
            case = CaseParser.parse(row)
            if case:
                cases.append(case)
        logger.info("从 {} 加载了 {} 条用例", file_path, len(cases))
        return cases

    def load_cases_from_directory(
        self,
        directory: str,
        case_type: str = "all",
    ) -> List[Any]:
        """从目录递归加载所有 Excel 用例文件

        Args:
            directory: 用例目录路径
            case_type: api / ui / all
        """
        cases = []
        for root, dirs, files in os.walk(directory):
            for filename in files:
                if not filename.endswith((".xlsx", ".xls")):
                    continue
                filepath = os.path.join(root, filename)
                try:
                    file_cases = self.load_cases_from_excel(filepath)
                    if case_type == "api":
                        file_cases = [c for c in file_cases if isinstance(c, ApiCaseModel)]
                    elif case_type == "ui":
                        file_cases = [c for c in file_cases if isinstance(c, UiCaseModel)]
                    cases.extend(file_cases)
                except Exception as e:
                    logger.warning("加载文件失败: {} | {}", filepath, e)
        logger.info("从目录 {} 共加载 {} 条用例", directory, len(cases))
        return cases

    def filter_cases(
        self,
        cases: List[Any],
        tags: List[str] = None,
        modules: List[str] = None,
        exclude_skip: bool = True,
    ) -> List[Any]:
        """按标签/模块过滤用例"""
        filtered = cases
        if exclude_skip:
            filtered = [c for c in filtered if not getattr(c, "skip", False)]
        if tags:
            filtered = [c for c in filtered if any(t in (getattr(c, "tags", []) or []) for t in tags)]
        if modules:
            filtered = [c for c in filtered if getattr(c, "module", "") in modules]
        logger.info("过滤后剩余 {} 条用例 (tags={}, modules={})", len(filtered), tags, modules)
        return filtered

    def run_api_cases(
        self,
        cases: List[ApiCaseModel],
        api_engine,
        dependency_sort: bool = True,
    ) -> List[TestResult]:
        """执行 API 用例列表"""
        from api.api_engine import ApiTestEngine
        if not cases:
            return []
        results = api_engine.run_cases(cases, dependency_sort=dependency_sort)
        self.results.extend(results)
        return results

    def run_ui_cases(
        self,
        cases: List[UiCaseModel],
        driver,
        screenshot_dir: str = "reports/screenshots",
    ) -> List[TestResult]:
        """执行 UI 用例列表"""
        from ui.ui_engine import UiTestEngine
        if not cases:
            return []
        engine = UiTestEngine(driver=driver, screenshot_dir=screenshot_dir)
        results = engine.run_cases(cases)
        self.results.extend(results)
        return results

    def get_summary(self) -> Dict[str, Any]:
        """生成测试摘要"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        passed_rate = (passed / total * 100) if total > 0 else 0

        summary = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "passed_rate": f"{passed_rate:.1f}%",
            "results": [r.to_dict() for r in self.results],
        }
        return summary

    def print_summary(self) -> None:
        """打印测试摘要"""
        summary = self.get_summary()
        logger.info("=" * 60)
        logger.info("测试摘要")
        logger.info("=" * 60)
        logger.info("总计: {}  通过: {}  失败: {}  通过率: {}",
                    summary["total"], summary["passed"], summary["failed"], summary["passed_rate"])
        for r in self.results:
            if not r.passed:
                logger.info("  ✗ [{}] {} - {}", r.case_id, r.case_name, r.error_message)
        logger.info("=" * 60)