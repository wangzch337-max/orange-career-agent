"""轻量 Tool／Provider 抽象；不依赖 LangChain。"""

from abc import ABC, abstractmethod
from typing import List

from data.models import CareerReport, CourseRecord, JobIntelligenceRecord, JobRecord, MatchResult, UserProfile


class Tool(ABC):
    """所有本地工具的最小标识契约。"""

    name: str


class CourseDataProvider(Tool):
    @abstractmethod
    def load(self) -> List[CourseRecord]:
        """读取规范化课程记录。"""


class JobDataProvider(Tool):
    @abstractmethod
    def load(self) -> List[JobRecord]:
        """读取规范化岗位记录。"""


class ReportProvider(Tool):
    @abstractmethod
    def build(
        self,
        workflow_id: str,
        profile: UserProfile,
        intelligence: List[JobIntelligenceRecord],
        matches: List[MatchResult],
    ) -> CareerReport:
        """由已校验的结构化对象组装报告。"""
