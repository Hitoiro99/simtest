"""数值模拟测试平台的命令行入口。"""

import argparse
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

from case_management.cases import (
    discover_cases,
    discover_conditions,
    execution_config,
    load_case,
    load_condition,
)
from run_control.install import register_install, select_install
from run_control.jobs import prepare_job, run_job
from solvers.exceptions import SolverError


def positive(value):
    """将命令行参数转换为有限正数。"""
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("必须为正且有限")

    return result


def parser():
    """定义子命令及其参数。"""
    cli = argparse.ArgumentParser(prog="simtest",description="数值模拟自动测试与解析解比较",)
    cli.add_argument("--root",type=Path,default=Path(__file__).resolve().parent,)
    commands = cli.add_subparsers(dest="command", required=True)

    deploy = commands.add_parser("setup")
    deploy.add_argument("--solver", required=True)
    deploy.add_argument("--version", required=True)
    deploy.add_argument("--path", required=True)
    deploy.add_argument("--config")
    deploy.add_argument("--environment",choices=["existing", "module", "script"],default="existing", )
    deploy.add_argument("--environment-script")
    deploy.add_argument("--environment-module", action="append", default=[])
    deploy.add_argument("--force", action="store_true")

    listing = commands.add_parser("list")
    listing.add_argument("kind", choices=["cases", "solvers", "runs"])
    listing.add_argument("--config")
    listing.add_argument("--case", help="仅列出此案例的已归档作业（list runs）")

    validate = commands.add_parser("validate")
    validate.add_argument("case")
    validate.add_argument("--condition")
    validate.add_argument("--solver", default="OpenFOAM@latest")
    validate.add_argument("--config")

    run = commands.add_parser("run")
    run.add_argument("case")
    run.add_argument("--condition")
    run.add_argument("--all-conditions", action="store_true")
    run.add_argument("--solver", action="append")
    run.add_argument("--config")
    run.add_argument("--processes", type=int)
    run.add_argument("--backend", choices=["serial", "openmp", "cuda"])
    run.add_argument("--openmp-threads", type=int)
    run.add_argument("--timeout", type=positive, default=300)
    run.add_argument("--heartbeat-timeout", type=positive, default=120)
    run.add_argument("--prepare-only", action="store_true")
    run.add_argument("--keep-raw", action="store_true")

    reports = commands.add_parser("report")
    reports.add_argument("case")
    reports.add_argument("--job-id", action="append")

    return cli


def main(argv=None):
    """调度 CLI 命令，返回成功、作业失败或命令错误的退出码。"""
    args = parser().parse_args(argv)

    try:
        root = args.root.resolve()

        if args.command == "setup":
            result = register_install(root, args)

        elif args.command == "list":
            if args.kind == "cases":
                result = []
                for path in discover_cases(root):
                    case = load_case(path)
                    result.append({
                        "id": case["id"],
                        "conditions": discover_conditions(path),
                    })

            elif args.kind == "runs":
                from reporting.report import archived_runs

                result = archived_runs(root, args.case)

            else:
                from solvers.registry import discover

                result = {
                    name: sorted(versions)
                    for name, versions in discover().items()
                }

        elif args.command == "validate":
            from case_management.templates import choose

            path = Path(args.case)
            if path.is_dir():
                path = path.resolve()
            else:
                path = root / "cases" / args.case

            case = load_case(path)
            if args.condition:
                conditions = [args.condition]
            else:
                conditions = discover_conditions(path)
            if not conditions:
                raise SolverError("没有工况")

            _, _, info, adapter = select_install(root, args.solver, args.config)
            chain = choose(path, adapter)
            execution = execution_config(case.get("execution", {}))
            for condition in conditions:
                load_condition(path, case, condition)
                context = SimpleNamespace(
                    case_path=path,
                    case=case,
                    execution=execution,
                    info=info,
                )
                adapter.validate(context)

            result = {
                "valid": True,
                "case": case["id"],
                "conditions": conditions,
                "actual_version": info.version,
                "adapter": adapter.version,
                "template": chain[-1]["id"],
            }

        elif args.command == "run":
            if args.all_conditions and args.condition:
                raise SolverError("--condition 与 --all-conditions 互斥")

            conditions = discover_conditions(root / "cases" / args.case)
            if args.condition:
                conditions = [args.condition]
            if not conditions:
                raise SolverError("没有工况")
            if not args.condition and not args.all_conditions and len(conditions) > 1:
                raise SolverError("有多个工况时需指定 --condition 或 --all-conditions")

            selectors = args.solver
            if not selectors:
                selectors = ["OpenFOAM@latest"]

            results = []
            for condition in conditions:
                for selector in selectors:
                    context, adapter = prepare_job(
                        root, args.case, condition, selector, args,
                    )
                    item = run_job(
                        context, adapter, args.prepare_only, args.keep_raw,
                    )
                    results.append(item)
                    print(json.dumps(item, ensure_ascii=False), flush=True)

            if not args.prepare_only:
                from reporting.report import report

                job_ids = [item["job_id"] for item in results]
                report_result = report(root, args.case, job_ids)
                print(json.dumps(report_result, ensure_ascii=False), flush=True)

            for item in results:
                if item["status"] not in ("SUCCEEDED", "QUEUED"):
                    return 1
            return 0

        elif args.command == "report":
            from reporting.report import report

            result = report(root, args.case, args.job_id)

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    except (SolverError, OSError, ValueError) as exc:
        error = {
            "error": type(exc).__name__,
            "message": str(exc),
        }
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
