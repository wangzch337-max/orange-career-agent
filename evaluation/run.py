"""python -m evaluation.run: offline only; no live switch exists."""

import argparse
from pathlib import Path

from evaluation.models import Capability, EvaluationLayer
from evaluation.report import write_reports
from evaluation.runner import EvaluationRunner, exit_code


def main(argv=None):
    parser = argparse.ArgumentParser(description="Orange offline synthetic Golden evaluation")
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--layer", choices=[item.value for item in EvaluationLayer])
    parser.add_argument("--capability", choices=[item.value for item in Capability])
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--strict-review", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = EvaluationRunner().run(scenario_ids=args.scenario,
            layer=EvaluationLayer(args.layer) if args.layer else None,
            capability=Capability(args.capability) if args.capability else None,
            tags=args.tag, fail_fast=args.fail_fast)
        paths = write_reports(report, args.output)
    except ValueError:
        print("Evaluation configuration invalid; no raw exception data displayed.")
        return 2
    summary = report.summary
    print(f"total={summary.total} PASS={summary.pass_count} FAIL={summary.fail} "
          f"EXPECTED_UNCERTAINTY={summary.expected_uncertainty} NEEDS_REVIEW={summary.needs_review}")
    print(f"network_attempts={report.run.network_attempt_count} private_access_attempts={report.run.private_access_attempt_count}")
    for path in paths:
        print(path)
    return exit_code(report, strict_review=args.strict_review)


if __name__ == "__main__":
    raise SystemExit(main())
