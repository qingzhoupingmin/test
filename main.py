"""测试框架主入口 — 提供 CLI 命令行方式运行测试"""
import argparse
import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))


def cmd_generate(args):
    """生成多格式测试用例模板"""
    from templates.template_generator import TemplateGenerator
    TemplateGenerator.generate_api_template(args.output, fmt=getattr(args, 'format', 'xlsx'))
    print("模板生成完成！")


def cmd_run(args):
    """运行测试"""
    # 设置环境变量
    if args.env:
        os.environ["TEST_ENV"] = args.env

    # 构建 pytest 参数
    pytest_args = []

    # 测试目标
    pytest_args.append("test_cases/test_api_executor.py")

    # 标记过滤
    if args.marker:
        pytest_args.extend(["-m", args.marker])

    # 报告
    if args.allure:
        pytest_args.extend(["--alluredir", "reports/allure-results"])

    # 详细输出
    if args.verbose:
        pytest_args.append("-v")

    # 并行
    if args.parallel:
        pytest_args.extend(["-n", str(args.parallel)])

    # 失败重跑
    if args.reruns:
        pytest_args.extend(["--reruns", str(args.reruns)])

    # 整合剩余透传参数
    pytest_args.extend(args.pytest_args)

    import pytest
    print(f"[测试框架] 启动 pytest: {' '.join(pytest_args)}")
    exit_code = pytest.main(pytest_args)
    sys.exit(exit_code)


def main():
    parser = argparse.ArgumentParser(
description="接口自动化测试框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 生成 API 模板（默认 xlsx）
  python main.py generate

  # 生成 YAML 模板
  python main.py generate --format yaml

  # 生成 CSV 模板到指定路径
  python main.py generate --format csv -o data/api/用例.csv

  # 运行 API 测试
  python main.py run

  # 运行冒烟测试带 Allure 报告
  python main.py run --marker smoke --allure

  # 运行测试带详细输出
  python main.py run --verbose
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # generate 子命令
    gen_parser = subparsers.add_parser("generate", help="生成多格式测试用例模板（xlsx/csv/json/yaml）")
    gen_parser.add_argument("--output", "-o", default=None, help="输出路径")
    gen_parser.add_argument("--format", "-f", default="xlsx", choices=["xlsx", "csv", "json", "yaml"],
                            help="输出格式（默认 xlsx）")
    gen_parser.set_defaults(func=cmd_generate)

    # run 子命令
    run_parser = subparsers.add_parser("run", help="运行测试")
    run_parser.add_argument("--env", choices=["dev", "test", "prod"], default=None, help="测试环境")
    run_parser.add_argument("--marker", "-m", default=None, help="pytest 标记过滤 (如 smoke / p0)")
    run_parser.add_argument("--allure", action="store_true", help="生成 Allure 报告")
    run_parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    run_parser.add_argument("--parallel", "-n", type=int, default=0, help="并行执行数 (如 4)")
    run_parser.add_argument("--reruns", type=int, default=0, help="失败重跑次数")
    run_parser.add_argument("pytest_args", nargs="*", help="传递给 pytest 的额外参数")
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()