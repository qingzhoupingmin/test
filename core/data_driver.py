"""数据驱动模块 — 支持参数化数据批量生成用例"""
import copy
from typing import Any, Dict, List, Optional

from loguru import logger

from core.file_reader import FileReader


class DataDriver:
    """从 Excel / CSV / JSON / YAML 数据文件加载参数化数据，与用例模板合并生成批量测试用例"""

    @staticmethod
    def load_params_from_file(
        file_path: str,
        sheet_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """从任意支持格式加载参数化数据（自动识别文件类型）

        Args:
            file_path: 参数文件路径（支持 xlsx/xls/csv/json/yaml/yml）
            sheet_name: Sheet 名称（仅 Excel 格式有效）
        Returns:
            参数数据列表
        """
        return FileReader.read_file(file_path, sheet_name)

    @staticmethod
    def load_params_from_excel(
        file_path: str,
        sheet_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """加载 Excel 参数化数据（向后兼容）"""
        from core.excel_reader import ExcelReader
        return ExcelReader.read_sheet(file_path, sheet_name)

    @staticmethod
    def load_params_from_csv(file_path: str) -> List[Dict[str, Any]]:
        """从 CSV 加载参数化数据（向后兼容）"""
        from core.file_reader import CsvReader
        return CsvReader.read_file(file_path)

    @classmethod
    def generate_cases(
        cls,
        template: Dict[str, Any],
        params_list: List[Dict[str, Any]],
        case_id_field: str = "case_id",
        case_name_field: str = "case_name",
    ) -> List[Dict[str, Any]]:
        """将模板与参数列表合并，生成独立用例行列表

        Args:
            template: 用例模板字典
            params_list: 参数列表
            case_id_field: 参数中作为 case_id 的字段
            case_name_field: 参数中作为 case_name 的字段
        Returns:
            合并后的用例列表
        """
        cases = []
        for params in params_list:
            row = copy.deepcopy(template)

            # 替换 case_id 和 case_name
            if case_id_field in params:
                row["case_id"] = str(params[case_id_field])
            if case_name_field in params:
                row["case_name"] = str(params[case_name_field])

            # 将参数合并到用例中（可被模板引用替换）
            for key, value in params.items():
                row[f"_param_{key}"] = value

            # 执行模板变量替换：{{name}} → params_value
            row = cls._replace_template_vars(row, params)
            cases.append(row)

        logger.info("数据驱动生成 {} 条用例", len(cases))
        return cases

    @classmethod
    def _replace_template_vars(cls, row: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """将模板中的 {{key}} 替换为 params 中对应的值"""
        import re

        def replacer(obj):
            if isinstance(obj, str):
                def _sub(match):
                    key = match.group(1) or match.group(2)
                    return str(params.get(key, match.group(0)))
                return re.sub(r"\{\{(\w+)\}\}|\$\{(\w+)\}", _sub, obj)
            if isinstance(obj, dict):
                return {k: replacer(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [replacer(item) for item in obj]
            return obj

        return replacer(row)