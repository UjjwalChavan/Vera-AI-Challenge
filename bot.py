from __future__ import annotations
import hashlib,re
from datetime import datetime, timezone
from typing import Any


def owner(merchant):
    i=merchant.get('identity',{})
    return i.get('owner_first_name') or i.get('name','there').split()[0]

def cityloc(m):
    i=m.get('identity',{}); return ', '.join(x for x in [i.get('locality'),i.get('city')] if x)

def active_offers(m):
    return [o for o in m.get('offers',[]) if str(o.get('status','')).lower()=='active']

def offer(m, terms=()):
    offers=active_offers(m)
    for o in offers:
        s=o.get('title','').lower()
        if any(t.lower() in s for t in terms): return o
    return offers[0] if offers else None

def money_title(o): return o.get('title') if o else None

def pct(x):
    try:return f"{abs(float(x))*100:.0f}%"
    except:return str(x)

def parse_dt(s):
    if not s:return None
    try:return datetime.fromisoformat(s.replace('Z','+00:00'))
    except:return None

def fact_source(category, trigger):
    return trigger.get('source') or category.get('source')

def digest_item(category, item_id):
    for x in category.get('digest',[]):
        if x.get('id')==item_id:return x
    return None

def recent_merchant_touch(m):
    hist=m.get('conversation_history',[])
    return hist[-1] if hist else None

def lang_style(customer=None, merchant=None):
    p=(customer or {}).get('identity',{}).get('language_pref') or (merchant or {}).get('identity',{}).get('languages',["en"])[0]
    p=p.lower()
    if 'hi' in p: return 'hi'
    return 'en'

def choose_cta(kind, customer=False):
    if kind in {'research_digest','cde_opportunity','curious_ask_due'}: return 'open_ended'
    if customer: return 'binary_yes_no'
    return 'binary_yes_no'

def rationale(kind, facts, action):
    return f"{kind}: {facts}. Next step is {action}; message uses only supplied context and one primary CTA."

def compose(category:dict, merchant:dict, trigger:dict, customer:dict|None=None)->dict:
    kind=trigger.get('kind','')
    p=trigger.get('payload') or {}
    mname=owner(merchant); cat=merchant.get('category_slug') or category.get('slug','')
    cust=customer.get('identity',{}).get('name') if customer else None
    customer_facing=customer is not None
    send_as='merchant_on_behalf' if customer_facing else 'vera'
    suppression=trigger.get('suppression_key') or f"{kind}:{trigger.get('id','')}"
    body=''; cta=choose_cta(kind,customer_facing); template=f"vera_{kind}_v1"

    if kind=='research_digest':
        item=digest_item(category,p.get('top_item_id')) or (category.get('digest') or [{}])[0]
        title=item.get('title','A new category research item landed')
        src=item.get('source')
        extra=[]
        if item.get('trial_n'): extra.append(f"{item['trial_n']:,}-patient trial")
        if item.get('summary'): extra.append(item['summary'])
        elif item.get('title'): extra.append(title)
        anchor='; '.join(extra)
        if 'high_risk' in ' '.join(merchant.get('signals',[])).lower() and item.get('patient_segment'):
            lead=f"One item is relevant to your high-risk-adult cohort — {anchor}."
        else: lead=f"One item stood out for your practice — {anchor}."
        body=f"{mname}, {src or 'a new industry digest'} landed. {lead} Want me to pull the key points and turn them into a short patient/marketing asset?"
        if src: body += f" — {src}"
        cta='open_ended'; action='pull the source and make a usable asset'
        facts=title
    elif kind=='cde_opportunity':
        item=digest_item(category,p.get('digest_item_id'))
        title=item.get('title') if item else 'a relevant member resource'
        fee=p.get('fee','')
        body=f"{mname}, {title} is available {('free for members' if fee=='free_for_members' else fee)} and you have {p.get('credits',0)} credits. Want me to pull the details and turn it into a concrete next step for your practice?"
        cta='open_ended'; action='use the available member resource'; facts=f"{p.get('credits',0)} credits, {fee}"
    elif kind in {'perf_dip','seasonal_perf_dip'}:
        metric=p.get('metric') or 'performance'; d=p.get('delta_pct'); base=p.get('vs_baseline')
        signals=merchant.get('signals',[]); offers=active_offers(merchant)
        if kind=='seasonal_perf_dip' and p.get('is_expected_seasonal'):
            season=p.get('season_note') or p.get('window','seasonal window')
            body=f"{mname}, {metric} are down {pct(d)} in the last {p.get('window','7d')}, but the context flags this as an expected seasonal dip ({season}). I'd hold off on extra acquisition spend and use the period to strengthen retention. Want me to draft one retention action?"
            action='protect retention rather than overreact to an expected dip'; facts=f"{metric} {pct(d)}; expected seasonal dip"
        else:
            baseline=f" from a {base:g} baseline" if isinstance(base,(int,float)) else ''
            if signals:
                sig=', '.join(signals[:2])
                rec='I would fix the strongest profile/visibility issue before buying more traffic.' if not offers else f"You already have {offers[0]['title']} live, so I'd improve conversion before adding another offer."
            else: rec='I would diagnose the funnel before adding a new promotion.'
            body=f"{mname}, {metric} are down {pct(d)} over {p.get('window','7d')}{baseline}. {rec} Want me to turn the diagnosis into a 3-step fix?"
            action='diagnose and fix the highest-leverage issue'; facts=f"{metric} down {pct(d)}{baseline}"
        cta='binary_yes_no'
    elif kind=='perf_spike':
        metric=p.get('metric') or merchant.get('performance',{}).get('primary_metric') or 'performance'; d=p.get('delta_pct'); base=p.get('vs_baseline'); driver=p.get('likely_driver')
        if d is None:
            dp=merchant.get('performance',{}).get('delta_7d',{}); d=dp.get('calls_pct') or dp.get('views_pct') or 0
        if base is None: base=merchant.get('performance',{}).get('calls') or merchant.get('performance',{}).get('views') or 'current'
        body=f"{mname}, {metric} are up {pct(d)} in {p.get('window','7d')} versus a {base} baseline" + (f", likely driven by {driver.replace('_',' ')}." if driver else '.')
        body += " This is a good moment to capture the extra demand rather than change the offer blindly. Want me to draft the next conversion step?"
        cta='binary_yes_no'; action='capture the spike'; facts=f"{metric} +{pct(d)} vs {base} baseline"
    elif kind=='active_planning_intent':
        topic=p.get('intent_topic','the idea you raised').replace('_',' ')
        last=p.get('merchant_last_message','')
        if 'corporate' in topic and cat=='restaurants':
            o=offer(merchant,('thali',)); price=o.get('title') if o else None
            body=f"{mname}, here's a starter version for the corporate bulk-thali idea you raised:\n\n• 10 thalis: {price or 'use your current lunch-thali price'}\n• 25+ thalis: ask for a bulk quote\n• Confirm orders the day before and set a fixed lunch delivery window\n\nI kept the pricing grounded in your current offer. Want me to turn this into a 3-line WhatsApp for office admins?"
        elif 'kids_yoga' in topic:
            o=offer(merchant,('499','free body'))
            body=f"{mname}, for the kids-yoga program you asked about, I'd start with a simple 4-week pilot: one fixed weekend slot, age-banded groups, and a clear parent outcome. Your current {o['title'] if o else 'active offer'} can be the entry point without inventing a new price. Want me to draft the parent-facing announcement?"
        else:
            body=f"{mname}, picking up your plan on {topic}: {last}. I can turn that into a simple first version using the offers and facts already on your profile. Want me to draft it?"
        cta='binary_yes_no'; action='turn explicit planning intent into an artifact'; facts=f"explicit planning intent: {topic}"
    elif kind=='competitor_opened':
        name=p.get('competitor_name') or 'a competitor'; dist=p.get('distance_km'); their=p.get('their_offer');
        our=offer(merchant)
        body=f"{mname}, {name} opened {dist} km away" + (f" with {their}" if their else '') + ". I'd avoid matching a competitor blindly; your strongest response is to make your existing value proposition clearer."
        if our: body+=f" Your active offer is {our['title']}. Want me to draft a profile/post angle around that?"
        else: body+=" Want me to draft a profile/post angle from the services already on your listing?"
        cta='binary_yes_no'; action='respond to competition without an unsupported price war'; facts=f"{name} at {dist} km" + (f", {their}" if their else '')
    elif kind=='ipl_match_today':
        match=p.get('match','today’s match'); venue=p.get('venue'); tm=p.get('match_time_iso'); o=offer(merchant)
        time_label=(tm[11:16] if tm and len(tm)>=16 else 'match time')
        if p.get('is_weeknight') is False and o and 'Tue-Thu' in o.get('title',''):
            body=f"Quick heads-up {mname} — {match} is at {venue} today at {time_label}. Your {o['title']} is Tue-Thu, so I wouldn't stretch it into Saturday. I'd position that existing BOGO for delivery on its eligible days instead. Want me to draft the delivery creative?"
        else:
            body=f"{mname}, {match} is at {venue} today. You already have {o['title'] if o else 'your current offers'} live. Want me to draft a match-day message using only that existing offer?"
        cta='binary_yes_no'; action='use existing offer without changing its terms'; facts=f"{match} at {venue}, existing offer {o['title'] if o else 'none'}"
    elif kind=='milestone_reached':
        metric=p.get('metric') or merchant.get('performance',{}).get('milestone_metric') or 'profile milestone'; val=p.get('value_now'); target=p.get('milestone_value')
        if val is None or target is None:
            body=f"{mname}, you have an imminent {metric.replace('_',' ')} milestone in the current trigger context. Want me to turn it into a simple social-proof post using the facts on your profile?"
        else:
            gap=target-val if isinstance(val,(int,float)) and isinstance(target,(int,float)) else 'a little'
            body=f"{mname}, you're at {val} {metric.replace('_',' ')} — just {gap} from the {target} milestone. Want me to draft a simple post that turns the milestone into social proof?"
        cta='binary_yes_no'; action='turn an imminent milestone into proof'; facts=f"{metric}={val}, target={target}"
    elif kind=='gbp_unverified':
        body=f"{mname}, your Google Business Profile is still unverified. The supplied verification path is {p.get('verification_path','the available verification process')}, with an estimated {pct(p.get('estimated_uplift_pct',0))} uplift if completed. Want the shortest 3-step checklist?"
        cta='binary_yes_no'; action='complete profile verification'; facts='GBP unverified'
    elif kind=='category_seasonal':
        trends=', '.join(p.get('trends',[])[:3]); body=f"{mname}, summer demand is shifting: {trends}. The context recommends a shelf action, so I'd move attention toward the strongest demand signals rather than promote cold/cough stock. Want me to turn this into a shelf-priority list?"; cta='binary_yes_no'; action='prioritize shelves using current demand'; facts=trends
    elif kind=='regulation_change':
        item=digest_item(category,p.get('top_item_id')) or {}; title=item.get('title','the new compliance item'); src=item.get('source','the supplied category digest'); deadline=p.get('deadline_iso','the supplied deadline')
        body=f"{mname}, compliance update: {title}. Deadline: {deadline}. Source: {src}. I can turn the requirement into a short checklist for your clinic. Want me to draft it?"; cta='binary_yes_no'; action='convert the update into a compliance checklist'; facts=f"{title}; deadline {deadline}"
    elif kind=='supply_alert':
        batches=', '.join(p.get('affected_batches',[])); body=f"{mname}, supply alert: voluntary recall for {p.get('molecule','the supplied molecule')} batches {batches} from {p.get('manufacturer','the supplied manufacturer')}. I would isolate the affected stock and prepare a customer notification using the supplied batch details. Want me to draft the notice?"; cta='binary_yes_no'; action='handle the supplied recall safely'; facts=f"batches {batches}, manufacturer {p.get('manufacturer')}"
    elif kind=='renewal_due':
        days=merchant.get('subscription',{}).get('days_remaining'); body=f"{mname}, your {merchant.get('subscription',{}).get('plan','current')} plan has {days} days remaining. Rather than sending a generic renewal pitch, I can summarize the strongest value signal from your current performance and offers first. Want that 3-point renewal brief?"; cta='binary_yes_no'; action='review renewal value'; facts=f"{days} days remaining"
    elif kind in {'dormant_with_vera'}:
        last=p.get('days_since_last_merchant_message') or p.get('placeholder') and None
        topic=p.get('last_topic')
        body=f"{mname}, it’s been {last} days since our last merchant conversation" if last else f"{mname}, we haven't had a recent working conversation"
        body += (f" about {topic.replace('_',' ')}." if topic else '.')+" I can pick up with one concrete improvement from your current profile. Want me to choose the highest-leverage one?"
        cta='binary_yes_no'; action='restart with one useful improvement'; facts=f"{last or 'no recent'} days since last touch"
    elif kind=='curious_ask_due':
        ask=p.get('ask_template') or 'what service is most in demand this week'
        body=f"Hi {mname}! Quick operator question: {ask.replace('_',' ')} at {merchant.get('identity',{}).get('name','your business')}? Give me the service name and I'll turn it into one usable post/reply."
        cta='open_ended'; action='get one merchant fact and return an artifact'; facts=ask
    elif kind=='festival_upcoming':
        fest=p.get('festival') or 'the upcoming festival'; days=p.get('days_until'); o=offer(merchant)
        body=f"{mname}, {fest} is {days} days away. I'd prepare early, but only with an offer you already have: {o['title'] if o else 'your existing service mix'}. Want me to draft one festival-ready message?"
        cta='binary_yes_no'; action='prepare a grounded seasonal asset'; facts=f"{fest}, {days} days"
    elif kind=='winback_eligible':
        body=f"{mname}, your subscription expired {p.get('days_since_expiry')} days ago, performance is down {pct(p.get('perf_dip_pct'))}, and {p.get('lapsed_customers_added_since_expiry')} lapsed customers were added since expiry. That makes a targeted winback more useful than a generic blast. Want me to draft it?"; cta='binary_yes_no'; action='run a targeted winback'; facts=f"expired {p.get('days_since_expiry')}d; perf {pct(p.get('perf_dip_pct'))}; {p.get('lapsed_customers_added_since_expiry')} lapsed customers"
    elif kind=='wedding_package_followup':
        body=f"Hi {cust or 'there'} 💍 {merchant.get('identity',{}).get('name','The salon')} here. Your wedding date is {p.get('wedding_date')}, and your bridal trial was {p.get('trial_completed')}. The 30-day skin-prep window is now open. Want me to block a first-session slot?"
        cta='binary_yes_no'; action='book the next bridal step'; facts=f"wedding {p.get('wedding_date')}; trial {p.get('trial_completed')}"
    elif kind in {'customer_lapsed_hard','customer_lapsed_soft','winback_eligible'} and customer_facing:
        days=p.get('days_since_last_visit')
        if cat=='gyms':
            goal=p.get('previous_focus') or customer.get('preferences',{}).get('training_focus'); o=offer(merchant)
            body=f"Hi {cust} 👋 {merchant.get('identity',{}).get('owner_first_name',mname)} from {merchant.get('identity',{}).get('name','the gym')} here. It’s been about {days or 'a while'} days — no judgment."
            if goal: body+=f" You were previously focused on {goal}."
            body+=f" We currently have {o['title'] if o else 'an active return option'}. Want me to hold a trial spot for you?"
        else:
            body=f"Hi {cust}, {merchant.get('identity',{}).get('name','the team')} here. We haven't seen you recently, and we'd be happy to help you come back when the timing suits you. Want me to share the simplest current option?"
        cta='binary_yes_no'; action='re-engage with a low-pressure next step'; facts=f"customer state {customer.get('state')}, days since visit {days}"
    elif kind=='recall_due' and customer_facing:
        consent=customer.get('consent',{}).get('scope',[])
        if 'recall_reminders' not in consent and 'appointment_reminders' not in consent:
            return {'body':'','cta':'none','send_as':send_as,'suppression_key':suppression,'rationale':'No permitted customer outreach scope for recall/appointment reminders.'}
        slots=p.get('available_slots',[]); o=offer(merchant)
        if slots:
            labels=[s.get('label') for s in slots[:2] if s.get('label')]
            if lang_style(customer,merchant)=='hi':
                body=f"Namaste {cust} — {merchant.get('identity',{}).get('name','clinic')} se. Aapka {p.get('service_due','recall').replace('_',' ')} due hai. {labels[0] if labels else ''} ya {labels[1] if len(labels)>1 else ''} available hain" + (f". {o['title']} bhi active hai." if o else '.') + " Reply YES and we’ll help with the slot."
            else:
                body=f"Hi {cust}, {merchant.get('identity',{}).get('name','the clinic')} here. Your {p.get('service_due','recall').replace('_',' ')} is due. We have {', '.join(labels)}" + (f". {o['title']} is also active." if o else '.') + " Reply YES and we’ll help confirm a slot."
        else:
            body=f"Hi {cust}, {merchant.get('identity',{}).get('name','the clinic')} here. Your {p.get('service_due','recall').replace('_',' ')} is due. Reply YES if you'd like us to help arrange the next visit."
        cta='binary_yes_no'; action='confirm a recall visit'; facts=f"due {p.get('due_date')}; slots {[s.get('label') for s in slots]}"
    elif kind=='appointment_tomorrow' and customer_facing:
        if not customer.get('preferences',{}).get('reminder_opt_in') and 'appointment_reminders' not in customer.get('consent',{}).get('scope',[]):
            return {'body':'','cta':'none','send_as':send_as,'suppression_key':suppression,'rationale':'Customer has no appointment-reminder consent in supplied context.'}
        body=f"Hi {cust}, reminder from {merchant.get('identity',{}).get('name','the team')}: your appointment is tomorrow. Reply YES to confirm, or NO if you need a change."
        cta='binary_yes_no'; action='confirm tomorrow appointment'; facts='appointment tomorrow'
    elif kind=='chronic_refill_due' and customer_facing:
        if 'refill_reminders' not in customer.get('consent',{}).get('scope',[]):
            return {'body':'','cta':'none','send_as':send_as,'suppression_key':suppression,'rationale':'Customer has no refill-reminder consent in supplied context.'}
        mol=', '.join(p.get('molecule_list',[])); run=parse_dt(p.get('stock_runs_out_iso')); date=run.strftime('%-d %B') if run else 'the supplied date';
        delivery=offer(merchant,('delivery',)); senior=offer(merchant,('senior',))
        sal='Namaste' if customer.get('identity',{}).get('senior_citizen') else 'Hi'
        via_son=' via your saved WhatsApp contact' if 'via_son' in customer.get('preferences',{}).get('channel','') else ''
        body=f"{sal} — {merchant.get('identity',{}).get('name','the pharmacy')} here{via_son}. Your monthly medicines ({mol}) are due to run out on {date}."
        if delivery: body+=f" {delivery['title']}"
        if senior: body+=f"; {senior['title']} applies where eligible."
        body+=" Reply YES if you want us to prepare the refill."
        cta='binary_yes_no'; action='confirm refill preparation'; facts=f"{mol}; run-out {date}"
    elif kind=='trial_followup' and customer_facing:
        o=offer(merchant)
        body=f"Hi {cust}, {merchant.get('identity',{}).get('name','the team')} here. Following up on your recent trial — {o['title'] if o else 'we can help with the next step'}. Want to continue?"
        cta='binary_yes_no'; action='continue after trial'; facts='trial follow-up'
    else:
        # Generic but still grounded fallback
        metric=p.get('metric_or_topic') or kind.replace('_',' ')
        o=offer(merchant)
        body=f"{mname}, this is about {metric}." + (f" You currently have {o['title']} active." if o else '') + " Want me to turn the supplied context into one concrete next step?"
        cta='binary_yes_no'; action='turn the trigger into one concrete next step'; facts=metric

    return {'body':body,'cta':cta,'send_as':send_as,'suppression_key':suppression,'rationale':rationale(kind,facts,action)}


def _norm(s): return re.sub(r'\s+',' ',(s or '').strip().lower())

STOP=['stop','unsubscribe','do not message','dont message','don’t message','not interested','no more']
AUTO=['thank you for contacting','thanks for contacting','our team will respond','we will get back to you','currently unavailable','please leave a message','office hours','thank you for reaching']
YES=['yes','sure','okay','ok','go ahead','do it','proceed','lets do it',"let's do it",'send it','start it','book it','confirm']
QUESTION=['?','how ','what ','when ','which ','can you','could you','why ']

def classify_reply(msg):
    t=_norm(msg)
    if any(x in t for x in STOP): return 'STOP'
    if any(x in t for x in AUTO): return 'AUTO_REPLY'
    if any(x in t for x in YES): return 'INTENT_TO_ACT'
    if any(x in t for x in QUESTION): return 'QUESTION'
    if t in {'no','nope','nah'}: return 'NO'
    return 'OTHER'

def respond(state:dict, message:str)->dict:
    intent=classify_reply(message); turns=state.setdefault('turns',[])
    if intent=='STOP': return {'action':'end','rationale':'Explicit stop/not-interested request; ending and suppressing further proactive outreach.'}
    if intent=='AUTO_REPLY':
        n=state.get('auto_reply_count',0)+1; state['auto_reply_count']=n
        if n>=3:return {'action':'end','rationale':'Repeated canned auto-reply detected; exiting after repeated non-human response.'}
        return {'action':'wait','wait_seconds':86400 if n>=2 else 1800,'rationale':'Canned auto-reply detected; backing off instead of treating it as merchant engagement.'}
    state['auto_reply_count']=0
    if intent=='INTENT_TO_ACT':
        state['committed']=True
        return {'action':'send','body':'Absolutely — I’ll move to the action you approved. If there’s one missing detail required to execute it, I’ll ask only for that next.','cta':'open_ended','rationale':'Merchant expressed commitment; transitioning from qualification to execution.'}
    if intent=='NO': return {'action':'end','rationale':'Merchant declined; ending without pressure.'}
    if intent=='QUESTION': return {'action':'send','body':'Yes — I’ll keep this focused on the same task. Tell me the specific part you want to clarify and I’ll answer from the context already supplied.','cta':'open_ended','rationale':'Answered/contained the question while keeping the conversation on-mission.'}
    return {'action':'send','body':'Got it. I’ll keep the next step focused and grounded in the details already available. What would you like to change?','cta':'open_ended','rationale':'Acknowledged the response and requested the smallest useful clarification.'}
