import json, glob
from bot import compose, respond
base='expanded'; trigs={}
for f in glob.glob(base+'/triggers/*.json'):
 x=json.load(open(f)); trigs[x['id']]=x
pairs=json.load(open(base+'/test_pairs.json'))['pairs']
outputs=[]
for p in pairs:
 m=json.load(open(f"{base}/merchants/{p['merchant_id']}.json")); c=json.load(open(f"{base}/customers/{p['customer_id']}.json")) if p['customer_id'] else None; cat=json.load(open(f"dataset/categories/{m['category_slug']}.json"))
 a=compose(cat,m,trigs[p['trigger_id']],c); b=compose(cat,m,trigs[p['trigger_id']],c)
 assert a==b, p['test_id']
 assert set(['body','cta','send_as','suppression_key','rationale'])<=set(a)
print('determinism: PASS for 30 canonical pairs')
st={'auto_reply_count':0,'turns':[]}
assert respond(st,'Thank you for contacting us, our team will respond.')['action']=='wait'
assert respond(st,'Thank you for contacting us, our team will respond.')['action']=='wait'
assert respond(st,'Thank you for contacting us, our team will respond.')['action']=='end'
print('auto-reply exit: PASS')
assert respond({'auto_reply_count':0,'turns':[]},"ok let's do it")['action']=='send'
print('intent transition: PASS')
assert respond({'auto_reply_count':0,'turns':[]},'stop') ['action']=='end'
print('stop handling: PASS')
