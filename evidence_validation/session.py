"""Orchestrator-owned bounded D.6 dialogue. All state and display are ephemeral."""

from dataclasses import dataclass, field
import re
from threading import RLock
from uuid import uuid4
from career_discovery.context import fingerprint
from role_landscape.service import normalized
from ui.conversation_store import _no_credentials
from evidence_validation.models import Binding, Token, Candidate, Outcome
from evidence_validation.sources import ExperimentRegistry
from evidence_validation.service import targets, summary, NOTICE, UNAVAILABLE
from evidence_match.projection import project_user


def intent(text):
    if not isinstance(text, str) or not 0 < len(text.strip()) <= 2000:
        return None
    s = normalized(text)
    if re.fullmatch(r"(?:我|我们)(?:怎么|如何)验证(?:这一点|这项未知|这项范围)|给我(?:一个)?小任务(?:试试|尝试)", s):
        return "experiment"
    if re.fullmatch(r"我以前(?:其实)?(?:做过|参与过|完成过)类似的(?:事|事情|工作)", s):
        return "recollection"
    if re.fullmatch(r"(?:验证|澄清)(?:第[1-9一二三四五六七八九]项|关系relationship_[0-9]{3})", s):
        return "select"
    if re.fullmatch(r"(?:查看|整理)(?:验证摘要|本次验证摘要)", s):
        return "summary"
    if re.fullmatch(r"(?:进入|转到)已有画像确认入口|我希望保存这次验证材料", s):
        return "handoff"
    if re.fullmatch(r"(?:跳过|拒绝|中止|停止)(?:这次验证|本次实验|这个小任务)", s):
        return "stop"
    if re.fullmatch(r"(?:我)?(?:已完成|完成了|完成)(?:本次实验|这个小任务)", s):
        return "completion"
    if re.fullmatch(r"(?:回忆|当前表述|范围|情境|观察|产出|反思|帮助)[:：].+", text.strip(), re.S):
        return "report"
    return None


@dataclass(frozen=True)
class Message:
    offsets: tuple[int, int, int, int, int]
    role: str
    text: str = field(repr=False)
    options: tuple = field(default=(), repr=False)
    token: object = None


def prepare(template):
    """Only approved material. No tool execution, artifact storage or grading."""
    return "\n".join(("可选公开合成小实验 · 约 " + str(template.estimated_minutes) + " 分钟",
        "唯一待核对范围：" + template.task, "给定合成材料：" + template.synthetic_material,
        "帮助规则：" + template.allowed_assistance,
        *["预期观察：" + x for x in template.expected_observations],
        *["反思问题：" + x for x in template.reflection_questions],
        *["限制：" + x for x in template.limitations],
        "可用主输入框逐项报告：观察：… / 产出：… / 反思：… / 帮助：…；完成本次实验，或中止本次实验。",
        f"模板 {template.template_id}@{template.version} · {fingerprint(template.model_dump(mode='json'))}",
        "工作来源：" + "; ".join(template.work_evidence_ids), NOTICE))


class EvidenceValidationSession:
    def __init__(self, workspace):
        self.workspace, self._lock, self.generation = workspace, RLock(), 0
        self.registry, self.prepare = ExperimentRegistry(), prepare
        self.invalidate()

    def invalidate(self):
        with self._lock:
            self.generation += 1
            self.binding = self.target = self.template = self.parent_stamp = None
            self.pending_claim = None
            self.candidates, self.messages = [], []
            self.outcome = Outcome()
            self.turns, self.experiment_selected, self.handoff_requested = 0, False, False
            self.status = "unavailable"

    def _parent(self):
        w, p = self.workspace, self.workspace.evidence_match
        if w._closed or not p.current() or p.result is None or p.context is None:
            raise ValueError("D6_PARENT_UNAVAILABLE")
        profile, _ = p._inputs()
        if project_user(profile) != p.context.user:
            raise ValueError("D6_USER_PROJECTION_MISMATCH")
        eligible = targets(p.result, p.context)
        stamp = fingerprint([p.binding.model_dump(mode="json"), p.result.model_dump(mode="json"),
                             p.context.model_dump(mode="json")])
        return p, eligible, stamp

    def current(self):
        with self._lock:
            if self.parent_stamp is None:
                return False
            try:
                p, eligible, stamp = self._parent()
                valid = stamp == self.parent_stamp
                if self.binding:
                    b, w = self.binding, self.workspace
                    template = self.registry.resolve(self.target, p.context.work)
                    valid = valid and (b.owner, b.subject, b.thread, b.generation) == (
                        w.owner_scope_id, w.subject_id, w.thread.thread_id, self.generation)
                    valid = valid and self.target in eligible and template == self.template and self._binding(p, self.target, template, b.request_id) == b
            except Exception:
                valid = False
            if not valid:
                self.invalidate(); self.status = "stale"
            return valid

    def token(self):
        # May also bind an explicit selection menu before a target is chosen.
        try:
            p, _, stamp = self._parent()
            w = self.workspace
            return Token(owner=w.owner_scope_id, subject=w.subject_id, thread=w.thread.thread_id,
                request_id=self.binding.request_id if self.binding else p.binding.request_id,
                generation=self.generation, turn=self.turns, parent_fingerprint=stamp)
        except Exception:
            return None

    def _binding(self, parent, target, template, request_id):
        b, w = parent.binding, self.workspace
        relation = next(r for r in parent.result.relationships if r.relationship_id == target.relation_id)
        return Binding(owner=w.owner_scope_id, subject=w.subject_id, thread=w.thread.thread_id,
            request_id=request_id, generation=self.generation, parent_request_id=b.request_id,
            parent_generation=b.generation, parent_binding_fingerprint=fingerprint(b.model_dump(mode="json")),
            parent_result_fingerprint=fingerprint(parent.result.model_dump(mode="json")),
            parent_context_fingerprint=fingerprint(parent.context.model_dump(mode="json")),
            profile_id=b.profile_id, profile_version=b.profile_version, profile_fingerprint=b.profile_fingerprint,
            role_id=b.role_id, source_id=b.source_id, source_version=b.source_version, source_fingerprint=b.source_fingerprint,
            relation_id=target.relation_id, relation_fingerprint=fingerprint(relation.model_dump(mode="json")),
            work_evidence_ids=target.work_evidence_ids, template_id=template.template_id if template else None,
            template_version=template.version if template else None,
            template_fingerprint=fingerprint(template.model_dump(mode="json")) if template else None)

    def _message(self, text, *, role="assistant", options=()):
        w = self.workspace
        self.messages.append(Message((len(w.chat.messages), len(w.career_reality.messages),
            len(w.role_landscape.messages), len(w.specific_role.messages), len(w.evidence_match.messages)),
            role, text, options, self.token() if options else None))
        del self.messages[:-60]

    def _offer(self, options):
        self._message("请明确选择一条关系及其中的唯一范围；不会默认选择第一项。" if options else
                      "当前没有可验证的用户侧未知范围。工作侧未知、证据冲突或材料省略不能通过实验测试用户。",
                      options=options)

    def _handoff_available(self):
        # Inspect only an already-present review/navigation token. In particular,
        # do not call available/_current: they can fingerprint resume contents.
        from career_runtime.profile_conversation import InterviewStage
        w = self.workspace
        review = w.profile_conversation
        token = review.token()
        return bool(review.stage == InterviewStage.REVIEW and token is not None and
                    (token.owner, token.thread) == (w.owner_scope_id, w.thread.thread_id))

    def select(self, token, relation_id):
        return self.submit("验证关系" + relation_id, token=token)

    def submit(self, text, *, token=None):
        with self._lock:
            self.current()
            if token is not None and token != self.token():
                return True
            kind = intent(text)
            if kind is None:
                return False
            try:
                _no_credentials(text)
            except ValueError:
                return True
            if self.workspace.agent_session.busy:
                return True
            try:
                parent, options, stamp = self._parent()
            except Exception:
                self.invalidate(); self._message(UNAVAILABLE)
                return True
            self.parent_stamp = stamp
            if self.turns >= 24 and kind != "stop":
                self._message("本次验证达到有限会话边界，请中止后重新明确范围。")
                return True
            self.turns += 1
            self._message(text.strip(), role="user")
            if kind == "select":
                raw = normalized(text)
                target = next((x for x in options if raw == "验证关系" + x.relation_id or raw == "澄清关系" + x.relation_id), None)
                number = re.search(r"第([1-9一二三四五六七八九])项", raw)
                if number:
                    n = int(number[1]) if number[1].isdigit() else "一二三四五六七八九".index(number[1]) + 1
                    target = options[n-1] if n <= len(options) else None
                if target is None:
                    self._offer(options); return True
                try:
                    template = self.registry.resolve(target, parent.context.work)
                except Exception:
                    self.invalidate()
                    self._message("批准模板来源校验未通过，本次验证未开始；不会使用其他资料或临时编任务。")
                    return True
                claim = self.pending_claim
                self.generation += 1
                self.target, self.template = target, template
                self.binding = self._binding(parent, target, template, "validation_" + uuid4().hex)
                self.candidates = [Candidate(kind="recollection", text=claim)] if claim else []
                self.pending_claim = None
                self.outcome, self.experiment_selected, self.handoff_requested = Outcome(), False, False
                self.status = "active"
                self._message("只核对：" + target.unresolved_scope + "\n可先回忆过去经历（回忆：… / 当前表述：… / 范围：… / 情境：…），也可直接说“给我一个小任务试试”。可跳过这次验证。\n" + NOTICE)
                return True
            if kind == "stop":
                self.outcome = Outcome(completion="stopped")
                self.status = "stopped"; self.experiment_selected = False
                self.pending_claim = None; self.candidates = []
                self.generation += 1
                # Revocation consumes all queued target/outcome tokens.
                self.binding = self.target = self.template = None
                self._message("已中止本次验证，未保存候选或实验结果。当前 D.5 关系不变。")
                return True
            if self.target is None:
                if kind == "recollection":
                    self.pending_claim = text.strip()
                self._offer(options); return True
            if self.status != "active":
                self._message("这次验证已失效，请重新明确范围。")
                return True
            if kind == "recollection":
                if len(self.candidates) < 12:
                    self.candidates.append(Candidate(kind="recollection", text=text.strip()))
                self._message("这只是待核对回忆，没有成为画像事实。请补充具体做了什么、范围、情境与获得的帮助；使用 回忆：… / 当前表述：… / 范围：… / 情境：…")
                return True
            if kind == "report":
                prefix, value = re.split(r"[:：]", text.strip(), maxsplit=1)
                if not 0 < len(value.strip()) <= 600:
                    self._message("请把单项自述限制在 600 字以内；未保存该项。")
                    return True
                fields = {"回忆":"recollection", "当前表述":"current_claim", "范围":"scope", "情境":"context"}
                if prefix in fields:
                    if len(self.candidates) < 12:
                        self.candidates.append(Candidate(kind=fields[prefix], text=value.strip()))
                    self._message("已暂存一项会话候选（未确认）。可继续补充、查看验证摘要，或显式转到已有画像确认入口。")
                elif not self.experiment_selected:
                    self._message("尚未选择本次实验，没有把这条报告记成实验结果。")
                else:
                    name = {"观察":"observations", "产出":"text_outputs", "反思":"reflections", "帮助":"assistance_reports"}[prefix]
                    values = getattr(self.outcome, name)
                    if len(values) < 8:
                        self.outcome = self.outcome.model_copy(update={name:(*values, value.strip())})
                    self._message("已暂存未验证的实验自述。产出与帮助情况不证明独立完成；反思不是技能事实。")
                return True
            if kind == "completion":
                if self.experiment_selected:
                    self.outcome = self.outcome.model_copy(update={"completion":"reported_completed"})
                    self._message(summary(self.target, self.candidates, self.outcome))
                else:
                    self._message("未选择本次实验；完成声明不能成为能力事实。")
                return True
            if kind == "summary":
                self._message(summary(self.target, self.candidates, self.outcome)); return True
            if kind == "handoff":
                self.handoff_requested = True
                # A navigation handoff ONLY. Never invoke start/confirm/refinement:
                # those gates may require a resume, fresh consent or a provider.
                available = self._handoff_available()
                self._message("已有画像审核入口可用：请自行进入并重新核对材料及确认授权；本次仅提示入口，未自动转移或确认，未进入 canonical Profile。" if available else
                    "当前已有画像确认入口不可用。候选继续仅本次会话有效，未进入 canonical Profile；D.6 不代替确认，也不自动读取简历或启动旧流程。")
                return True
            if self.template is None:
                self._message("这一具体范围没有批准模板，安全 unsupported；可以澄清过去经历或跳过，不会临时编任务。")
                return True
            template, expected = self.template, self.token()
        # Generation-bound publication also rejects a late future tool result.
        try:
            presentation = self.prepare(template)
        except Exception:
            with self._lock:
                if self.current() and self.token() == expected:
                    self._message("本次实验展示未完成；没有模型重试或临时替代任务。")
            return True
        with self._lock:
            if not self.current() or self.token() != expected:
                return True
            self.experiment_selected = True
            self._message(presentation)
        return True
