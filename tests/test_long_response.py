"""Public deterministic real-adapter stress tests; ZERO live requests or sleeps."""

import json
import sqlite3
from dataclasses import replace
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from pydantic import SecretStr

from career_runtime.engine import OrangeRuntime, TurnComplete, AnswerDelta, TurnFailed
from career_runtime.finalization import finalize_wire, MAX_WIRE_CHARACTERS
from career_runtime.models import ResponseEnvelope, ResponseCore, StreamMetrics, length_bucket
from career_runtime.session import AgentSession, INTERRUPTED_TEXT, VALIDATION_TEXT, PERSISTENCE_TEXT, completed_metadata
from career_runtime.streaming import StreamingQwenProvider, StreamComplete, VisibleJSONStream
from providers.models import LLMMessage
from tests.agent_doubles import plan, answer, request
from tests.test_agent_runtime import seed
from tests.test_agent_streaming import Transport, chunk
from ui.chat_runtime import Workspace


def prose(size=5000):
    pattern = '## 公开合成沟通练习\n\n先倾听，再询问需要什么支持。🍊“我愿意听你说。”\n\n- 不急于下结论；尊重边界。\n\n```python\nmessage = "中文与标点"\n```\n'
    return (pattern * (size//len(pattern)+1))[:size]


def wire(text, suggestions=(), *, escaped=False, citations=(), proposals=()):
    return json.dumps(dict(visible_response=text, citations=list(citations),
        candidate_proposals=list(proposals), suggestions=list(suggestions)), ensure_ascii=escaped)


def split(value, shape):
    widths = {"tiny": (1,), "medium": (127,), "uneven": (2,1,19,700,3,5,61)}[shape]
    position, index, result = 0, 0, []
    while position < len(value):
        width = widths[index % len(widths)]
        result.append(value[position:position+width])
        position += width
        index += 1
    return result


class LongTransport(Transport):
    def __init__(self, raw, *, shape="medium", finish="stop", interruption=False, plans=None):
        chunks = [chunk(part) for part in split(raw, shape)]
        if interruption:
            chunks.append(RuntimeError("PRIVATE_TRANSPORT_EXCEPTION_SENTINEL"))
        else:
            chunks.append(chunk(finish=finish))
            chunks.append(NS(choices=[], usage=NS(prompt_tokens=10,completion_tokens=20,total_tokens=30)))
        super().__init__(chunks)
        self.plan_calls = []
        self.plans = list(plans or [plan(suggestions="optional_relevant")])

    def parse(self, **kwargs):
        self.plan_calls.append(kwargs)
        return NS(choices=[NS(message=NS(parsed=self.plans.pop(0)))], usage=None)


def setup_session(workspace, transport):
    provider = StreamingQwenProvider(SecretStr("sk-test-offline-only"),SecretStr("https://example.invalid"),client=transport)
    session = AgentSession(workspace,provider_factory=lambda: provider)
    session.set_consent(granted=True)
    return session, provider


def turn(workspace, transport, text="公开合成：请给出详细的一般沟通建议。"):
    session, provider = setup_session(workspace, transport)
    session.queue(text,"typed")
    pending=session.pending; session.pending=None
    events=list(session.stream_turn(pending))
    stored=workspace.store.list_messages(workspace.owner_scope_id,pending.thread_id)
    return session,provider,pending,events,stored


@pytest.fixture
def workspace(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as value:
        yield value


@pytest.mark.parametrize("size",[450,2000,5000,9500])
@pytest.mark.parametrize("shape",["tiny","medium","uneven"])
@pytest.mark.parametrize("escaped",[False,True])
def test_length_chunk_unicode_matrix_identical_once_and_reload(workspace,size,shape,escaped):
    text=prose(size); t=LongTransport(wire(text,escaped=escaped),shape=shape)
    session,p,pending,events,stored=turn(workspace,t)
    final=next(e for e in events if isinstance(e,TurnComplete))
    visible="".join(e.text for e in events if isinstance(e,AnswerDelta))
    assert visible == text == final.answer.visible_response == stored[-1].content
    assert len(stored)==2 and stored[-1].metadata['agent_stream']['persistence_committed']
    assert final.stream_metrics.provider_finish_category=='normal_stop'
    assert final.stream_metrics.visible_length_bucket==length_bucket(size)
    assert len(t.calls)==len(t.plan_calls)==1
    assert not json.loads(t.calls[0]['messages'][1]['content'])['selected_context']
    assert list(session.stream_turn(pending))==[]
    workspace.activate(pending.thread_id)
    assert workspace.chat.messages[-1].content==text and len(t.calls)==1


@pytest.mark.parametrize("bad",[None,{},[1],['重复','重复'],[''],['过长'*70],['a']*5])
def test_malformed_optional_suggestions_keep_long_core(workspace,bad):
    raw=json.loads(wire(prose()));raw['suggestions']=bad
    _,_,_,events,stored=turn(workspace,LongTransport(json.dumps(raw,ensure_ascii=False)))
    final=next(e for e in events if isinstance(e,TurnComplete))
    assert final.answer.suggestions==[] and stored[-1].content==prose()
    assert stored[-1].metadata['agent_stream']['degraded_optional_metadata']
    assert any(d.stage=='response_optional_validation' for d in final.diagnostics)


@pytest.mark.parametrize("tail",['["未完整结束','{"wrong":', '["下一步"]', 'null'])
def test_incomplete_optional_tail_after_sealed_core_kept_only_on_stop(workspace,tail):
    raw=wire(prose()).rsplit('"suggestions":',1)[0]+'"suggestions":'+tail
    _,_,_,events,stored=turn(workspace,LongTransport(raw))
    assert any(isinstance(e,TurnComplete) for e in events)
    assert stored[-1].content==prose() and stored[-1].metadata['suggestions']==[]
    assert not stored[-1].metadata['agent_stream']['envelope_complete']


@pytest.mark.parametrize("finish",['length','content_filter','tool_calls',None])
def test_real_truncation_never_salvaged_even_with_complete_core(workspace,finish):
    session,p,_,events,stored=turn(workspace,LongTransport(wire(prose()),finish=finish))
    assert not any(isinstance(e,TurnComplete) for e in events)
    assert stored[-1].content==INTERRUPTED_TEXT
    metric=stored[-1].metadata['agent_stream']
    assert metric['transport_completed'] and metric['output_limit_reached']==(finish=='length')
    assert p.attempts[-1].total_tokens==30 and len(p.attempts)==2
    assert session.last_failure.reason==('output_limit' if finish=='length' else 'transport_incomplete')


def test_interrupted_after_large_visible_core_still_fails(workspace):
    session,p,_,events,stored=turn(workspace,LongTransport(wire(prose()),interruption=True))
    assert not any(isinstance(e,TurnComplete) for e in events)
    assert len(''.join(e.text for e in events if isinstance(e,AnswerDelta)))==5000
    assert stored[-1].content!=prose() and not stored[-1].metadata['agent_stream']['transport_completed']
    assert p.attempts[-1].total_tokens is None
    assert 'PRIVATE_' not in json.dumps(stored[-1].metadata)


@pytest.mark.parametrize("damage",['missing_citations','missing_candidates','unowned','candidate','duplicate_core','unknown_field','incomplete_text','too_long','blank'])
def test_required_integrity_remains_strict(workspace,damage):
    payload=json.loads(wire(prose()))
    if damage=='missing_citations': del payload['citations']
    elif damage=='missing_candidates': del payload['candidate_proposals']
    elif damage=='unowned': payload['citations']=['foreign_ref']
    elif damage=='candidate': payload['candidate_proposals']=[dict(kind='memory',dimension='career_direction_priority',value='ai_product',user_quote='invented')]
    elif damage=='unknown_field': payload['reasoning']='PRIVATE_HIDDEN_SENTINEL'
    elif damage=='too_long': payload['visible_response']=prose(10001)
    elif damage=='blank': payload['visible_response']='  '
    raw=json.dumps(payload,ensure_ascii=False)
    if damage=='duplicate_core': raw=raw[:-1]+',"citations":[]}'
    elif damage=='incomplete_text': raw=raw[:raw.index('citations')-4]
    _,_,_,events,stored=turn(workspace,LongTransport(raw))
    assert not any(isinstance(e,TurnComplete) for e in events)
    assert stored[-1].content!=prose() and 'PRIVATE_HIDDEN' not in json.dumps(stored[-1].metadata)


@pytest.mark.parametrize("kind",['policy','repeat','credential'])
def test_suggestion_policy_failure_degrades_without_second_call(workspace,kind):
    user='公开合成：请给出详细的一般沟通建议。'
    suggestion=user if kind=='repeat' else ('sk-'+'Q'*25 if kind=='credential' else '给一个示例')
    planned=plan(suggestions='none' if kind=='policy' else 'optional_relevant')
    t=LongTransport(wire(prose(),[suggestion]),plans=[planned])
    _,_,_,events,stored=turn(workspace,t,user)
    assert any(isinstance(e,TurnComplete) for e in events)
    assert stored[-1].content==prose() and stored[-1].metadata['suggestions']==[]
    assert len(t.calls)==len(t.plan_calls)==1


def test_long_career_reads_context_without_authority_mutation(workspace):
    original=seed(workspace)
    plans=[plan(relevance='DIRECT_CAREER',tools=[request('current_profile',sections=['skills'])],suggestions='optional_relevant')]
    t=LongTransport(wire(prose()),plans=plans)
    _,_,_,events,stored=turn(workspace,t,'公开合成：根据已知证据详细讨论两种方向，未知仍是未知，不作总体排名。')
    final=next(e for e in events if isinstance(e,TurnComplete))
    assert stored[-1].content==prose() and final.accounting.tool_attempt_count==1
    assert json.loads(t.calls[0]['messages'][1]['content'])['selected_context']
    assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id)==original
    assert not workspace.controller.active_memories()


def test_long_valid_suggestions_and_core_refs_keep_identity(workspace):
    original=seed(workspace); ref=original.skills[0].evidence_ids[0]
    t=LongTransport(wire(prose(),['提供一个沟通例子'],citations=[ref]),plans=[plan(relevance='DIRECT_CAREER',tools=[request('current_profile',sections=['skills'])],suggestions='optional_relevant')])
    _,_,_,events,stored=turn(workspace,t)
    assert next(e for e in events if isinstance(e,TurnComplete)).answer.citations==[ref]
    assert stored[-1].metadata['suggestions']==['提供一个沟通例子']


def test_service_restart_restores_long_exactly_without_provider(tmp_path):
    owner=str(uuid4())
    with Workspace(owner,tmp_path) as w:
        t=LongTransport(wire(prose(9500)));_,_,_,_,stored=turn(w,t); text=stored[-1].content
    with Workspace(owner,tmp_path) as w:
        assert w.chat.messages[-1].content==text and w.agent_session.provider is None
        assert len(t.calls)==1


@pytest.mark.parametrize("ack_lost",[False,True])
def test_persistence_failure_or_lost_ack_does_not_reexecute(workspace,monkeypatch,ack_lost):
    original=workspace.store.append_turn
    def fail(*args,**kwargs):
        if ack_lost: original(*args,**kwargs)
        raise sqlite3.OperationalError('PRIVATE_SQL_ERROR_SENTINEL')
    monkeypatch.setattr(workspace.store,'append_turn',fail)
    session,p,pending,events,stored=turn(workspace,LongTransport(wire(prose())))
    assert len(p.attempts)==2
    if ack_lost:
        assert len(stored)==2 and stored[-1].content==prose()
        assert any(isinstance(e,TurnComplete) for e in events)
        assert list(session.stream_turn(pending))==[]
    else:
        assert stored==() and session.last_failure.reason=='persistence_error'
        assert not session.failure_persisted and not any(isinstance(e,TurnComplete) for e in events)
    assert 'PRIVATE_SQL' not in str(session.last_failure)


def test_optional_runtime_metadata_is_individually_dropped_not_global_store_relaxation(workspace):
    _,_,_,events,_=turn(workspace,LongTransport(wire(prose())))
    final=next(e for e in events if isinstance(e,TurnComplete))
    damaged=replace(final,usage=({'raw_answer':'PRIVATE_METADATA_SENTINEL'},),accounting=None)
    metadata,metrics=completed_metadata(damaged)
    assert metrics.degraded_optional_metadata and 'agent_usage' not in metadata and 'agent_accounting' not in metadata
    assert 'PRIVATE_METADATA' not in json.dumps(metadata)
    with pytest.raises(ValueError):
        workspace.store.append_turn(workspace.owner_scope_id,workspace.thread.thread_id,'问题','回答',assistant_metadata={'raw_answer':'PRIVATE'})


def test_direct_sqlite_size_boundary_is_existing_20000(workspace):
    pair=workspace.store.append_turn(workspace.owner_scope_id,workspace.thread.thread_id,'问题',prose(20000))
    assert len(pair[-1].content)==20000
    with pytest.raises(ValueError): workspace.store.append_turn(workspace.owner_scope_id,workspace.thread.thread_id,'问题',prose(20001))


def test_wire_and_visible_budgets_are_separate_and_bounded():
    text='🍊'*10000; raw=wire(text,escaped=True)
    assert len(raw)>24000 and len(raw)<MAX_WIRE_CHARACTERS
    projection=VisibleJSONStream()
    assert ''.join(projection.feed(s) for s in split(raw,'uneven'))==text
    assert finalize_wire(raw)[0].visible_response==text
    with pytest.raises(ValueError): finalize_wire(raw+' '*MAX_WIRE_CHARACTERS)


def test_sdk_utf8_sse_byte_splits_decode_incrementally_no_network():
    import httpx
    from openai import OpenAI
    raw=wire(prose(2000))
    data=''.join('data: '+json.dumps({'id':'fake','object':'chat.completion.chunk','created':0,'model':'qwen3.8-flash','choices':[{'index':0,'delta':{'content':s},'finish_reason':None}]},ensure_ascii=False)+'\n\n' for s in split(raw,'uneven'))
    data+='data: '+json.dumps({'id':'fake','object':'chat.completion.chunk','created':0,'model':'qwen3.8-flash','choices':[{'index':0,'delta':{},'finish_reason':'stop'}]})+'\n\ndata: [DONE]\n\n'
    class Bytes(httpx.SyncByteStream):
        def __iter__(self):
            for byte in data.encode('utf-8'): yield bytes([byte])
    client=OpenAI(api_key='sk-test-offline-only',base_url='https://example.invalid',http_client=httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Bytes()))),max_retries=0)
    try:
        p=StreamingQwenProvider(SecretStr('fake'),SecretStr('https://example.invalid'),client=client)
        events=list(p.stream_structured([LLMMessage(role='user',content='公开测试')],ResponseEnvelope,OrangeRuntime(p).response_options,prompt_name='orange_response',prompt_version='v1'))
        assert events[-1].response.data.visible_response==prose(2000)
        assert events[-1].metrics.transport_completed
    finally: client.close()


def test_ordered_core_wire_schema_and_runtime_only_output_budget():
    from providers.models import GenerationOptions
    from openai.lib._pydantic import to_strict_json_schema
    schema=to_strict_json_schema(ResponseEnvelope)
    assert list(schema['properties'])==['visible_response','citations','candidate_proposals','suggestions']
    assert schema['additionalProperties'] is False and set(schema['required'])==set(schema['properties'])
    runtime=OrangeRuntime(setup_session_dummy())
    assert runtime.response_options.max_output_tokens==8192 and runtime.response_options.max_retries==0
    assert runtime.response_options.timeout_seconds==90 and runtime.planning_options.max_output_tokens==1800
    with pytest.raises(ValueError): GenerationOptions(max_output_tokens=8192)


def setup_session_dummy():
    return StreamingQwenProvider(SecretStr('fake'),SecretStr('https://example.invalid'),client=LongTransport(wire('短答复')))


def test_duplicate_identical_completion_is_idempotent_but_conflicting_fails(workspace):
    from tests.agent_doubles import ScriptedProvider
    class Duplicate(ScriptedProvider):
        def stream_structured(self,*args,**kwargs):
            for event in super().stream_structured(*args,**kwargs):
                yield event
                if isinstance(event,StreamComplete): yield event
    provider=Duplicate(response=answer(prose()))
    session=AgentSession(workspace,provider_factory=lambda:provider);session.set_consent(granted=True)
    session.queue('公开问题','typed'); events=list(session.stream_turn(session.pending))
    assert next(e for e in events if isinstance(e,TurnComplete)).stream_metrics.duplicate_finalization_count==1
    assert workspace.chat.messages[-1].content==prose() and len(workspace.chat.messages)==2
    assert list(session.stream_turn(session.pending))==[] and provider.stream_calls==1
    class Conflict(ScriptedProvider):
        def stream_structured(self,*args,**kwargs):
            for event in super().stream_structured(*args,**kwargs):
                yield event
                if isinstance(event,StreamComplete):
                    yield replace(event,response=event.response.model_copy(update={'data':answer('另一个回答')}))
    other=AgentSession(workspace,provider_factory=lambda:Conflict(response=answer(prose())))
    other.queue('另一次公开问题','typed'); failed=list(other.stream_turn(other.pending))
    assert not any(isinstance(e,TurnComplete) for e in failed)
    assert workspace.chat.messages[-1].content!=prose()


def test_close_cleanup_failure_does_not_erase_successful_core(workspace):
    t=LongTransport(wire(prose()))
    def fail_close(): raise RuntimeError('PRIVATE_CLEANUP_SENTINEL')
    t.stream.close=fail_close
    _,_,_,events,stored=turn(workspace,t)
    assert any(isinstance(e,TurnComplete) for e in events)
    assert stored[-1].content==prose() and stored[-1].metadata['agent_stream']['close_failed']


@pytest.mark.parametrize('theme',['跟随系统','浅色模式','深色模式'])
def test_long_ui_completion_rerun_theme_preserves_exact_transcript(tmp_path,theme):
    from tests.test_chat_product import app,WORKSPACE_KEY,suggestions
    value=app(tmp_path,str(uuid4()));w=value.session_state[WORKSPACE_KEY]
    try:
        t=LongTransport(wire(prose(),['再给一个沟通例子']),shape='uneven')
        _,provider=setup_session(w,t)
        w.agent_session.provider_factory=lambda:provider
        value.button(key='orange_agent_consent').click().run()
        value.radio(key='orange_appearance').set_value(theme).run()
        value.chat_input[0].set_value('公开合成：详细的一般沟通建议。').run(timeout=30)
        assert not value.exception and len(value.chat_message)==2
        assert w.chat.messages[-1].content==prose()
        assert [b.label for b in suggestions(value)]==['再给一个沟通例子']
        value.run(timeout=30)
        assert not value.exception and len(t.calls)==1 and len(value.chat_message)==2
        assert value.radio(key='orange_appearance').options==['跟随系统','浅色模式','深色模式']
        assert len(value.chat_input)==1
    finally: w.close()


def test_safe_stream_metrics_cannot_accept_content_or_reasoning(workspace):
    _,_,_,events,stored=turn(workspace,LongTransport(wire(prose())))
    metadata=json.dumps(stored[-1].metadata,ensure_ascii=False)
    assert prose() not in metadata and 'reasoning_content' not in metadata
    with pytest.raises(ValueError): StreamMetrics(raw_answer=prose())
    with pytest.raises(ValueError): StreamMetrics(provider_finish_category='PRIVATE_UNKNOWN')
    with pytest.raises(ValueError):
        workspace.store.append_turn(workspace.owner_scope_id,workspace.thread.thread_id,'问题','回答',assistant_metadata={'agent_stream':{'reasoning':'PRIVATE'}})
