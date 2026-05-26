"""Excel 解析器 — 读取 .xlsx 文件，按 Sheet 返回 List[Dict]"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from openpyxl import load_workbook


class ExcelReader:
    """读取 .xlsx 文件，支持：
    - 多 Sheet 读取
    - 行过滤（跳过注释行、空行、skip=Y）
    - 自动 JSON 字符串解析
    """

    @staticmethod
    def read_sheet(file_path: str, sheet_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """读取指定 Sheet 的所有用例行

        Args:
            file_path: Excel 文件路径
            sheet_name: Sheet 名称，默认读取第一个 Sheet
        Returns:
            用例行列表，每行为 dict，key 为表头字段名
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Excel 文件不存在: {file_path}")

        wb = load_workbook(file_path, data_only=True)
        sheet = wb[sheet_name] if sheet_name else wb.active

        logger.debug("读取 Excel: {} → Sheet: {}", file_path, sheet.title)

        rows = list(sheet.iter_rows(values_only=True))
        if len(rows) < 2:
            return []

        # 第一行为表头
        headers = [str(h).strip() if h else "" for h in rows[0]]

        cases = []
        for row_idx, row in enumerate(rows[1:], start=2):
            row_dict = {}
            for idx, header in enumerate(headers):
                value = row[idx] if idx < len(row) else None
                row_dict[header] = value

            # 跳过空行（case_id 为空）
            case_id = row_dict.get("case_id")
            if case_id is None or str(case_id).strip() == "":
                continue

            # 跳过注释行（以 # 开头）
            if str(case_id).startswith("#"):
                continue

            # 跳过标记为 skip=Y 的行
            skip_val = row_dict.get("skip", "")
            if isinstance(skip_val, str) and skip_val.strip().upper() == "Y":
                logger.debug("跳过用例: {} (skip=Y)", case_id)
                continue

            # 清理值：None 转空字符串，保留其他类型
            cleaned = {}
            for k, v in row_dict.items():
                if v is None:
                    cleaned[k] = ""
                elif isinstance(v, float) and v == int(v):
                    # 将 1.0 转为 1，避免数字字段解析问题
                    cleaned[k] = int(v)
                else:
                    cleaned[k] = v

            cases.append(cleaned)

        wb.close()
        logger.info("从 {} 读取到 {} 条用例", file_path, len(cases))
        return cases

    @staticmethod
    def read_all_sheets(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
        """读取所有 Sheet，返回 {sheet_name: List[Dict]}"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Excel 文件不存在: {file_path}")

        wb = load_workbook(file_path, data_only=True)
        result = {}
        for sheet_name in wb.sheetnames:
            result[sheet_name] = ExcelReader.read_sheet(file_path, sheet_name)
        wb.close()
        return result

    @staticmethod
    def read_directory(dir_path: str, pattern: str = "*.xlsx") -> List[Dict[str, Any]]:
        """递归读取目录下所有 Excel 文件的所有 Sheet 用例

        Args:
            dir_path: 目录路径
            pattern: 文件匹配模式，默认 *.xlsx
        Returns:
            所有用例行列表
        """
        base = Path(dir_path)
        if not base.exists():
            logger.warning("目录不存在: {}", dir_path)
            return []

        all_cases = []
        for xlsx_file in sorted(base.rglob(pattern)):
            # 跳过临时文件（以 ~$ 开头）
            if xlsx_file.name.startswith("~$"):
                continue
            try:
                sheets = ExcelReader.read_all_sheets(str(xlsx_file))
                for sheet_name, cases in sheets.items():
                    for case in cases:
                        # 注入来源信息
                        case["_source_file"] = str(xlsx_file)
                        case["_source_sheet"] = sheet_name
                    all_cases.extend(cases)
            except Exception as e:
                logger.error("读取文件失败: {} | 错误: {}", xlsx_file, e)

        logger.info("从目录 {} 共读取到 {} 条用例", dir_path, len(all_cases))
        return all_cases

    @staticmethod
    def parse_json_field(raw: Any) -> Any:
        """安全解析 JSON 字段，支持 str/dict/list 多种输入"""
        if raw is None or raw == "":
            return None
        if isinstance(raw, (dict, list)):
            return raw
        if isinstance(raw, str):
            raw = raw.strip()
            if raw == "":
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("JSON 解析失败，返回原始字符串: {}", raw[:100])
                return raw
        return raw