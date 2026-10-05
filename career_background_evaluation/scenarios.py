"""Small public synthetic careers; no personal data or fixture files on disk."""

from dataclasses import dataclass
from io import BytesIO

from docx import Document


@dataclass(frozen=True)
class Fact:
    category: str
    label: str
    organization: str = "Public Synthetic Organization"
    time_range: str = "2016 - 2024"
    responsibility: str = "Documented team activities and coordinated colleagues"

    def text(self):
        return "\n".join((self.label, self.organization, self.time_range, self.responsibility))


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    facts: tuple[Fact, ...]
    answer: str = "我正在探索数据或业务分析，但尚未确定是否转向。"
    goal_label: str = "探索数据或业务分析，尚未确定"
    current: str = ""
    uncertain: bool = True
    tags: tuple[str, ...] = ()


AUDIT = Fact("work_experience", "Audit Associate", "Public Synthetic Audit Firm",
             "2016 - 2024", "Prepared statutory audit working papers and reconciled financial records")
SCENARIOS = (
    Scenario("student_new_graduate", (Fact("education", "Diploma in Hospitality", time_range="2023 - 2026"),), tags=("student", "no_cs")),
    Scenario("experienced_professional", (Fact("work_experience", "Senior Operations Coordinator"),), tags=("experienced",)),
    Scenario("career_switcher", (Fact("work_experience", "Logistics Supervisor"),), tags=("switcher",)),
    Scenario("accounting_audit", (AUDIT,), tags=("audit", "zero_projects")),
    Scenario("finance_business", (Fact("work_experience", "Commercial Finance Analyst", responsibility="Reviewed budget variance and business reporting"),), tags=("finance",)),
    Scenario("mechanical_manufacturing", (Fact("work_experience", "Mechanical Engineer", responsibility="Reviewed tolerances and maintenance records"),), tags=("manufacturing",)),
    Scenario("marketing_ecommerce", (Fact("work_experience", "Ecommerce Coordinator", responsibility="Reviewed campaign conversion and customer reports"),), tags=("marketing",)),
    Scenario("ux_design", (Fact("work_experience", "UX Designer", responsibility="Conducted usability interviews and accessibility reviews"),), tags=("design",)),
    Scenario("work_heavy_zero_projects", (AUDIT, Fact("work_experience", "Audit Team Coordinator", responsibility="Coordinated statutory review schedules")), tags=("work_heavy", "zero_projects")),
    Scenario("education_strong_little_experience", (Fact("education", "Masters in Public Policy", time_range="2022 - 2024"),), tags=("education",)),
    Scenario("limited_education_strong_experience", (Fact("work_experience", "Warehouse Supervisor", time_range="2008 - 2024"), Fact("education", "Secondary School Certificate", time_range="2007")), tags=("limited_education", "experienced")),
    Scenario("clear_goal", (AUDIT,), answer="我希望继续审计。", goal_label="继续审计", current="我希望继续审计。", uncertain=False, tags=("clear_goal",)),
    Scenario("unknown_goal", (Fact("work_experience", "Customer Service Coordinator"),), answer="我还没有明确的职业方向，尚未确定。", goal_label="职业方向尚未确定", tags=("unknown_goal",)),
    Scenario("explicit_uncertainty", (AUDIT,), tags=("uncertainty",)),
    Scenario("cross_industry", (Fact("work_experience", "Retail Operations Coordinator"), Fact("work_experience", "Hospital Administration Coordinator", responsibility="Coordinated appointment schedules and quality records")), tags=("cross_industry",)),
    Scenario("healthcare_professional", (Fact("work_experience", "Registered Nurse", responsibility="Coordinated ward handovers and documented care procedures"),), tags=("healthcare",)),
    Scenario("operations_consulting", (Fact("work_experience", "Operations Consultant", responsibility="Mapped business processes and documented stakeholder requirements"),), tags=("consulting",)),
)

# Reserved example domain / fictional numeric strings, intentionally public-safe.
CONTACTS = ("Email: synthetic-candidate@example.invalid", "Phone: +1 202 555 0199",
            "Home address: 123 Fictional Example Lane", "Personal URL: https://example.invalid/private-synthetic")
RAW_MARKER = "PUBLIC_SYNTHETIC_RAW_ONLY_MARKER_C5A"


def upload_bytes(scenario, kind="docx"):
    paragraphs = [fact.text() for fact in scenario.facts] + [*CONTACTS, RAW_MARKER]
    if kind == "pdf":
        # The existing in-memory public PDF generator uses real pypdf resources.
        from tests.resume_doubles import pdf_bytes
        return pdf_bytes(*(line for paragraph in paragraphs for line in paragraph.splitlines()))
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    output = BytesIO()
    document.save(output)
    return output.getvalue()
