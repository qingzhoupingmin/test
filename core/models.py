"""数据模型定义 — API/UI 用例模型、断言项、步骤等"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AssertionItem:
    """单条断言"""
    type: str                              # status_code / jsonpath / contains / response_time / header / schema / db / soft / element_visible / text_equals / url_contains / page_title
    key: Optional[str] = None              # jsonpath 表达式 或 header key
    value: Optional[Any] = None            # 期望值
    max_ms: Optional[float] = None         # response_time 上限
    not_null: bool = False                 # 非空断言
    target: Optional[str] = None           # UI 选择器
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
class UiStep:
    """UI 操作步骤"""
    action: str                            # navigate / click / fill / wait / screenshot / ...
    selector: Optional[str] = None         # CSS / XPath 选择器
    value: Optional[str] = None            # 输入值 / URL / 等待毫秒数
    iframe: Optional[str] = None           # 所在 iframe 选择器


@dataclass
class UiCaseModel:
    """UI 用例"""
    # 元信息
    case_id: str
    case_name: str
    module: str = ""
    tags: List[str] = field(default_factory=list)
    # 页面
    page_url: str = ""
    # 步骤
    steps: List[UiStep] = field(default_factory=list)
    # 断言
    assertions: List[AssertionItem] = field(default_factory=list)
    # 控制
    wait_after_ms: int = 0                 # 步骤间等待
    screenshot_on_fail: bool = True
    skip: bool = False
    # 钩子
    pre_hook: Optional[str] = None
    post_hook: Optional[str] = None


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