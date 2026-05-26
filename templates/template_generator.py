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

        # 示例数据（使用通用占位符，实际使用时替换为真实接口信息）
        samples = [
            ["TC_EXAMPLE_001", "获取资源列表", "示例模块", "smoke,p0", "P0",
             "GET", "/api/v1/resources", "", '{"page":1,"size":10}', "", "",
             "status_code", "", "200",
             "$.data", "result_data",
             "", "", "否", "", "通用GET请求示例 — 查询资源列表并提取响应数据"],

            ["TC_EXAMPLE_002", "创建资源", "示例模块", "p0,regression", "P0",
             "POST", "/api/v1/resources", '{"Content-Type":"application/json"}', "",
             '{"name":"resource_{{random_str}}","desc":"auto_test"}', "json",
             "status_code", "", "201",
             "$.data.id", "new_resource_id",
             "hooks.sample_hooks.hook_before_case", "hooks.sample_hooks.hook_after_case", "否", "", "通用POST请求示例 — 创建资源并提取ID"],

            ["TC_EXAMPLE_003", "查询资源详情", "示例模块", "p1", "P1",
             "GET", "/api/v1/resources/{{new_resource_id}}", "", "", "", "",
             "jsonpath_equals", "$.data.name", "resource_{{random_str}}",
             "", "",
             "", "", "否", "TC_EXAMPLE_002", "通用GET请求示例 — 依赖创建的资源ID"],

            ["TC_EXAMPLE_004", "删除资源", "示例模块", "p1", "P1",
             "DELETE", "/api/v1/resources/{{new_resource_id}}", "", "", "", "",
             "status_code", "", "204",
             "", "",
             "", "", "否", "TC_EXAMPLE_003", "通用DELETE请求示例 — 清理测试资源"],
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


def main():
    """生成 API 测试用例模板"""
    print("=" * 50)
    print("API 测试框架模板生成器")
    print("=" * 50)
    TemplateGenerator.generate_api_template()
    print("模板生成完成！")


if __name__ == "__main__":
    main()
