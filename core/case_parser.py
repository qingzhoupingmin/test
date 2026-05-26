"""用例解析器 — 将 Excel 原始行数据解析为标准化的 CaseModel 对象"""
from typing import Any, Dict, List, Optional

from loguru import logger

from core.excel_reader import ExcelReader
from core.models import ApiCaseModel, AssertionItem, UiCaseModel, UiStep


class CaseParser:
    """将 Excel 原始行解析为 ApiCaseModel / UiCaseModel。
    自动根据字段判断用例类型（API 有 method 字段，UI 有 steps 字段）。
    """

    @classmethod
    def parse(cls, row: Dict[str, Any]) -> Optional[Any]:
        """自动识别类型并解析"""
        method = row.get("method", "")
        steps = row.get("steps", "")
        if method:
            return cls.parse_api_case(row)
        elif steps:
            return cls.parse_ui_case(row)
        else:
            logger.warning("无法识别用例类型，跳过: {}", row.get("case_id", "unknown"))
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
        skip = str(row.get("skip", "")).strip().upper() == "Y"

        # 标签
        tags_raw = str(row.get("tags", "")).strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        # 解析 JSON 字段
        headers = ExcelReader.parse_json_field(row.get("headers")) or {}
        params = ExcelReader.parse_json_field(row.get("params")) or {}
        body = ExcelReader.parse_json_field(row.get("body"))
        assertions = cls._parse_assertions(row.get("assertions"))
        extract = cls._parse_extract(row.get("extract"))
        files = ExcelReader.parse_json_field(row.get("files")) or {}
        retry = int(row.get("retry", 0)) if row.get("retry") else 0

        return ApiCaseModel(
            case_id=case_id,
            case_name=case_name,
            module=module,
            tags=tags,
            method=method,
            url=url,
            headers=headers,
            params=params,
            body=body,
            files=files,
            extract=extract,
            assertions=assertions,
            depends_on=depends_on,
            pre_hook=pre_hook,
            post_hook=post_hook,
            skip=skip,
            retry=retry,
        )

    @classmethod
    def parse_ui_case(cls, row: Dict[str, Any]) -> UiCaseModel:
        """解析 UI 用例行"""
        case_id = str(row.get("case_id", "")).strip()
        case_name = str(row.get("case_name", "")).strip()
        if not case_id:
            raise ValueError(f"缺少 case_id: {row}")

        module = str(row.get("module", ""))
        page_url = str(row.get("page_url", ""))
        pre_hook = str(row.get("pre_hook", "")).strip() or None
        post_hook = str(row.get("post_hook", "")).strip() or None
        skip = str(row.get("skip", "")).strip().upper() == "Y"
        screenshot_on_fail = str(row.get("screenshot_on_fail", "Y")).strip().upper() != "N"

        tags_raw = str(row.get("tags", "")).strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        wait_after_ms = int(row.get("wait_after_ms", 0)) if row.get("wait_after_ms") else 0

        steps = cls._parse_steps(row.get("steps"))
        assertions = cls._parse_assertions(row.get("assertions"))

        return UiCaseModel(
            case_id=case_id,
            case_name=case_name,
            module=module,
            tags=tags,
            page_url=page_url,
            steps=steps,
            assertions=assertions,
            wait_after_ms=wait_after_ms,
            screenshot_on_fail=screenshot_on_fail,
            skip=skip,
            pre_hook=pre_hook,
            post_hook=post_hook,
        )

    # =================== 内部解析方法 ===================

    @classmethod
    def _parse_assertions(cls, raw: Any) -> List[AssertionItem]:
        """解析断言列表"""
        data = ExcelReader.parse_json_field(raw)
        if data is None:
            return []
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
                target=item.get("target"),
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
            result = {}
            pairs = [p.strip() for p in raw.split(";") if p.strip()]
            for pair in pairs:
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    result[k.strip()] = v.strip()
            return result
        return {}

    @classmethod
    def _parse_steps(cls, raw: Any) -> List[UiStep]:
        """解析 UI 步骤 JSON 数组"""
        data = ExcelReader.parse_json_field(raw)
        if data is None:
            return []
        if not isinstance(data, list):
            logger.warning("steps 格式不是 JSON 数组: {}", raw)
            return []

        steps = []
        for item in data:
            if not isinstance(item, dict):
                continue
            steps.append(UiStep(
                action=item.get("action", ""),
                selector=item.get("selector"),
                value=str(item.get("value", "")) if item.get("value") is not None else None,
                iframe=item.get("iframe"),
            ))
        return steps