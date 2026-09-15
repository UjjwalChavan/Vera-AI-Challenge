import json,glob,os
from bot import compose
base='expanded'
triggers={}
for f in glob.glob(base+'/triggers/*.json'):
    x=json.load(open(f)); triggers[x['id']]=x
pairs=json.load(open(base+'/test_pairs.json'))['pairs']
out=[]
for p in pairs:
    m=json.load(open(f"{base}/merchants/{p['merchant_id']}.json"))
    c=json.load(open(f"{base}/customers/{p['customer_id']}.json")) if p['customer_id'] else None
    cat=json.load(open(f"dataset/categories/{m['category_slug']}.json"))
    o=compose(cat,m,triggers[p['trigger_id']],c)
    out.append({'test_id':p['test_id'],**o})
with open('submission.jsonl','w') as f:
    for x in out:f.write(json.dumps(x,ensure_ascii=False)+'\n')
print('wrote',len(out),'lines')
