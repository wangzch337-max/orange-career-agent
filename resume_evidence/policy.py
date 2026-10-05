"""Single source of bounded resume extraction policy."""

MAX_CONTEXT_CHARS = 12_000
MAX_CONTEXT_JSON_CHARS = 16_000
MAX_CONTEXT_BLOCKS = 32
MAX_BLOCK_CHARS = 1600
MAX_EVIDENCE_ITEMS = 40
MAX_SOURCE_REFS = 6
MAX_WORK_DETAILS = 6
MAX_UNCERTAINTIES = 12
MAX_CLAIM_CHARS = 400
MAX_QUOTE_CHARS = 800
MAX_ANALYSIS_EVENTS = 32
MODEL = "qwen3.8-flash"
PROMPT_NAME = "resume_evidence"
PROMPT_VERSION = "v1"
CONSENT_VERSION = "resume-ai-v1"

CATEGORIES = (
    "education", "work_experience", "projects", "responsibilities", "achievements",
    "skills", "tools", "domain_knowledge", "certifications", "professional_qualifications",
    "research", "leadership", "collaboration", "languages", "portfolio", "business_metrics",
    "awards", "publications", "other_evidence", "uncertainty",
)
