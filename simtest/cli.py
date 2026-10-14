import argparse
import json
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from solvers.exceptions import SolverError
from .cases import discover_cases, discover_conditions, load_case, load_condition
from .io import atomic_json
from .runner import deployment, prepare_context, run_job, setup


def positive(value):
    result=float(value)
    if not math.isfinite(result) or result<=0: raise argparse.ArgumentTypeError("必须为正且有限")
    return result


def parser():
    main = argparse.ArgumentParser(prog="simtest",description="数值模拟自动测试与解析解比较")
    main.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    commands=main.add_subparsers(dest="command",required=True)
    deploy=commands.add_parser("setup")
    deploy.add_argument("--solver",required=True); deploy.add_argument("--version",required=True)
    deploy.add_argument("--path",required=True); deploy.add_argument("--config")
    deploy.add_argument("--environment",choices=["existing","module","script"],default="existing")
    deploy.add_argument("--environment-script"); deploy.add_argument("--environment-module",action="append",default=[])
    deploy.add_argument("--force",action="store_true")
    listing=commands.add_parser("list"); listing.add_argument("kind",choices=["cases","solvers","runs"]); listing.add_argument("--config")
    listing.add_argument("--case", help="仅列出此案例的已归档作业（list runs）")
    validate=commands.add_parser("validate"); validate.add_argument("case"); validate.add_argument("--condition"); validate.add_argument("--solver",default="OpenFOAM@latest"); validate.add_argument("--config")
    run=commands.add_parser("run"); run.add_argument("case")
    run.add_argument("--condition"); run.add_argument("--all-conditions",action="store_true")
    run.add_argument("--solver",action="append"); run.add_argument("--config")
    run.add_argument("--processes",type=int); run.add_argument("--backend",choices=["serial","openmp","cuda"]); run.add_argument("--openmp-threads",type=int)
    run.add_argument("--timeout",type=positive,default=300); run.add_argument("--heartbeat-timeout",type=positive,default=120)
    run.add_argument("--prepare-only",action="store_true"); run.add_argument("--keep-raw",action="store_true")
    reports=commands.add_parser("report"); reports.add_argument("case"); reports.add_argument("--job-id",action="append")
    return main


def main(argv=None):
    args=parser().parse_args(argv); root=args.root.resolve()
    try:
        if args.command=="setup": result=setup(root,args)
        elif args.command=="list":
            if args.kind=="cases": result=[{"id":load_case(path)["id"],"conditions":discover_conditions(path)} for path in discover_cases(root)]
            elif args.kind=="runs":
                from .report import archived_runs
                result=archived_runs(root,args.case)
            else:
                from solvers.registry import discover
                result={name:sorted(versions) for name,versions in discover().items()}
        elif args.command=="validate":
            path=Path(args.case)
            path=path.resolve() if path.is_dir() else root/"cases"/args.case
            case=load_case(path); conditions=[args.condition] if args.condition else discover_conditions(path)
            if not conditions: raise SolverError("没有工况")
            installation,environment,info,adapter=deployment(root,args.solver,args.config)
            from .templates import choose
            chain=choose(path,adapter)
            for condition in conditions:
                load_condition(path,case,condition)
                adapter.validate(SimpleNamespace(case_path=path,execution=case["execution"],info=info))
            result={"valid":True,"case":case["id"],"conditions":conditions,"actual_version":info.version,"adapter":adapter.version,"template":chain[-1]["id"]}
        elif args.command=="run":
            if args.all_conditions and args.condition: raise SolverError("--condition 与 --all-conditions 互斥")
            conditions=discover_conditions(root/"cases"/args.case)
            if args.condition: conditions=[args.condition]
            elif not args.all_conditions and len(conditions)!=1: raise SolverError("有多个工况时需指定 --condition 或 --all-conditions")
            if not conditions: raise SolverError("没有工况")
            result=[]
            for condition in conditions:
                for selector in args.solver or ["OpenFOAM@latest"]:
                    context,adapter=prepare_context(root,args.case,condition,selector,args)
                    item=run_job(context,adapter,args.prepare_only,args.keep_raw); result.append(item)
                    print(json.dumps(item,ensure_ascii=False),flush=True)
            if not args.prepare_only:
                from .report import report
                print(json.dumps(report(root,args.case,[item["job_id"] for item in result]),ensure_ascii=False),flush=True)
            return 0 if all(r["status"] in ("SUCCEEDED","QUEUED") for r in result) else 1
        elif args.command=="report":
            from .report import report
            result=report(root,args.case,args.job_id)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (SolverError,OSError,ValueError) as exc:
        print(json.dumps({"error":type(exc).__name__,"message":str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=="__main__": raise SystemExit(main())
