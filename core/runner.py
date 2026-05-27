"""统一测试运行器 — 协调多格式文件解析、用例执行、报告输出"""
import os
from typing import Any, Dict, List, Optional

from loguru import logger

from core.case_parser import CaseParser
from core.file_reader import FileReader
from core.models import ApiCaseModel, TestResult


class TestRunner:
    """统一测试运行器，支持：
    - 从 Excel / CSV / JSON / YAML 文件加载用例
    - 按模块/标签过滤
    - API 用例执行
    - 汇总生成测试报告数据结构
    """

    def __init__(self):
        self.results: List[TestResult] = []

    def load_cases_from_file(
        self,
        file_path: str,
        sheet_name: Optional[str] = None,
    ) -> List[Any]:
        """从文件加载用例（自动识别格式：xlsx/xls/csv/json/yaml/yml）

        Args:
            file_path: 用例文件路径
            sheet_name: Sheet 名称（仅 Excel 格式有效）
        Returns:
            解析后的用例模型列表
        """
        rows = FileReader.read_file(file_path, sheet_name)
        cases = []
        for row in rows:
            parsed = CaseParser.parse_multi(row)
            cases.extend(parsed)
        logger.info("从 {} 加载了 {} 条用例", file_path, len(cases))
        return cases

    def load_cases_from_excel(
        self,
        file_path: str,
        sheet_name: Optional[str] = None,
    ) -> List[Any]:
        """加载 Excel 文件中的所有用例并解析为模型对象（向后兼容）

        .. deprecated:: 2.0
            请使用 :func:`load_cases_from_file` 代替。
        """
        import warnings
        warnings.warn(
            "load_cases_from_excel 已弃用，请使用 load_cases_from_file",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.load_cases_from_file(file_path, sheet_name)

    def load_cases_from_directory(
        self,
        directory: str,
        patterns: Optional[List[str]] = None,
        raw_mode: bool = False,
    ) -> List[Any]:
        """从目录递归加载所有支持的用例文件

        Args:
            directory: 目录路径
            patterns: 文件匹配模式列表，默认支持 xlsx/xls/csv/json/yaml/yml
            raw_mode: 是否保留原始值（不调用 to_string），适用于 JSON/YAML 模板变量
        Returns:
            解析后的用例模型列表
        """
        rows = FileReader.read_directory(directory, patterns, raw_mode=raw_mode)
        cases = []
        for row in rows:
            parsed = CaseParser.parse_multi(row)
            cases.extend(parsed)
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
        if not cases:
            return []
        results = api_engine.run_cases(cases, dependency_sort=dependency_sort)
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