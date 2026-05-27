"""框架分层异常体系"""


class FrameworkError(Exception):
    """框架根异常，所有自定义异常基类"""
    pass


# ── 配置层 ──

class ConfigError(FrameworkError):
    """配置加载/解析错误"""
    pass


class ConfigNotFoundError(ConfigError):
    """配置文件未找到"""
    pass


# ── 变量层 ──

class VariableError(FrameworkError):
    """变量相关错误"""
    pass


class VariableNotFoundError(VariableError):
    """变量未定义"""
    pass


# ── 用例定义层 ──

class CaseError(FrameworkError):
    """用例定义/解析错误"""
    pass


class CaseParseError(CaseError):
    """用例解析失败（Excel/Markdown/YAML 格式错误）"""
    pass


class CaseDependencyError(CaseError):
    """用例依赖解析失败（循环依赖、依赖不存在等）"""
    pass


# ── 执行层 ──

class ExecutionError(FrameworkError):
    """用例执行错误"""
    pass


class RequestError(ExecutionError):
    """HTTP 请求错误"""
    pass


class TimeoutError(ExecutionError):
    """请求超时"""
    pass


class AssertionError(ExecutionError):
    """断言失败"""
    pass


class HookExecutionError(ExecutionError):
    """钩子执行失败"""
    pass


# ── UI 层 ──

class UIError(FrameworkError):
    """UI 测试相关错误"""
    pass


class ElementNotFoundError(UIError):
    """UI 元素未找到"""
    pass


# ── 数据层 ──

class DataError(FrameworkError):
    """数据驱动/数据源相关错误"""
    pass


class DBConnectionError(DataError):
    """数据库连接失败"""
    pass


class DBQueryError(DataError):
    """数据库查询失败"""
    pass