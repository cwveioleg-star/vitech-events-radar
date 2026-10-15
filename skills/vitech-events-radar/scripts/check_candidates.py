"""Local evidence and temporal gate; no network calls. Python 3.10+."""
import argparse, json
from datetime import datetime, timedelta
from urllib.parse import urlparse

def dt(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None: raise ValueError('timezone required')
    return result

def reasons(item, now, days=30):
    bad=[]
    try:
        if not all(item.get(k) for k in ('name','topics','audience','format')): bad.append('missing relevance fields')
        for field in ('url','primary_url'):
            u=urlparse(item.get(field,''))
            if u.scheme != 'https' or not u.netloc or u.username or u.password: bad.append('invalid '+field)
        if item.get('primary_verified') is not True: bad.append('unverified primary source')
        if item.get('accessible') is not True: bad.append('access unconfirmed')
        checked=dt(item['checked_at'])
        if checked > now or now-checked > timedelta(hours=24): bad.append('stale/future check')
        start=dt(item['starts_at'])
        if start <= now: bad.append('past or started event')
        evidence=item.get('evidence',{})
        keys=['date','status','price','language','community']
        if item.get('free') is not True: bad.append('free unconfirmed')
        if item.get('language') != 'ru': bad.append('Russian language unconfirmed')
        if item.get('russian_community') is not True: bad.append('Russian community unconfirmed')
        if item.get('kind') == 'event':
            if start > now+timedelta(days=days): bad.append('outside window')
            if item.get('registration') not in ('open','not-required','not_required'): bad.append('registration unavailable')
        elif item.get('kind') == 'cfp':
            keys.append('deadline')
            deadline=dt(item['deadline'])
            if item.get('cfp_status') != 'open' or deadline <= now: bad.append('CFP closed')
            if deadline >= start: bad.append('deadline not before conference')
        else: bad.append('unknown kind')
        if not all(isinstance(evidence.get(k),str) and evidence[k].strip() for k in keys): bad.append('missing evidence')
    except (KeyError, ValueError, TypeError, AttributeError): bad.append('invalid or missing date/fields')
    return bad

def main():
    p=argparse.ArgumentParser();p.add_argument('file');p.add_argument('--now',required=True);p.add_argument('--days',type=int,default=30);a=p.parse_args()
    now=dt(a.now)
    if a.days < 1: p.error('--days must be positive')
    items=json.load(open(a.file,encoding='utf-8'))
    if not isinstance(items,list): p.error('expected JSON array')
    accepted=[];rejected=[];seen=set()
    for item in items:
        if not isinstance(item,dict): rejected.append({'name':None,'reasons':['not an object']});continue
        why=reasons(item,now,a.days)
        key=(item.get('kind'),item.get('name','').casefold(),item.get('starts_at'))
        if key in seen: why.append('duplicate')
        if why: rejected.append({'name':item.get('name'),'reasons':why})
        else: accepted.append(item);seen.add(key)
    print(json.dumps({'accepted':accepted,'rejected':rejected},ensure_ascii=False,indent=2))
if __name__ == '__main__': main()
