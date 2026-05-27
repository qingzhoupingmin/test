"""用例解析器 — 将多格式原始行数据（Excel/CSV/JSON/YAML）解析为标准化的 CaseModel 对象"""
from typing import Any, Dict, List, Optional

from loguru import logger

from core.file_reader import FileReader, parse_json_field
from core.models import ApiCaseModel, AssertionItem


class CaseParser:
    """将多格式原始行解析为 ApiCaseModel。
    支持 params_file 数据驱动：模板行 + 外部参数文件 → 多条用例。
    """

    @classmethod
    def parse(cls, row: Dict[str, Any]) -> Optional[Any]:
        """自动识别类型并解析（单条）"""
        return cls._parse_single(row)

    @classmethod
    def parse_multi(cls, row: Dict[str, Any]) -> List[Any]:
        """解析一行（可能含数据驱动），返回用例列表

        如果 row 中存在 params_file 字段，则以此行为模板，
        从参数文件加载数据批量生成用例；否则返回单条用例。
        """
        params_file = str(row.get("params_file", "")).strip()
        if not params_file:
            case = cls._parse_single(row)
            return [case] if case else []

        # 数据驱动模式：加载模板并批量生成
        from core.data_driver import DataDriver
        params_sheet = str(row.get("params_sheet", "")).strip() or None

        params_list = DataDriver.load_params_from_file(params_file, sheet_name=params_sheet)

        if not params_list:
            logger.warning("参数文件 {} 无数据，跳过数据驱动展开", params_file)
            return []

        generated_rows = DataDriver.generate_cases(row, params_list)
        cases = []
        for gen_row in generated_rows:
            case = cls._parse_single(gen_row)
            if case:
                cases.append(case)

        logger.info("数据驱动展开: {} → {} 条用例", row.get("case_id", "?"), len(cases))
        return cases

    # =================== 内部：单行解析 ===================

    @classmethod
    def _parse_single(cls, row: Dict[str, Any]) -> Optional[Any]:
        """解析单行用例（不含数据驱动）"""
        method = row.get("method", "")
        if method:
            return cls.parse_api_case(row)
        else:
            logger.warning("跳过非 API 用例 (缺少 method 字段): {}", row.get("case_id", "unknown"))
            return None

    @classmethod
    def parse_api_case(cls, row: Dict[str, Any]) -> ApiCaseModel:
        """解析 API 用例行"""
        case_id = str(row.get("case_id", "")).strip()
        case_name = str(row.get("case_name", "")).strip()
        if not case_id:
            raise ValueError(f"缺少 case_id: {row}")

        # 基础字段
        module = str(row.get("module", ""))
        method = str(row.get("method", "GET")).strip().upper()
        url = str(row.get("url", "")).strip()
        depends_on = str(row.get("depends_on", "")).strip() or None
        pre_hook = str(row.get("pre_hook", "")).strip() or None
        post_hook = str(row.get("post_hook", "")).strip() or None
        skip_raw = str(row.get("skip", "")).strip().upper()
        skip = skip_raw in ("Y", "YES", "TRUE", "是", "1")

        # 标签（兼容 str 逗号分隔 和 list 两种格式）
        tags_raw = row.get("tags", "")
        if isinstance(tags_raw, list):
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]
        else:
            tags_str = str(tags_raw).strip()
            tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        # 解析 JSON 字段
        headers = parse_json_field(row.get("headers")) or {}
        params = parse_json_field(row.get("params")) or {}
        body = parse_json_field(row.get("body"))
        assertions = cls._parse_assertions(row.get("assertions"))
        extract = cls._parse_extract(row.get("extract"))
        files = parse_json_field(row.get("files")) or {}
        retry = int(row.get("retry", 0)) if row.get("retry") else 0
        payload_type = str(row.get("payload_type", "")).strip() or None
        priority = str(row.get("priority", "")).strip() or None

        case = ApiCaseModel(
            case_id=case_id,
            case_name=case_name,
            module=module,
            tags=tags,
            priority=priority,
            method=method,
            url=url,
            headers=headers,
            params=params,
            body=body,
            files=files,
            payload_type=payload_type,
            extract=extract,
            assertions=assertions,
            depends_on=depends_on,
            pre_hook=pre_hook,
            post_hook=post_hook,
            skip=skip,
            retry=retry,
        )
        return case

    # =================== 内部解析方法 ===================

    @classmethod
    def _parse_assertions(cls, raw: Any) -> List[AssertionItem]:
        """解析断言列表

        支持三种输入格式：
        1. JSON 数组: [{"type":"status_code","value":200}, ...]
        2. 简写数字: 200 → 自动包装为 [{"type":"status_code","value":200}]
        3. 简写字符串: "200" → 自动包装为 [{"type":"status_code","value":200}]
        """
        data = parse_json_field(raw)
        if data is None:
            return []

        # 简写格式：expected_status = 200 或 "200"
        if isinstance(data, (int, float)):
            return [AssertionItem(type="status_code", value=int(data), comment="expected_status")]
        if isinstance(data, str) and data.strip().isdigit():
            return [AssertionItem(type="status_code", value=int(data.strip()), comment="expected_status")]

        if not isinstance(data, list):
            logger.warning("断言格式不是 JSON 数组: {}", raw)
            return []

        items = []
        for item in data:
            if not isinstance(item, dict):
                continue
            items.append(AssertionItem(
                type=item.get("type", ""),
                key=item.get("key"),
                value=item.get("value"),
                max_ms=item.get("max_ms"),
                not_null=item.get("not_null", False),
                comment=item.get("comment"),
                query=item.get("query"),
            ))
        return items

    @classmethod
    def _parse_extract(cls, raw: Any) -> Dict[str, str]:
        """解析响应提取规则
        支持两种格式：
          - JSON 对象: {"token": "$.data.token", "user_id": "$.data.id"}
          - 简写字符串: "token=$.data.token; user_id=$.data.id"
        """
        if not raw:
            return {}
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
        if isinstance(raw, str):
            # 先尝试 JSON 解析
            try:
                import json
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return {str(k): str(v) for k, v in parsed.items()}
            except (json.JSONDecodeError, ValueError):
                pass
            # 再尝试简写格式
            result = {}
            pairs = [p.strip() for p in raw.split(";") if p.strip()]
            for pair in pairs:
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    result[k.strip()] = v.strip()
            return result
        return {}
