from __future__ import annotations
import time, hashlib
from datetime import datetime, timezone
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any
from bot import compose, respond

app=FastAPI(title='Vera Message Engine')
START=time.time()
contexts={}
conversations={}
sent_keys=set()

class ContextIn(BaseModel):
    scope:str; context_id:str; version:int; payload:dict[str,Any]; delivered_at:str
class TickIn(BaseModel):
    now:str; available_triggers:list[str]=[]
class ReplyIn(BaseModel):
    conversation_id:str; merchant_id:str; customer_id:str|None=None; from_role:str; message:str; received_at:str; turn_number:int

@app.get('/v1/healthz')
def healthz():
    counts={k:0 for k in ['category','merchant','customer','trigger']}
    for (scope,_),v in contexts.items(): counts[scope]=counts.get(scope,0)+1
    return {'status':'ok','uptime_seconds':int(time.time()-START),'contexts_loaded':counts}

@app.get('/v1/metadata')
def metadata():
    return {'team_name':'Vera Deterministic Engine','team_members':['Candidate'],'model':'deterministic-rules-v1','approach':'context resolver + trigger router + category-aware deterministic composer + conversation FSM','contact_email':'candidate@example.com','version':'1.0.0','submitted_at':datetime.now(timezone.utc).isoformat()}

@app.post('/v1/context')
def push_context(x:ContextIn):
    if x.scope not in {'category','merchant','customer','trigger'}:
        return {'accepted':False,'reason':'invalid_scope','details':x.scope}
    key=(x.scope,x.context_id); cur=contexts.get(key)
    if cur and cur['version']>=x.version:
        return {'accepted':False,'reason':'stale_version','current_version':cur['version']}
    contexts[key]={'version':x.version,'payload':x.payload}
    return {'accepted':True,'ack_id':f'ack_{x.context_id}_v{x.version}','stored_at':datetime.now(timezone.utc).isoformat()}

def get(scope,id): return contexts.get((scope,id),{}).get('payload')

def cid_for(mid,tid,cid): return f"conv_{mid}_{tid}" if not cid else f"conv_{mid}_{cid}_{tid}"

def is_expired(trg,now):
    exp=trg.get('expires_at'); dt=parse_iso(exp); nt=parse_iso(now)
    return bool(dt and nt and nt>=dt)

def parse_iso(s):
    if not s:return None
    try:return datetime.fromisoformat(s.replace('Z','+00:00'))
    except:return None

@app.post('/v1/tick')
def tick(x:TickIn):
    actions=[]
    for tid in x.available_triggers:
        trg=get('trigger',tid)
        if not trg or is_expired(trg,x.now): continue
        mid=trg.get('merchant_id') or (trg.get('payload') or {}).get('merchant_id')
        if not mid: continue
        m=get('merchant',mid)
        if not m: continue
        cat=get('category',m.get('category_slug'))
        if not cat: continue
        cust=None; custid=trg.get('customer_id')
        if custid: cust=get('customer',custid)
        out=compose(cat,m,trg,cust)
        if not out.get('body'): continue
        sk=out.get('suppression_key','')
        if sk in sent_keys: continue
        conversation_id=cid_for(mid,tid,custid)
        if conversation_id in conversations: continue
        conversations[conversation_id]={'merchant_id':mid,'customer_id':custid,'turns':[{'role':'vera','body':out['body']}],'auto_reply_count':0,'committed':False}
        sent_keys.add(sk)
        actions.append({'conversation_id':conversation_id,'merchant_id':mid,'customer_id':custid,'send_as':out['send_as'],'trigger_id':tid,'template_name':f"vera_{trg.get('kind','trigger')}_v1",'template_params':[],'body':out['body'],'cta':out['cta'],'suppression_key':sk,'rationale':out['rationale']})
    return {'actions':actions}

@app.post('/v1/reply')
def reply(x:ReplyIn):
    st=conversations.setdefault(x.conversation_id,{'merchant_id':x.merchant_id,'customer_id':x.customer_id,'turns':[],'auto_reply_count':0,'committed':False})
    st['turns'].append({'role':x.from_role,'body':x.message})
    out=respond(st,x.message)
    if out['action']=='end': sent_keys.add(f'conversation:{x.conversation_id}')
    if out['action']=='send': st['turns'].append({'role':'vera','body':out.get('body','')})
    return out
