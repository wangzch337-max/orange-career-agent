"""Safe structured and failures-first Markdown reports, never raw observations."""

import json
from pathlib import Path

from evaluation.models import EvaluationReport, EvaluationStatus
from evaluation.runner import OUTPUT_ROOT


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown_report(report: EvaluationReport) -> str:
    summary = report.summary
    lines = ["# Orange Golden Evaluation — 离线合成报告", "",
        "仅使用 FakeLLMProvider / FakeEmbeddingProvider；不是 live benchmark，也不输出质量分数。", "",
        f"Schema: `{report.schema_version}` · Run: `{report.run.run_id}` · Commit: `{report.run.git_commit}`", "",
        f"总数 {summary.total} · PASS {summary.pass_count} · FAIL {summary.fail} · "
        f"EXPECTED_UNCERTAINTY {summary.expected_uncertainty} · NEEDS_REVIEW {summary.needs_review}", "",
        "## FAIL / NEEDS_REVIEW（优先检查）", ""]
    findings = [item for scenario in report.scenarios for item in scenario.findings]
    if not findings:
        lines.append("无 FAIL / NEEDS_REVIEW finding。")
    for item in findings:
        lines.extend([f"### {item.failure_id}", "", f"{item.taxonomy.value} / {item.severity.value} / {item.source_component}", "",
            item.summary, "", f"Expected: `{_cell(json.dumps(item.expected, ensure_ascii=False))}`", "",
            f"Observed: `{_cell(item.observed)}`", "",
            f"Evidence refs: {', '.join(item.evidence_refs) or 'none'} · Memory refs: {', '.join(item.memory_refs) or 'none'}", ""])
    lines.extend(["", "## 全部场景与检查", ""])
    for scenario in report.scenarios:
        lines.extend([f"### {scenario.scenario_id} — {scenario.title}", "",
            f"{scenario.status.value} · {scenario.layer.value} · {scenario.capability.value}", "",
            "| Check | Kind | Result | Rule |", "|---|---|---|---|"])
        for check in scenario.checks:
            status = "NEEDS_REVIEW" if check.review_triggered else "PASS" if check.passed else "FAIL"
            lines.append(f"| {check.check_id} | {check.kind} | {status} | {_cell(check.summary)} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_reports(report: EvaluationReport, output: Path | None = None):
    directory = (output or OUTPUT_ROOT).resolve()
    if not directory.is_relative_to(OUTPUT_ROOT.resolve()):
        raise ValueError("Reports must remain under the ignored artifacts/evaluation directory")
    directory.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = directory / "report.json", directory / "report.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    return json_path, markdown_path
