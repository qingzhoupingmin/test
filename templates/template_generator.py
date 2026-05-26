"""模板生成器 — 快速生成 Excel 测试用例模板文件"""
import os
from pathlib import Path
from typing import Optional


class TemplateGenerator:
    """生成标准 Excel 测试用例模板"""

    TEMPLATE_DIR = Path(__file__).parent

    @staticmethod
    def _ensure_openpyxl():
        try:
            import openpyxl
            return openpyxl
        except ImportError:
            raise ImportError("请安装 openpyxl: pip install openpyxl")

    @classmethod
    def generate_api_template(
        cls,
        output_path: Optional[str] = None,
    ) -> str:
        """生成 CRUD 型 API 用例模板 Excel"""
        openpyxl = cls._ensure_openpyxl()

        output_path = output_path or str(cls.TEMPLATE_DIR / "api_sample.xlsx")
        wb = openpyxl.Workbook()

        # Sheet 1: 用例列表
        ws = wb.active
        ws.title = "API用例"

        # 表头
        headers = [
            "case_id", "case_name", "module", "tags", "priority",
            "method", "url_path", "headers", "params", "payload", "payload_type",
            "assert_type", "assert_target", "assert_value",
            "extract_jsonpath", "extract_var",
            "pre_hook", "post_hook", "skip", "depends_on_case_id", "description"
        ]
        for col, h in enumerate(headers, 1):
            ws.cell(row=1, column=col, value=h)

        # 示例数据
        samples = [
            ["TC_LOGIN_001", "登录成功", "用户管理", "smoke,p0", "P0",
             "POST", "/api/v1/login", '{"Content-Type":"application/json"}', "",
             '{"username":"admin","password":"admin123"}', "json",
             "status_code", "", "200",
             "data.token", "auth_token",
             "", "", "否", "", "使用管理员账号登录获取Token"],

            ["TC_USER_001", "创建用户", "用户管理", "p0,regression", "P0",
             "POST", "/api/v1/users", "", "",
             '{"name":"测试用户{{random_str}}","email":"{{random_str}}@test.com"}', "json",
             "status_code", "", "201",
             "$.data.id", "new_user_id",
             "hooks.sample_hooks.hook_set_headers", "hooks.sample_hooks.hook_cleanup_test_data", "否", "TC_LOGIN_001", "依赖登录获取Token"],

            ["TC_USER_002", "查询用户详情", "用户管理", "p1", "P1",
             "GET", "/api/v1/users/{{new_user_id}}", "", "", "", "",
             "jsonpath_equals", "$.data.name", "测试用户{{random_str}}",
             "", "",
             "", "", "否", "TC_USER_001", "依赖创建用户"],

            ["TC_USER_003", "删除用户", "用户管理", "p1", "P1",
             "DELETE", "/api/v1/users/{{new_user_id}}", "", "", "", "",
             "status_code", "", "204",
             "", "",
             "", "", "否", "TC_USER_002", ""],
        ]
        for row_idx, sample in enumerate(samples, 2):
            for col_idx, val in enumerate(sample, 1):
                ws.cell(row=row_idx, column=col_idx, value=val)

        # Sheet 2: 使用说明
        ws2 = wb.create_sheet("使用说明")
        instructions = [
            ["字段", "说明", "可选值/示例"],
            ["case_id", "用例唯一ID", "TC_XX_001"],
            ["case_name", "用例名称", "登录成功"],
            ["module", "所属模块", "用户管理"],
            ["tags", "标签(逗号分隔)", "smoke,p0,regression"],
            ["priority", "优先级", "P0 / P1 / P2"],
            ["method", "请求方法", "GET/POST/PUT/DELETE/PATCH"],
            ["url_path", "接口路径", "/api/v1/login"],
            ["headers", "请求头(JSON)", '{"Content-Type":"application/json"}'],
            ["params", "URL参数(JSON)", '{"page":1,"size":10}'],
            ["payload", "请求体", '{"name":"test"}'],
            ["payload_type", "请求体类型", "json / form / formdata"],
            ["assert_type", "断言类型", "status_code / jsonpath_equals / jsonpath_contains / jsonpath_exists / response_contains / schema / db_check"],
            ["assert_target", "断言目标", "$.data.name"],
            ["assert_value", "期望值", "200或期望的具体值"],
            ["extract_jsonpath", "提取JSONPath", "$.data.token"],
            ["extract_var", "提取变量名", "auth_token"],
            ["pre_hook", "前置钩子", "hooks.sample_hooks.hook_login_api"],
            ["post_hook", "后置钩子", "hooks.sample_hooks.hook_cleanup_test_data"],
            ["skip", "是否跳过", "是/否"],
            ["depends_on_case_id", "依赖case_id", "TC_XX_001"],
            ["description", "用例描述", ""],
        ]
        for row_idx, row_data in enumerate(instructions, 1):
            for col_idx, val in enumerate(row_data, 1):
                ws2.cell(row=row_idx, column=col_idx, value=val)

        # 调整列宽
        for ws_obj in [ws, ws2]:
            for col in ws_obj.columns:
                max_length = max(len(str(cell.value or "")) for cell in col)
                ws_obj.column_dimensions[col[0].column_letter].width = min(max_length + 4, 50)

        wb.save(output_path)
        print(f"API 模板已生成: {output_path}")
        return output_path

    @classmethod
    def generate_ui_template(
        cls,
        output_path: Optional[str] = None,
    ) -> str:
        """生成 UI 自动化用例模板 Excel"""
        openpyxl = cls._ensure_openpyxl()

        output_path = output_path or str(cls.TEMPLATE_DIR / "ui_sample.xlsx")
        wb = openpyxl.Workbook()

        # Sheet 1: 用例列表
        ws = wb.active
        ws.title = "UI用例"

        headers = [
            "case_id", "case_name", "module", "tags", "priority",
            "case_type", "page_url",
            "steps",  # JSON 数组
            "assert_type", "assert_target", "assert_value",
            "pre_hook", "post_hook",
            "skip", "screenshot_on_fail", "wait_after_ms", "description"
        ]
        for col, h in enumerate(headers, 1):
            ws.cell(row=1, column=col, value=h)

        # 示例数据
        sample_steps = '[{"action":"navigate","value":"{{base_url}}/login"},{"action":"input","selector":"#username","value":"admin"},{"action":"input","selector":"#password","value":"admin123"},{"action":"click","selector":"button[type=submit]"},{"action":"wait","value":"2000"}]'
        samples = [
            ["TC_UI_LOGIN_001", "登录页面-正常登录", "登录模块", "smoke,p0", "P0",
             "ui", "{{base_url}}/login",
             sample_steps,
             "url_contains", "", "/dashboard",
             "hooks.sample_hooks.hook_wait_for_loading", "",
             "否", "是", "2000", "验证正常登录流程"],

            ["TC_UI_LOGIN_002", "登录页面-错误密码", "登录模块", "p1", "P1",
             "ui", "{{base_url}}/login",
             '[{"action":"input","selector":"#username","value":"admin"},{"action":"input","selector":"#password","value":"wrong"},{"action":"click","selector":"button[type=submit]"}]',
             "text_contains", ".error-msg", "用户名或密码错误",
             "", "",
             "否", "是", "1000", "验证错误密码提示"],
        ]
        for row_idx, sample in enumerate(samples, 2):
            for col_idx, val in enumerate(sample, 1):
                ws.cell(row=row_idx, column=col_idx, value=val)

        # Sheet 2: 使用说明
        ws2 = wb.create_sheet("使用说明")
        instructions = [
            ["字段", "说明", "可选值/示例"],
            ["case_id", "用例唯一ID", "TC_UI_XX_001"],
            ["case_name", "用例名称", ""],
            ["case_type", "用例类型", "ui"],
            ["page_url", "起始页面URL", "{{base_url}}/login"],
            ["steps", "步骤JSON数组", '参考下方步骤说明'],
            ["assert_type", "断言类型", "element_visible / element_not_visible / text_equals / text_contains / url_contains / page_title / element_count"],
            ["assert_target", "断言目标选择器", "#result"],
            ["assert_value", "期望值", ""],
            ["pre_hook", "前置钩子", ""],
            ["post_hook", "后置钩子", ""],
            ["skip", "跳过", "是/否"],
            ["screenshot_on_fail", "失败截图", "是/否"],
            ["wait_after_ms", "执行后等待(ms)", "2000"],
            ["", "", ""],
            ["步骤action可选值:", "", ""],
            ["navigate", "导航到URL", '{"action":"navigate","value":"url"}'],
            ["click", "点击元素", '{"action":"click","selector":"#btn"}'],
            ["input", "输入文本", '{"action":"input","selector":"#name","value":"text"}'],
            ["select", "下拉选择", '{"action":"select","selector":"#city","value":"北京"}'],
            ["hover", "鼠标悬停", '{"action":"hover","selector":"#menu"}'],
            ["double_click", "双击", '{"action":"double_click","selector":"#item"}'],
            ["right_click", "右键点击", '{"action":"right_click","selector":"#item"}'],
            ["scroll_to", "滚动到元素", '{"action":"scroll_to","selector":"#bottom"}'],
            ["switch_frame", "切换iframe", '{"action":"switch_frame","selector":"#frame"}'],
            ["switch_default", "回到默认frame", '{"action":"switch_default"}'],
            ["switch_window", "切换窗口", '{"action":"switch_window","value":"0"}'],
            ["wait", "等待ms", '{"action":"wait","value":"2000"}'],
            ["wait_element", "等待元素出现", '{"action":"wait_element","selector":"#load","value":"10"}'],
            ["execute_script", "执行JS", '{"action":"execute_script","value":"alert(1)"}'],
            ["upload_file", "上传文件", '{"action":"upload_file","selector":"#file","value":"/path/to/file"}'],
            ["press_key", "按键", '{"action":"press_key","value":"ENTER"}'],
            ["clear", "清空输入框", '{"action":"clear","selector":"#name"}'],
            ["", "", ""],
            ["选择器格式:", "", ""],
            ["#id", "ID选择器", "#username"],
            [".class", "类选择器", ".btn-primary"],
            ["//xpath", "XPath", "//button[text()='提交']"],
            ["css:.selector", "CSS选择器", "css:.container > div"],
            ["text:文本", "文本匹配", "text:提交"],
            ["[attribute=value]", "属性选择器", "[data-testid=submit]"],
        ]
        for row_idx, row_data in enumerate(instructions, 1):
            for col_idx, val in enumerate(row_data, 1):
                ws2.cell(row=row_idx, column=col_idx, value=val)

        # 调整列宽
        for ws_obj in [ws, ws2]:
            for col in ws_obj.columns:
                max_length = max(len(str(cell.value or "")) for cell in col)
                ws_obj.column_dimensions[col[0].column_letter].width = min(max_length + 4, 60)

        wb.save(output_path)
        print(f"UI 模板已生成: {output_path}")
        return output_path


def main():
    """生成所有模板"""
    print("=" * 50)
    print("测试框架模板生成器")
    print("=" * 50)
    TemplateGenerator.generate_api_template()
    TemplateGenerator.generate_ui_template()
    print("所有模板生成完成！")


if __name__ == "__main__":
    main()