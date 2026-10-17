"""Local evidence and temporal gate; no network calls. Python 3.10+."""
import argparse, json
from calendar import monthrange
from datetime import datetime, timedelta
from urllib.parse import urlparse

def dt(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None: raise ValueError('timezone required')
    return result

def add_months(value, months):
    total = value.year * 12 + value.month - 1 + months
    year, month = divmod(total, 12)
    return value.replace(year=year, month=month + 1,
                         day=min(value.day, monthrange(year, month + 1)[1]))


def public_url(value):
    u = urlparse(value)
    return u.scheme == 'https' and bool(u.netloc) and not u.username and not u.password


def speaker_route_reasons(item):
    bad = []
    if item.get('speaker_route') not in ('speaker_page', 'external_talks'):
        bad.append('external speaker route unconfirmed')
    if not public_url(item.get('speaker_url', '')):
        bad.append('invalid speaker_url')
    if item.get('cfp_status', 'unknown') not in ('unknown', 'not_announced'):
        bad.append('closed CFP or open CFP card required')
    if item.get('program_final') is True:
        bad.append('program finalized')
    return bad


def reasons(item, now, days=30, months=6):
    bad=[]
    try:
        if not all(item.get(k) for k in ('name','topics','audience','format')): bad.append('missing relevance fields')
        for field in ('url','primary_url'):
            if not public_url(item.get(field,'')): bad.append('invalid '+field)
        if item.get('primary_verified') is not True: bad.append('unverified primary source')
        if item.get('accessible') is not True: bad.append('access unconfirmed')
        checked=dt(item['checked_at'])
        if checked > now or now-checked > timedelta(hours=24): bad.append('stale/future check')
        start=dt(item['starts_at'])
        if start <= now: bad.append('past or started event')
        evidence=item.get('evidence',{})
        keys=['date','status','language','community']
        if item.get('language') != 'ru': bad.append('Russian language unconfirmed')
        if item.get('russian_community') is not True: bad.append('Russian community unconfirmed')
        if item.get('kind') == 'event':
            keys.append('attendee_price')
            if item.get('free_for_attendee') is not True: bad.append('attendee price unconfirmed or paid')
            if start > now+timedelta(days=days): bad.append('outside window')
            if item.get('registration') not in ('open','not-required','not_required'): bad.append('registration unavailable')
        elif item.get('kind') in ('cfp', 'speaker', 'speaker_inquiry'):
            keys.append('section')
            if item.get('program_final') is True or item.get('external_talks') is False:
                bad.append('no available external talks')
            inquiry = item.get('kind') == 'speaker_inquiry'
            price = item.get('free_for_speaker')
            if inquiry:
                if price is not None and type(price) is not bool: bad.append('invalid speaker price status')
                if price is False: bad.append('speaker fee required')
                if price is True: keys.append('speaker_price')
            else:
                keys.append('speaker_price')
                if price is not True: bad.append('speaker price unconfirmed or paid')
            attendee = item.get('free_for_attendee')
            if attendee is not None and type(attendee) is not bool:
                bad.append('invalid attendee price status')
            if type(attendee) is bool: keys.append('attendee_price')
            if start > add_months(now, months): bad.append('outside speaker window')
            if item.get('kind') == 'cfp':
                keys.append('deadline')
                deadline=dt(item['deadline'])
                if item.get('cfp_status') != 'open' or deadline <= now: bad.append('CFP closed')
                if deadline >= start: bad.append('deadline not before conference')
            elif not inquiry:
                keys.append('speaker_route')
                bad.extend(speaker_route_reasons(item))
                if item.get('deadline') is not None:
                    deadline = dt(item['deadline'])
                    if deadline <= now or deadline >= start: bad.append('CFP closed or invalid deadline')
            else:
                keys.append('speaker_contact')
                if not public_url(item.get('organizer_contact_url', '')): bad.append('invalid organizer contact URL')
                status = item.get('cfp_status', 'unknown')
                if status not in ('unknown', 'not_announced', 'open'): bad.append('CFP closed')
                if item.get('deadline') is not None:
                    keys.append('deadline')
                    deadline = dt(item['deadline'])
                    if deadline <= now or deadline >= start: bad.append('CFP closed or invalid deadline')
                elif status == 'open': bad.append('open CFP needs deadline')
        else: bad.append('unknown kind')
        if not all(isinstance(evidence.get(k),str) and evidence[k].strip() for k in keys): bad.append('missing evidence')
    except (KeyError, ValueError, TypeError, AttributeError): bad.append('invalid or missing date/fields')
    return bad


def speaker_reasons(item, now, days=30, months=6):
    """Attendance eligibility alone must never create a speaking option."""
    bad = reasons(item, now, days, months)
    if item.get('kind') == 'event':
        opportunity = dict(item, kind='speaker')
        bad.extend(reasons(opportunity, now, days, months))
    return list(dict.fromkeys(bad))

def main():
    p=argparse.ArgumentParser();p.add_argument('file');p.add_argument('--now',required=True);p.add_argument('--days',type=int,default=30);p.add_argument('--months',type=int,default=6);a=p.parse_args()
    now=dt(a.now)
    if a.days < 1: p.error('--days must be positive')
    if not 1 <= a.months <= 24: p.error('--months must be between 1 and 24')
    items=json.load(open(a.file,encoding='utf-8'))
    if not isinstance(items,list): p.error('expected JSON array')
    accepted=[];rejected=[];seen=set()
    for item in items:
        if not isinstance(item,dict): rejected.append({'name':None,'reasons':['not an object']});continue
        why=reasons(item,now,a.days,a.months)
        key=(item.get('kind'),item.get('name','').casefold(),item.get('starts_at'))
        if key in seen: why.append('duplicate')
        if why: rejected.append({'name':item.get('name'),'reasons':why})
        else: accepted.append(item);seen.add(key)
    print(json.dumps({'accepted':accepted,'rejected':rejected},ensure_ascii=False,indent=2))
if __name__ == '__main__': main()
