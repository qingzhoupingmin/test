"""数据模型定义 — API/UI 用例模型、断言项、步骤等"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AssertionItem:
    """单条断言"""
    type: str                              # status_code / jsonpath / contains / response_time / header / schema / db / soft
    key: Optional[str] = None              # jsonpath 表达式 或 header key
    value: Optional[Any] = None            # 期望值
    max_ms: Optional[float] = None         # response_time 上限
    not_null: bool = False                 # 非空断言
    comment: Optional[str] = None          # 注释（软断言时说明）
    query: Optional[str] = None            # db 断言 SQL


@dataclass
class ApiCaseModel:
    """API 用例"""
    # 元信息
    case_id: str
    case_name: str
    module: str = ""
    tags: List[str] = field(default_factory=list)
    # 请求
    method: str = "GET"                    # GET / POST / PUT / DELETE / PATCH
    url: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    body: Optional[Any] = None             # dict（JSON 请求体） 或 str（form）
    files: Dict[str, str] = field(default_factory=dict)  # 上传文件路径
    # 响应处理
    extract: Dict[str, str] = field(default_factory=dict)  # {变量名: jsonpath}
    # 断言
    assertions: List[AssertionItem] = field(default_factory=list)
    # 依赖
    depends_on: Optional[str] = None       # 依赖的前置用例 case_id
    # 钩子
    pre_hook: Optional[str] = None
    post_hook: Optional[str] = None
    # 控制
    skip: bool = False
    retry: int = 0                         # 本用例单独重试次数


@dataclass
class TestResult:
    """用例执行结果"""
    case_id: str
    case_name: str
    passed: bool
    error_message: str = ""
    response_time_ms: float = 0.0
    status_code: int = 0
    response_body: Any = None
    extract_vars: Dict[str, Any] = field(default_factory=dict)
    screenshots: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转为字典，方便序列化"""
        import json
        return {
            "case_id": self.case_id,
            "case_name": self.case_name,
            "passed": self.passed,
            "error_message": self.error_message,
            "response_time_ms": self.response_time_ms,
            "status_code": self.status_code,
            "response_body": _safe_serialize(self.response_body),
            "extract_vars": _safe_serialize(self.extract_vars),
            "screenshots": self.screenshots,
        }


def _safe_serialize(value: Any) -> Any:
    """安全序列化：将不可 JSON 序列化的对象转为字符串"""
    import json as _json
    if value is None:
        return None
    try:
        _json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)
