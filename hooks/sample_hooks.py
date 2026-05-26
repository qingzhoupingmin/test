"""示例钩子函数 — 演示前置/后置钩子的典型用法

将本文件复制为项目专属钩子文件后在 conftest.py 中注册即可使用。
"""


def hook_before_case(case=None, variables=None, **kwargs):
    """用例执行前钩子 — 示例：注入通用请求头"""
    # 示例：从变量中读取 token 并注入到请求头
    # token = variables.get("auth_token", "")
    # if token and case:
    #     case.headers = case.headers or {}
    #     case.headers["Authorization"] = f"Bearer {token}"
    pass


def hook_after_case(case=None, response=None, extract_vars=None, **kwargs):
    """用例执行后钩子 — 示例：清理测试数据、提取额外变量"""
    pass