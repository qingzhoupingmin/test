"""文件读取器工厂 — 支持多格式测试用例文件的统一读取入口。

支持的格式：
- .xlsx / .xls : Excel (openpyxl)
- .csv         : CSV (csv 模块，自动编码检测)
- .json        : JSON
- .yaml / .yml : YAML (PyYAML)

设计原则：
- 所有 Reader 输出统一格式：List[Dict[str, Any]]
- 通过 FileReader 工厂类根据扩展名自动分发
- DataCleaner 统一负责清洗、过滤、类型规范化
- 完全向后兼容原有 ExcelReader
"""

import csv
import json
import math
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


# ==================== 字段别名配置 ====================

# 默认字段别名映射：外部文件中的非标准字段名 → 标准字段名
# 用户可在 settings.yaml 中通过 field_aliases 配置项覆盖/扩展
_DEFAULT_FIELD_ALIASES: Dict[str, str] = {
    "request_method": "method",
    "http_method": "method",
    "api_path": "url",
    "request_url": "url",
    "endpoint": "url",
    "test_id": "case_id",
    "test_name": "case_name",
    "depends_on_case_id": "depends_on",
    "description": "case_name",
    "request_headers": "headers",
    "query_params": "params",
    "request_body": "body",
    "payload": "body",
    "expected_status": "assertions",
    "timeout_ms": "timeout",
}

# 核心字段列表：这些字段在 DataCleaner 中强制转为 str 类型
_CORE_STRING_FIELDS = [
    "case_id", "case_name", "method", "url", "module",
    "depends_on", "pre_hook", "post_hook", "skip",
]

# skip 字段中表示"跳过用例"的值（与 CaseParser 保持一致）
_SKIP_TRUE_VALUES = frozenset({"Y", "YES", "TRUE", "是", "1"})


def _load_user_aliases() -> Dict[str, str]:
    """从 settings.yaml 加载用户自定义的字段别名映射。"""
    try:
        from utils.config_loader import load_settings
        settings = load_settings()
        user_aliases = settings.get("field_aliases", {})
        if isinstance(user_aliases, dict) and user_aliases:
            merged = dict(_DEFAULT_FIELD_ALIASES)
            merged.update(user_aliases)
            return merged
    except Exception:
        pass
    return _DEFAULT_FIELD_ALIASES


# ==================== 工具函数 ====================

def parse_json_field(raw: Any) -> Any:
    """安全解析 JSON 字段，支持 str/dict/list 多种输入。

    从 ExcelReader 提取为独立工具函数，供所有 Reader 共用。
    """
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


# ==================== 数据清洗器 ====================

class DataCleaner:
    """统一数据清洗器 — 各 Reader 读取原始数据后统一调用进行清洗。

    职责：
    1. 行过滤（空行、注释行、skip=Y）
    2. 字段类型规范化（核心字段强转 str，None→""）
    3. 字段别名映射（非标准字段名 → 标准字段名）
    4. 数值类型清理（float→int 兼容 Excel）
    """

    @classmethod
    def clean_rows(
        cls,
        rows: List[Dict[str, Any]],
        field_aliases: Optional[Dict[str, str]] = None,
        raw_mode: bool = False,
    ) -> List[Dict[str, Any]]:
        """清洗行数据列表。

        Args:
            rows: 原始行数据列表
            field_aliases: 字段别名映射（None 则自动从配置加载）
            raw_mode: True 表示跳过行过滤和类型规范化，仅做别名映射
        Returns:
            清洗后的行数据列表
        """
        if raw_mode:
            # raw_mode：保留原始数据，仅映射别名
            result = []
            for row in rows:
                mapped = cls._apply_aliases(row, field_aliases)
                result.append(mapped)
            return result

        # 正常模式：完整清洗
        cleaned = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            # 字段别名映射
            row = cls._apply_aliases(row, field_aliases)

            # 跳过空行
            case_id = row.get("case_id")
            if case_id is None or str(case_id).strip() == "":
                continue

            # 跳过注释行
            if str(case_id).startswith("#"):
                continue

            # 跳过 skip=True 的行（与 CaseParser 保持一致的值集合）
            skip_val = row.get("skip", "")
            if isinstance(skip_val, str) and skip_val.strip().upper() in _SKIP_TRUE_VALUES:
                logger.debug("跳过用例: {} (skip={})", case_id, skip_val)
                continue

            # 规范化字段类型和值
            normalized = cls._normalize_row(row)
            cleaned.append(normalized)

        return cleaned

    @classmethod
    def _normalize_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        """规范化单行数据：核心字段强转 str，None→""，float→int 兼容。"""
        result = {}
        for k, v in row.items():
            # None → ""
            if v is None:
                result[k] = ""
                continue

            # 核心字段强制转字符串
            if k in _CORE_STRING_FIELDS and not isinstance(v, str):
                result[k] = str(v)
                continue

            # Excel 数值兼容：1.0 → 1（跳过 NaN/Inf 等非有限值）
            if isinstance(v, float) and math.isfinite(v) and v == int(v):
                result[k] = int(v)
                continue

            result[k] = v

        # 确保核心字段至少存在（即使为空）
        for field in _CORE_STRING_FIELDS:
            if field not in result:
                result[field] = ""

        return result

    @classmethod
    def _apply_aliases(
        cls,
        row: Dict[str, Any],
        field_aliases: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """将非标准字段名映射为标准字段名。

        例如：{"request_method": "POST"} → {"method": "POST"}
        """
        if field_aliases is None:
            field_aliases = _load_user_aliases()

        if not field_aliases:
            return row

        result = {}
        for k, v in row.items():
            mapped_key = field_aliases.get(k)
            if mapped_key:
                # 若目标字段已存在，不覆盖
                if mapped_key not in result:
                    result[mapped_key] = v
                else:
                    logger.debug("字段别名冲突: '{}' → '{}' 被忽略（目标字段已存在值）", k, mapped_key)
            else:
                result[k] = v

        return result


# ==================== CSV Reader ====================

class CsvReader:
    """CSV 文件读取器。

    CSV 格式与 Excel 表头格式完全一致：
    - 第一行为表头（列名）
    - 后续行为用例数据
    - 自动编码检测（utf-8-sig → gbk → gb2312 → latin-1）
    """

    # 编码检测顺序
    _ENCODINGS = ["utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030", "latin-1"]

    @staticmethod
    def read_file(file_path: str) -> List[Dict[str, Any]]:
        """读取 CSV 文件中的所有用例行。

        Args:
            file_path: CSV 文件路径
        Returns:
            用例行列表（已清洗）
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV 文件不存在: {file_path}")

        rows = CsvReader._read_with_encoding_fallback(file_path)
        if not rows:
            return []

        return DataCleaner.clean_rows(rows)

    @classmethod
    def _read_with_encoding_fallback(cls, file_path: str) -> List[Dict[str, Any]]:
        """尝试多种编码读取 CSV，返回原始行数据。"""
        for encoding in cls._ENCODINGS:
            try:
                return cls._read_raw(file_path, encoding)
            except (UnicodeDecodeError, UnicodeError):
                logger.debug(f"编码 {encoding} 失败，尝试下一种...")
                continue
            except Exception as e:
                logger.warning(f"编码 {encoding} 读取异常: {e}")
                continue

        # 所有编码都失败，使用 errors="replace" 兜底
        logger.warning(f"CSV 编码检测全部失败，使用 utf-8 + replace 兜底: {file_path}")
        try:
            return cls._read_raw(file_path, "utf-8", errors="replace")
        except Exception as e:
            raise ValueError(f"无法读取 CSV 文件: {file_path}，错误: {e}")

    @staticmethod
    def _read_raw(file_path: str, encoding: str, errors: str = "strict") -> List[Dict[str, Any]]:
        """读取 CSV 原始数据。"""
        with open(file_path, "r", encoding=encoding, errors=errors) as f:
            reader = csv.DictReader(f)
            rows = []
            for row_dict in reader:
                # 清理 None 键（DictReader 可能产生 None 表头）
                cleaned_row = {
                    (k if k is not None else ""): v
                    for k, v in row_dict.items()
                }
                rows.append(cleaned_row)

        if rows:
            detected_enc = encoding if errors == "strict" else f"{encoding}(replace)"
            logger.debug("CSV 编码 {} 读取成功: {}", detected_enc, file_path)

        return rows


# ==================== JSON Reader ====================

class JsonReader:
    """JSON 文件读取器。

    支持两种 JSON 结构：
    1. 单条对象: { "case_id": "...", "method": "...", ... }
    2. 多条数组: [ { "case_id": "...", ... }, ... ]

    注意：JSON 值保留原生类型，如需使用 {{ }} 模板替换请配置 raw_mode。
    """

    @staticmethod
    def read_file(
        file_path: str,
        raw_mode: bool = False,
    ) -> List[Dict[str, Any]]:
        """读取 JSON 文件中的用例。

        Args:
            file_path: JSON 文件路径
            raw_mode: True 时跳过类型规范化（适用于含模板变量的 JSON）
        Returns:
            用例行列表（已清洗）
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"JSON 文件不存在: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            rows = [data]
        elif isinstance(data, list):
            rows = data
        else:
            raise ValueError(f"JSON 格式不支持: 预期 dict 或 list，实际为 {type(data)}")

        # 过滤掉非 dict 条目
        rows = [r for r in rows if isinstance(r, dict)]

        return DataCleaner.clean_rows(rows, raw_mode=raw_mode)


# ==================== YAML Reader ====================

class YamlReader:
    """YAML 文件读取器。

    支持两种 YAML 结构：
    1. 单条对象（dict）
    2. 多条数组（list of dict）

    注意：YAML 值保留原生类型，如需使用 {{ }} 模板替换请配置 raw_mode。

    依赖 PyYAML 库。
    """

    @staticmethod
    def read_file(
        file_path: str,
        raw_mode: bool = False,
    ) -> List[Dict[str, Any]]:
        """读取 YAML 文件中的用例。

        Args:
            file_path: YAML 文件路径
            raw_mode: True 时跳过类型规范化（适用于含模板变量的 YAML）
        Returns:
            用例行列表（已清洗）
        """
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "读取 YAML 文件需要 PyYAML 库，请执行: pip install pyyaml"
            )

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"YAML 文件不存在: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            return []

        if isinstance(data, dict):
            rows = [data]
        elif isinstance(data, list):
            rows = data
        else:
            raise ValueError(f"YAML 格式不支持: 预期 dict 或 list，实际为 {type(data)}")

        # 过滤掉非 dict 条目
        rows = [r for r in rows if isinstance(r, dict)]

        return DataCleaner.clean_rows(rows, raw_mode=raw_mode)


# ==================== 统一工厂 ====================

class FileReader:
    """统一文件读取器工厂。

    根据文件扩展名自动分发到对应的 Reader。
    所有 Reader 输出的行数据已通过 DataCleaner 统一清洗。
    """

    # 扩展名映射
    READER_MAP = {
        ".xlsx": "excel",
        ".xls": "excel",
        ".csv": "csv",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
    }

    # 支持的文件扩展名列表（用于错误提示）
    SUPPORTED_EXTENSIONS = list(READER_MAP.keys())

    # 默认支持的文件扩展名模式
    DEFAULT_PATTERNS = ["*.xlsx", "*.xls", "*.csv", "*.json", "*.yaml", "*.yml"]

    @classmethod
    def read_file(
        cls,
        file_path: str,
        sheet_name: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """根据文件扩展名读取用例。

        Args:
            file_path: 文件路径
            sheet_name: Sheet 名称（仅 Excel 格式有效）
            **kwargs: 传递给具体 Reader 的额外参数
        Returns:
            用例行列表（已清洗）
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext in (".xlsx", ".xls"):
            from core.excel_reader import ExcelReader
            return ExcelReader.read_sheet(file_path, sheet_name)
        elif ext == ".csv":
            return CsvReader.read_file(file_path)
        elif ext == ".json":
            return JsonReader.read_file(file_path, **kwargs)
        elif ext in (".yaml", ".yml"):
            return YamlReader.read_file(file_path, **kwargs)
        else:
            _raise_unsupported_format(ext, file_path)

    @classmethod
    def read_all_sheets(cls, file_path: str) -> Dict[str, List[Dict[str, Any]]]:
        """读取 Excel 文件的所有 Sheet（仅 Excel 格式）。"""
        path = Path(file_path)
        ext = path.suffix.lower()
        if ext in (".xlsx", ".xls"):
            from core.excel_reader import ExcelReader
            return ExcelReader.read_all_sheets(file_path)
        else:
            # 非 Excel 格式，以文件名作为 key
            return {path.stem: cls.read_file(file_path)}

    @classmethod
    def read_directory(
        cls,
        dir_path: str,
        patterns: Optional[List[str]] = None,
        raw_mode: bool = False,
    ) -> List[Dict[str, Any]]:
        """递归读取目录下所有支持的用例文件（单次 rglob 遍历，高性能）。

        Args:
            dir_path: 目录路径
            patterns: 文件匹配模式列表，默认支持 xlsx/xls/csv/json/yaml/yml
            raw_mode: True 时 JSON/YAML 跳过类型规范化（适用于含模板变量的文件）
        Returns:
            所有用例行列表
        """
        base = Path(dir_path)
        if not base.exists():
            logger.warning("目录不存在: {}", dir_path)
            return []

        # 构建扩展名白名单（从 patterns 中提取）
        if patterns is None:
            valid_exts = set(cls.SUPPORTED_EXTENSIONS)
        else:
            valid_exts = set()
            for p in patterns:
                ext = Path(p).suffix.lower()
                if ext:
                    valid_exts.add(ext)

        all_cases = []
        # 单次 rglob 遍历所有文件，按扩展名分流
        for matched_file in sorted(base.rglob("*")):
            if not matched_file.is_file():
                continue
            # 跳过临时文件
            if matched_file.name.startswith("~$"):
                continue

            ext = matched_file.suffix.lower()
            if ext not in valid_exts:
                continue

            logger.debug("发现文件: {}", matched_file)
            try:
                if ext in (".xlsx", ".xls"):
                    sheets = cls.read_all_sheets(str(matched_file))
                    for sheet_name, cases in sheets.items():
                        for case in cases:
                            case["_source_file"] = str(matched_file)
                            case["_source_sheet"] = sheet_name
                        all_cases.extend(cases)
                else:
                    cases = cls.read_file(str(matched_file), raw_mode=raw_mode)
                    for case in cases:
                        case["_source_file"] = str(matched_file)
                        case["_source_sheet"] = ""
                    all_cases.extend(cases)
            except Exception as e:
                logger.error("读取文件失败: {} | 错误: {}", matched_file, e)

        logger.info("从目录 {} 共读取到 {} 条用例", dir_path, len(all_cases))
        return all_cases

    @classmethod
    def parse_json_field(cls, raw: Any) -> Any:
        """安全解析 JSON 字段（转发到工具函数，保持向后兼容）。"""
        return parse_json_field(raw)


def _raise_unsupported_format(ext: str, file_path: str) -> None:
    """抛出友好的格式不支持错误。"""
    supported = ", ".join(sorted(FileReader.SUPPORTED_EXTENSIONS))
    msg = (
        f'不支持的文件格式 "{ext}"（文件: {file_path}）。\n'
        f"支持的格式: {supported}\n"
        f"提示：请将用例转换为以上任一格式，或参考架构设计文档添加自定义 Reader。"
    )
    raise ValueError(msg)