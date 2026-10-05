"""Offline portfolio contracts; no live service, private input or prose snapshots."""

from __future__ import annotations

from functools import lru_cache
import ast
import hashlib
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

import pytest

from tests.v12_contract import approved_ui_test_source


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = "8ba7f1facca42dc03f29e92e2d5d6761dbef06e2"
# Resolved from the authenticated GitHub API before publication, not guessed.
# Pin the public destination so pytest stays offline and needs no credentials.
PUBLIC_GITHUB_OWNER = "wangzch337-max"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def safe_github_remote_url(url: str, expected_owner: str) -> bool:
    """Accept only credential-free, canonical URLs for this public repository."""
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", expected_owner):
        return False
    match = re.fullmatch(
        r"(?:https://github[.]com/|git@github[.]com:|ssh://git@github[.]com/)"
        r"([A-Za-z0-9-]+)/orange-career-agent(?:[.]git)?", url,
    )
    return bool(match and match.group(1).casefold() == expected_owner.casefold())


def remote_configuration_safe(remotes: dict[str, tuple[tuple[str, ...], tuple[str, ...]]], expected_owner: str) -> bool:
    """Publication permits no remotes, or one exact origin for fetch and push."""
    if not remotes:
        return True
    if set(remotes) != {"origin"}:
        return False
    fetch, push = remotes["origin"]
    return (len(fetch) == len(push) == 1
            and all(safe_github_remote_url(url, expected_owner) for url in (*fetch, *push)))


def publication_remote_is_safe(root: Path = ROOT, expected_owner: str = PUBLIC_GITHUB_OWNER) -> bool:
    """Read local Git metadata only; never emit a potentially unsafe remote URL."""
    def read(*args: str, optional: bool = False) -> tuple[str, ...]:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
        if optional and result.returncode == 1:
            return ()
        if result.returncode:
            raise ValueError("Invalid local remote configuration.")
        return tuple(result.stdout.decode().splitlines())

    try:
        names = read("remote")
        if not names:
            return not read("config", "--get-regexp", r"^remote[.]", optional=True)
        if names != ("origin",):
            return False
        raw_fetch = read("config", "--get-all", "remote.origin.url")
        raw_push = read("config", "--get-all", "remote.origin.pushurl", optional=True)
        if len(raw_fetch) != 1 or len(raw_push) > 1:
            return False
        if not all(safe_github_remote_url(url, expected_owner) for url in (*raw_fetch, *raw_push)):
            return False
        effective = {"origin": (read("remote", "get-url", "--all", "origin"),
                                read("remote", "get-url", "--push", "--all", "origin"))}
        return remote_configuration_safe(effective, expected_owner)
    except (OSError, ValueError, UnicodeError):
        return False


def public_paths() -> list[Path]:
    names = git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return sorted({ROOT / name for name in names.decode().split("\0") if name})


def markdown_body(source: str) -> str:
    return re.sub(r"(?ms)^```.*?^```\s*$", "", source)


def anchor_ids(source: str) -> set[str]:
    anchors = set(re.findall(r'<a\s+id="([^"]+)"', source))
    duplicates: dict[str, int] = {}
    for heading in re.findall(r"(?m)^#{1,6}\s+(.+)$", markdown_body(source)):
        slug = re.sub(r"[^\w\- ]", "", heading.casefold()).replace(" ", "-")
        count = duplicates.get(slug, 0)
        duplicates[slug] = count + 1
        anchors.add(f"{slug}-{count}" if count else slug)
    return anchors


def broken_links(path: Path, source: str) -> list[tuple[str, str]]:
    failures = []
    for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", markdown_body(source)):
        target = target.strip().strip("<>")
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue  # Offline: deliberately no external URL validation.
        destination = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
        if not destination.is_relative_to(ROOT) or not destination.exists():
            failures.append((path.relative_to(ROOT).as_posix(), target))
        elif parsed.fragment and destination.suffix == ".md":
            if unquote(parsed.fragment) not in anchor_ids(destination.read_text()):
                failures.append((path.relative_to(ROOT).as_posix(), target))
    return failures


# Patterns are broad candidate detection, not a promise of complete DLP.
# Returned diagnostics deliberately never include a matched value or source line.
SECRET_PATTERNS = {
    "provider_key": r"\bsk-[A-Za-z0-9_-]{20,}\b",
    "github_token": r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b",
    "aws_access_key": r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "credential_assignment": r'''(?i)(?:api_key|access_token|password|secret_key)\s*[=:]\s*["']([A-Za-z0-9_+/=-]{20,})["']''',
    "bearer_literal": r"(?i)Bearer\s+([A-Za-z0-9_+/=-]{20,})",
}


def secret_findings(name: str, source: str) -> list[tuple[str, int, str]]:
    findings = []
    for category, pattern in SECRET_PATTERNS.items():
        for match in re.finditer(pattern, source):
            value = match.group(1) if match.lastindex else match.group()
            if value.lower().startswith(("sk-fake", "sk-test", "fake-", "synthetic-")):
                continue
            findings.append((name, source.count("\n", 0, match.start()) + 1, category))
    return findings


def private_path(name: str) -> bool:
    parts = Path(name).parts
    return (
        (Path(name).name.startswith(".env") and Path(name).name != ".env.example")
        or name.startswith(("data/private/", "data/local/", "artifacts/", ".venv/"))
        or "golden_case" in parts
        or bool(re.search(r"\.(?:sqlite3?|db)(?:-|$)|\.(?:onnx|safetensors|pt)$", name))
    )


@lru_cache(maxsize=1)
def historical_blobs() -> tuple[tuple[str, str], ...]:
    blobs = []
    for row in git("rev-list", "--objects", "--all").decode().splitlines():
        object_id, _, name = row.partition(" ")
        if name and git("cat-file", "-t", object_id).strip() == b"blob":
            blobs.append((name, git("cat-file", "blob", object_id).decode("utf-8", errors="replace")))
    return tuple(blobs)


def assert_frozen_bytes(name: str, current: bytes, historical: bytes) -> None:
    """仅兼容获批准的 checkpoint／CSS／v1.1 UI 接线，其余字节完全冻结。"""
    from tests.profile_conversation_contract import pre_integration_bytes
    current = pre_integration_bytes(ROOT, name, current)
    if name in {"data/models.py", "memory/sqlite_store.py"}:
        from tests.profile_refinement_contract import assert_c4_shared_delta
        assert_c4_shared_delta(name, current, historical)
        return
    expected = historical
    if name == "tests/test_ui_polish.py":
        old_sha = b"5a6a1d14cb95e1a79ab11a1b16e4835d2bce5873"
        old_line = b'CHECKPOINT = "' + old_sha + b'"\n'
        new_line = b'CHECKPOINT = "53aa2abb7861e3593a6f4d6bb4fa75c8fda75497"\n'
        assert historical.count(old_sha) == 1, name
        assert historical.splitlines(keepends=True).count(old_line) == 1, name
        expected = historical.replace(old_line, new_line, 1)
    elif name == "ui/visual_system.py":
        # The authorized rendering repair changes only these exact CSS fragments.
        replacements = (
            (
                b'    .block-container {max-width:1200px; padding-top:1.7rem; padding-bottom:3rem;}\n',
                b'    [data-testid="stMainBlockContainer"] {max-width:1200px; padding-top:calc(3.75rem + var(--orange-space-md)); padding-bottom:3rem;}\n',
            ),
            (
                b'    [data-testid="stSidebar"] {background:var(--orange-surface); border-right:1px solid var(--orange-line);}\n',
                b'    [data-testid="stSidebar"] {background:var(--orange-surface); color:var(--orange-ink); border-right:1px solid var(--orange-line);}\n'
                b'    [data-testid="stSidebar"] h2 {color:var(--orange-ink);}\n'
                b'    [data-testid="stWidgetLabel"],\n'
                b'    [data-testid="stRadio"] [data-testid="stRadioOption"],\n'
                b'    [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"],\n'
                b'    [data-testid="stCheckbox"] [data-baseweb="checkbox"],\n'
                b'    [data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] {color:var(--orange-ink);}\n',
            ),
            (
                b'      .block-container {padding-left:1rem; padding-right:1rem;}\n',
                b'      [data-testid="stMainBlockContainer"] {padding-left:1rem; padding-right:1rem;}\n',
            ),
        )
        for before, after in replacements:
            assert expected.count(before) == 1, name
            expected = expected.replace(before, after, 1)
    elif name == "ui/app.py":
        source = historical.decode()
        sidebar = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "_sidebar")
        old = ast.get_source_segment(source, sidebar).encode()
        assert hashlib.sha256(old).hexdigest() == "c5d501d908f1841f4b9ea9bfd8111db934a3579e592ca37195bfbfa1ce028284"
        replacements = (
            (b"from ui.conversation import QuestionKind\n", b"from ui.conversation import QuestionKind\nfrom ui.app_bar import render_app_bar\nfrom ui.onboarding import render_onboarding\n"),
            (old, b"def _app_bar(controller: DemoController) -> None:\n    render_app_bar(controller, go=_go, reset=_reset_demo)"),
            (b'        initial_sidebar_state="expanded",\n', b'        initial_sidebar_state="collapsed",\n'),
            (b"    _sidebar(controller)\n", b"    _app_bar(controller)\n"),
            (b"    render_developer_trace(controller.safe_trace(), controller.diagnostics_snapshot())\n", b"    render_developer_trace(controller.safe_trace(), controller.diagnostics_snapshot())\n    render_onboarding()\n"),
        )
        for before, after in replacements:
            assert expected.count(before) == 1, name
            expected = expected.replace(before, after, 1)
    from tests.v12_contract import assert_v12_delta
    assert_v12_delta(name, current, expected)


def test_frozen_compatibility_rejects_all_unapproved_differences():
    name = "tests/test_ui_polish.py"
    old_sha = b"5a6a1d14cb95e1a79ab11a1b16e4835d2bce5873"
    new_sha = b"53aa2abb7861e3593a6f4d6bb4fa75c8fda75497"
    old_line = b'CHECKPOINT = "' + old_sha + b'"\n'
    new_line = b'CHECKPOINT = "' + new_sha + b'"\n'
    historical = b"# frozen header\n" + old_line + b"assert True\n"
    approved = b"# frozen header\n" + new_line + b"assert True\n"
    assert_frozen_bytes(name, approved, historical)
    assert_frozen_bytes("tests/unrelated.py", historical, historical)
    invalid_cases = (
        ("tests/unrelated.py", approved, historical),
        ("./tests/test_ui_polish.py", approved, historical),
        (name, approved, b"# old SHA absent\n"),
        (name, approved, historical + old_line),
        (name, approved, historical + b"# " + old_sha + b"\n"),
        (name, approved, b"# " + old_line),
        (name, approved, historical.replace(old_sha, b"0" * 40, 1)),
        (name, approved.replace(new_sha, b"0" * 40, 1), historical),
        (name, historical, historical),
        (name, approved + b"# extra byte difference\n", historical),
        ("tests/unrelated.py", historical + b"\n", historical),
    )
    for path, current, original in invalid_cases:
        with pytest.raises(AssertionError):
            assert_frozen_bytes(path, current, original)


def test_ui_rendering_repair_keeps_every_other_byte_frozen():
    name = "ui/visual_system.py"
    historical = git("show", f"{CHECKPOINT}:{name}")
    current = (ROOT / name).read_bytes()
    assert_frozen_bytes(name, current, historical)
    for path, modified, original in (
        (name, current + b"\n", historical),
        (name, current.replace(b"import streamlit as st", b"import streamlit as other", 1), historical),
        (name, current, historical + b"    .block-container {max-width:1200px; padding-top:1.7rem; padding-bottom:3rem;}\n"),
        (name, current, current),
        ("ui/components.py", current, historical),
    ):
        with pytest.raises(AssertionError):
            assert_frozen_bytes(path, modified, original)


def test_phase8c_checkpoint_and_original_tests_preserved():
    assert git("show", "-s", "--format=%s", CHECKPOINT).decode().strip() == "feat: polish orange demo experience"
    assert git("merge-base", "--is-ancestor", CHECKPOINT, "HEAD") == b""
    for name in git("ls-tree", "-r", "--name-only", CHECKPOINT, "tests").decode().splitlines():
        assert_frozen_bytes(name, (ROOT / name).read_bytes(), git("show", f"{CHECKPOINT}:{name}"))


def test_all_existing_runtime_prompts_fixtures_and_dependencies_unchanged():
    # Markdown documentation may change, except versioned prompts which are frozen.
    for name in git("ls-tree", "-r", "--name-only", CHECKPOINT).decode().splitlines():
        if Path(name).suffix == ".md" and not name.startswith("config/prompts/"):
            continue
        assert_frozen_bytes(name, (ROOT / name).read_bytes(), git("show", f"{CHECKPOINT}:{name}"))


@pytest.mark.parametrize("anchor", ["product-experience", "demo", "architecture", "evaluation", "run-locally", "documentation"])
def test_product_entry_navigation_has_resolved_sections(anchor):
    source = (ROOT / "README.md").read_text()
    assert source.startswith("# 🍊 Orange\n")
    assert anchor in anchor_ids(source)
    intro = source.split("##", 1)[0]
    assert "Career Discovery" in intro and "先理解自己" in intro
    assert "Phase" not in intro


def test_readme_capability_and_quality_claims_are_bounded():
    source = (ROOT / "README.md").read_text()
    for pattern in (r"\b\d+(?:\.\d+)?%", r"git clone\s", r"!\[.*(?:CI|coverage).+?\]", r"(?i)accuracy\s*[:=]\s*\d"):
        assert not re.search(pattern, source)
    assert "Public Synthetic Demo" in source
    assert "FakeLLMProvider" in source and "FakeEmbeddingProvider" in source
    assert "不是香港城市大学官方产品" in source
    assert "不做总体适配分数或岗位排名" in source
    assert "尚未实现认证" in source and "未开始" in source
    assert "不消费 retrieved Memory" in source
    uncertainty = source.split("`EXPECTED_UNCERTAINTY`", 1)[1].split("\n\n", 1)[0]
    assert "成功状态" in uncertainty and "证据不足" in uncertainty


def test_default_run_path_does_not_require_live_credentials_or_model():
    source = (ROOT / "README.md").read_text()
    commands = re.findall(r"```bash\n(.*?)\n```", source, re.S)
    assert len(commands) == 2
    assert "python3.11 -m venv .venv" in commands[0]
    assert "pip install -r requirements.txt" in commands[0]
    assert "streamlit run ui/app.py" in commands[0]
    assert "pytest -q" in commands[1] and "-m evaluation.run" in commands[1]
    assert not any("--live" in command or "API_KEY=" in command for command in commands)
    assert "3.11.9" in source and "Apple Silicon" in source


def diagrams() -> list[str]:
    return re.findall(r"```mermaid\n(.*?)\n```", (ROOT / "README.md").read_text(), re.S)


def nodes_and_edges(source: str) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Structural smoke for this bounded flowchart subset, not a Mermaid renderer."""
    assert source.splitlines()[0] in ("flowchart LR", "flowchart TB")
    nodes = {key: square or diamond for key, square, diamond in re.findall(r'\b([A-Z][A-Z0-9]*)\s*(?:\["([^"]+)"\]|\{"([^"]+)"\})', source)}
    edges = []
    for line in source.splitlines()[1:]:
        stripped = re.sub(r'\["[^"]+"\]|\{"[^"]+"\}', "", line).strip()
        assert line.count('"') % 2 == 0
        assert line.count("[") == line.count("]") and line.count("{") == line.count("}")
        match = re.fullmatch(r'([A-Z][A-Z0-9]*)\s*(?:-->|-\.->)\s*(?:\|"[^"]+"\|\s*)?([A-Z][A-Z0-9]*)', stripped)
        if match:
            edges.append(match.groups())
        else:
            assert stripped in nodes, "Unsupported diagram statement"
    assert all(left in nodes and right in nodes for left, right in edges)
    return nodes, edges


def reachable(start: str, edges: list[tuple[str, str]], blocked: set[str] | None = None) -> set[str]:
    seen = set(blocked or ())
    frontier = [start]
    while frontier:
        node = frontier.pop()
        if node in seen:
            continue
        seen.add(node)
        frontier.extend(right for left, right in edges if left == node)
    return seen - set(blocked or ())


def test_three_mermaid_diagrams_structural_smoke_and_product_confirmation_gate():
    charts = diagrams()
    assert len(charts) == 3
    for chart in charts:
        nodes_and_edges(chart)
    nodes, edges = nodes_and_edges(charts[0])
    assert "CONFIRM Gate" in nodes["H"]
    assert "M" in reachable("U", edges)
    assert "M" not in reachable("U", edges, blocked={"H"})
    assert "R" not in reachable("U", edges, blocked={"H"})


def test_agent_memory_edges_do_not_feed_job_or_match_generation():
    nodes, edges = nodes_and_edges(diagrams()[1])
    assert {nodes[node] for node in ("S", "J", "M")} == {"Self-Discovery Agent", "Job Intelligence Agent", "Match & Insight Agent"}
    assert "Orchestrator Agent" in nodes["O"] and "LangGraph" in nodes["O"]
    assert "Report Builder" in nodes["R"] and "Agent" not in nodes["R"]
    assert {target for origin, target in edges if origin == "P"} == {"PR", "RC"}
    assert "J" not in reachable("MEM", edges)
    # A future confirmed revision can influence Match; retrieved context cannot.
    assert "M" not in reachable("MEM", edges, blocked={"PA"})


def test_memory_diagram_distinguishes_authority_index_rrf_and_policy_order():
    nodes, edges = nodes_and_edges(diagrams()[2])
    assert "authoritative" in nodes["C"]
    assert "MemoryRecord only" in nodes["ACT"]
    assert "Derived" in nodes["D"] and "rebuildable" in nodes["D"]
    assert "RRF k=60" in nodes["RRF"]
    for edge in (("POL", "Q"), ("S", "V"), ("C", "V"), ("V", "RRF"), ("RRF", "B"), ("POL", "B")):
        assert edge in edges
    assert {target for origin, target in edges if origin == "B"} == {"PR", "RC"}


def test_all_public_markdown_relative_links_and_anchors_exist():
    failures = []
    for path in public_paths():
        if path.suffix == ".md":
            failures.extend(broken_links(path, path.read_text()))
    assert failures == []


def test_link_checker_detects_missing_file_anchor_and_image_without_fetching():
    source = "[missing](nonexistent.md) [anchor](#missing) ![asset](missing.png) [external](https://example.invalid/)"
    assert len(broken_links(ROOT / "README.md", source)) == 3


def test_markdown_fences_and_heading_hierarchy_and_unique_current_sections():
    for name in ("README.md", "PRODUCT_SPEC.md", "ARCHITECTURE.md", "DATA_CONTRACTS.md", "docs/SCREENSHOT_PLAN.md", "docs/PUBLIC_RELEASE_CHECKLIST.md", "docs/PORTFOLIO_ACCEPTANCE.md"):
        source = (ROOT / name).read_text()
        assert len(re.findall(r"(?m)^```", source)) % 2 == 0, name
        headings = re.findall(r"(?m)^(#{1,6})\s+(.+)$", markdown_body(source))
        assert headings[0][0] == "#", name
        assert len([h for h, _ in headings if h == "#"]) == 1, name
        assert len({title for _, title in headings}) == len(headings), name
        assert all(len(after[0]) <= len(before[0]) + 1 for before, after in zip(headings, headings[1:])), name


def test_documentation_index_and_real_project_structure():
    source = (ROOT / "README.md").read_text()
    for name in ("PRODUCT_SPEC.md", "ARCHITECTURE.md", "DATA_CONTRACTS.md", "IMPLEMENTATION_PLAN.md", "LEARNING_PLAN.md", "docs/DECISIONS.md", "memory/README.md", "evaluation/README.md", "observability/README.md", "docs/PRODUCT_UX_ACCEPTANCE.md"):
        assert f"]({name})" in source and (ROOT / name).is_file()
    for name in ("agents", "providers", "workflows", "memory", "evaluation", "observability", "ui", "data/fixtures", "docs", "tests"):
        assert (ROOT / name).is_dir()
    assert "Project Structure" in source and "Phase 9A" in source and "Phase 9B" in source


def test_screenshot_plan_has_six_targets_and_no_fabricated_image_assets():
    plan = (ROOT / "docs/SCREENSHOT_PLAN.md").read_text()
    rows = [line for line in plan.splitlines() if line.startswith("| ") and ".png`" in line]
    assert len(rows) == 6 and all(len(row.split("|")) == 8 for row in rows)
    assert (ROOT / "docs/assets/README.md").is_file()
    assert not re.search(r"!\[[^\]]*\]\(", (ROOT / "README.md").read_text())
    assert not list((ROOT / "docs/assets").glob("*.png"))


def test_checklists_cover_release_decisions_and_portfolio_not_numeric_scoring():
    release = (ROOT / "docs/PUBLIC_RELEASE_CHECKLIST.md").read_text()
    for category in ("LICENSE", "author", "Screenshot", "remote", "visibility", "push", "pytest", "Golden", "history", "artifact"):
        assert category.casefold() in release.casefold()
    for line in release.splitlines()[4:]:
        if line.startswith("| ") and not line.startswith("| 项目"):
            assert line.split("|")[2].strip() in {"PASS", "BLOCKED", "USER DECISION REQUIRED"}
    portfolio = (ROOT / "docs/PORTFOLIO_ACCEPTANCE.md").read_text()
    rows = [line for line in portfolio.splitlines() if line.startswith("| ")]
    assert len(rows) == 11  # Header plus ten dimensions, not a target test count.
    assert not re.search(r"\d+%", portfolio)


@pytest.mark.parametrize("name", [".env.local", ".venv/probe", "data/private/golden_case/confirmed_profile.json", "data/private/memory/orange_memory.sqlite3", "data/local/orange_vectors.sqlite3", "data/local/models/probe.onnx", "artifacts/evaluation/report.json", "artifacts/diagnostics/probe.json"])
def test_private_config_databases_cache_and_artifacts_stay_ignored_untracked(name):
    assert subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT, check=False).returncode == 0
    assert not git("ls-files", "--", name)


def test_current_public_file_inventory_has_no_private_runtime_or_deployment_files():
    names = [path.relative_to(ROOT).as_posix() for path in public_paths()]
    assert not [name for name in names if private_path(name)]
    assert not [name for name in names if name.startswith(".github/") or Path(name).name in {"Dockerfile", "docker-compose.yml", "vercel.json", "render.yaml"}]


def test_current_secret_candidates_redacted_and_empty():
    findings = []
    for path in public_paths():
        if path.is_file():
            findings.extend(secret_findings(path.relative_to(ROOT).as_posix(), path.read_bytes().decode("utf-8", errors="replace")))
    assert findings == []


def test_secret_scanner_redacts_real_shaped_candidates_but_allows_explicit_fake():
    candidate = "sk-" + "A1b2C3d4" * 4
    diagnostic = secret_findings("sample.txt", "first\n" + candidate)
    assert diagnostic == [("sample.txt", 2, "provider_key")]
    assert candidate not in repr(diagnostic)
    assert secret_findings("sample.txt", "sk-fake-" + "x" * 30) == []


def test_public_docs_production_and_history_no_developer_absolute_paths():
    # Preserve the original generic rejection-test literal, not a developer path.
    pattern = r"/Users/[^\s`\"']+|/home/[^\s`\"']+|C:\\Users\\[^\s`\"']+"
    findings = []
    for name, source in historical_blobs():
        if not name.startswith("tests/") and re.search(pattern, source):
            findings.append(name)
    for path in public_paths():
        name = path.relative_to(ROOT).as_posix()
        if not name.startswith("tests/") and re.search(pattern, path.read_bytes().decode("utf-8", errors="replace")):
            findings.append(name)
    assert findings == []


def test_full_reachable_git_history_private_paths_and_secret_values_absent():
    # Inspect every tree as well as deduplicated blobs (renamed paths included).
    path_findings = []
    for commit in git("rev-list", "--all").decode().splitlines():
        path_findings.extend(name for name in git("ls-tree", "-r", "--name-only", commit).decode().splitlines() if private_path(name))
    assert path_findings == []
    findings = [finding for name, source in historical_blobs() for finding in secret_findings(name, source)]
    assert findings == []
    assert "CLEAN FOR PUBLIC-RELEASE REVIEW" in (ROOT / "docs/PUBLIC_READINESS_AUDIT.md").read_text()


def test_public_personal_identifier_patterns_current_and_history():
    patterns = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "student_id": r'''(?i)(?:student[_ -]?id|学号)\s*[=:：]\s*["']?[0-9]{6,12}''',
        "phone": r"(?<![\w.])\+?86[- ]?1[3-9][0-9]{9}(?!\w)",
    }
    findings = []
    current = [(p.relative_to(ROOT).as_posix(), p.read_bytes().decode("utf-8", errors="replace")) for p in public_paths() if p.is_file()]
    for name, source in (*historical_blobs(), *current):
        for category, pattern in patterns.items():
            for match in re.finditer(pattern, source):
                if category == "email" and match.group().endswith("@example.invalid"):
                    continue
                findings.append((name, source.count("\n", 0, match.start()) + 1, category))
    assert findings == []


def test_user_approved_standard_mit_license_and_third_party_distinction():
    expected = '''MIT License

Copyright (c) 2026 王梓丞

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''
    assert (ROOT / "LICENSE").read_text() == expected
    notes = (ROOT / "docs/THIRD_PARTY_NOTES.md").read_text()
    assert "Apache-2.0" in notes and "MiniLM-L12-v2" in notes
    assert "不重新许可" in notes and "原许可证" in notes
    readme = (ROOT / "README.md").read_text()
    assert "[MIT License](LICENSE)" in readme and "不重新许可第三方依赖" in readme
    if not publication_remote_is_safe():
        pytest.fail("Unexpected publication remote configuration (URLs withheld).", pytrace=False)


def test_diff_whitespace_clean():
    assert git("diff", "--check") == b""


OBSERVABILITY_TEST = "tests/test_observability_integration.py"
OWNER = "synthetic-owner"
HTTPS_URL = f"https://github.com/{OWNER}/orange-career-agent.git"
SSH_PREFIX = "git@" + "github.com:"


def historical_observability_source():
    return git("show", f"{CHECKPOINT}:{OBSERVABILITY_TEST}")


def test_exact_ancestry_repair_preserves_entire_frozen_observability_test():
    historical = historical_observability_source()
    current = (ROOT / OBSERVABILITY_TEST).read_bytes()
    assert_frozen_bytes(OBSERVABILITY_TEST, current, historical)
    assert b'"merge-base", "--is-ancestor", checkpoint, "HEAD"' in current
    assert b'"3fb50b47594bde069f2d31585c06657e764205b4"' in current


@pytest.mark.parametrize("mutation", [
    lambda source: source.replace(b"3fb50b47594bde069f2d31585c06657e764205b4", b"0" * 40),
    lambda source: source.replace(
        b'    subprocess.check_call(["git", "merge-base", "--is-ancestor", checkpoint, "HEAD"], cwd=ROOT)\n', b""),
    lambda source: source.replace(b"    assert message.strip() ==", b"    assert message =="),
    lambda source: source.replace(b"        assert dependency not in requirements\n", b""),
    lambda source: source.replace(b'        assert "import httpx" not in source and "import requests" not in source\n', b""),
    lambda source: source + b"# Unapproved future change\n",
])
def test_frozen_observability_rejects_every_unapproved_mutation(mutation):
    with pytest.raises(AssertionError):
        assert_frozen_bytes(OBSERVABILITY_TEST, mutation((ROOT / OBSERVABILITY_TEST).read_bytes()),
                            historical_observability_source())


def test_old_window_check_and_other_filename_are_not_allowed_repairs():
    historical = historical_observability_source()
    old_current = historical.replace(b"from streamlit.testing.v1 import AppTest\n",
                                     b"from streamlit.testing.v1 import AppTest\nfrom tests.ui_legacy import legacy_app\n")
    with pytest.raises(AssertionError):
        assert_frozen_bytes(OBSERVABILITY_TEST, old_current, historical)
    with pytest.raises(AssertionError):
        assert_frozen_bytes("tests/unrelated.py", (ROOT / OBSERVABILITY_TEST).read_bytes(), historical)


@pytest.mark.parametrize("source", [b"# missing historical check\n", historical_observability_source() * 2])
def test_ancestry_compatibility_rejects_missing_or_duplicate_historical_check(source):
    with pytest.raises(AssertionError):
        approved_ui_test_source(OBSERVABILITY_TEST, source.decode())


@pytest.mark.parametrize("url", [
    HTTPS_URL, HTTPS_URL.removesuffix(".git"),
    SSH_PREFIX + f"{OWNER}/orange-career-agent.git",
    SSH_PREFIX + f"{OWNER}/orange-career-agent",
    "ssh://git@" + f"github.com/{OWNER}/orange-career-agent.git",
    HTTPS_URL.replace(OWNER, OWNER.upper()),
])
def test_only_canonical_safe_https_and_ssh_destinations_pass(url):
    assert safe_github_remote_url(url, OWNER)
    assert remote_configuration_safe({"origin": ((url,), (url,))}, OWNER)


@pytest.mark.parametrize("url", [
    f"https://example.invalid/{OWNER}/orange-career-agent.git",
    HTTPS_URL.replace("orange-career-agent", "another-repository"),
    HTTPS_URL.replace(OWNER, "other-owner"),
    HTTPS_URL.replace("https://", "https://synthetic-token@"),
    HTTPS_URL.replace("https://", "https://synthetic-user:synthetic-password@"),
    "http://" + HTTPS_URL.removeprefix("https://"),
    "https://github.com.evil.invalid/" + f"{OWNER}/orange-career-agent.git",
    HTTPS_URL + "?token=synthetic-token", HTTPS_URL + "#fragment", HTTPS_URL + "/extra",
    " " + HTTPS_URL, HTTPS_URL + "\n", HTTPS_URL.replace("github.com", "github.com:443"),
    HTTPS_URL.replace("/orange", "/../orange"), "../orange-career-agent.git",
    "", SSH_PREFIX.replace("git@", "synthetic-token@") + f"{OWNER}/orange-career-agent.git",
])
def test_unsafe_credential_malformed_host_owner_and_repository_urls_fail(url):
    assert not safe_github_remote_url(url, OWNER)
    assert not remote_configuration_safe({"origin": ((url,), (url,))}, OWNER)


@pytest.mark.parametrize("remotes", [
    {"origin": ((HTTPS_URL,), (HTTPS_URL,)), "backup": ((HTTPS_URL,), (HTTPS_URL,))},
    {"upstream": ((HTTPS_URL,), (HTTPS_URL,))},
    {"origin": ((), (HTTPS_URL,))}, {"origin": ((HTTPS_URL,), ())},
    {"origin": ((HTTPS_URL, HTTPS_URL), (HTTPS_URL,))},
    {"origin": ((HTTPS_URL,), (HTTPS_URL, HTTPS_URL))},
    {"origin": ((HTTPS_URL,), (HTTPS_URL.replace(OWNER, "other-owner"),))},
])
def test_second_remote_missing_urls_multiple_urls_and_competing_push_fail(remotes):
    assert not remote_configuration_safe(remotes, OWNER)


def test_prepublication_accepts_zero_remotes():
    assert remote_configuration_safe({}, OWNER)


@pytest.fixture
def local_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    return tmp_path


def configure(root: Path, *args: str):
    subprocess.run(["git", "config", "--local", *args], cwd=root, check=True, capture_output=True)


def test_actual_local_remote_lifecycle_is_offline_and_credential_independent(local_repo, monkeypatch):
    original = subprocess.run
    calls = []

    def local_git_only(args, **kwargs):
        assert args[0] == "git" and args[1] in {"remote", "config"}
        assert kwargs["cwd"] == local_repo
        calls.append(tuple(args))
        return original(args, **kwargs)

    configure(local_repo, "remote.origin.url", HTTPS_URL)
    monkeypatch.setattr(subprocess, "run", local_git_only)
    assert publication_remote_is_safe(local_repo, OWNER)
    assert calls  # No gh, auth, credential access, fetch, push or network command.


def test_actual_repository_pre_and_post_publication_states(local_repo):
    assert publication_remote_is_safe(local_repo, OWNER)
    configure(local_repo, "remote.origin.url", HTTPS_URL)
    assert publication_remote_is_safe(local_repo, OWNER)
    configure(local_repo, "remote.origin.pushurl", SSH_PREFIX + f"{OWNER}/orange-career-agent.git")
    assert publication_remote_is_safe(local_repo, OWNER)
    configure(local_repo, "remote.backup.url", HTTPS_URL)
    assert not publication_remote_is_safe(local_repo, OWNER)


@pytest.mark.parametrize("key,value", [
    ("remote.origin.url", HTTPS_URL.replace("https://", "https://synthetic-token@")),
    ("remote.origin.url", HTTPS_URL.replace("orange-career-agent", "wrong-repo")),
    ("remote.origin.url", "https://example.invalid/other.git"),
    ("remote.origin.pushurl", HTTPS_URL.replace(OWNER, "other-owner")),
    ("remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"),
])
def test_actual_repository_rejects_bad_raw_remote_configuration(local_repo, key, value):
    if key != "remote.origin.fetch":
        configure(local_repo, "remote.origin.url", HTTPS_URL)
    configure(local_repo, key, value)
    assert not publication_remote_is_safe(local_repo, OWNER)


def test_git_url_rewrites_cannot_bypass_raw_or_effective_destination_check(local_repo):
    unsafe = "https://example.invalid/synthetic.git"
    configure(local_repo, "remote.origin.url", unsafe)
    configure(local_repo, f"url.{HTTPS_URL}.insteadOf", unsafe)
    assert not publication_remote_is_safe(local_repo, OWNER)
    configure(local_repo, "remote.origin.url", HTTPS_URL)
    configure(local_repo, f"url.{unsafe}.pushInsteadOf", HTTPS_URL)
    assert not publication_remote_is_safe(local_repo, OWNER)
