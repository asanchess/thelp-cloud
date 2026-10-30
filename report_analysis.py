"""Portable date, secret-redaction and evidence verification functions."""
import collections
import datetime as dt
import re
UTC=dt.timezone.utc
LOCAL=dt.timezone(dt.timedelta(hours=5),'Asia/Qyzylorda')

def day_bounds(day):
    start=dt.datetime.combine(day,dt.time(),LOCAL)
    return start.astimezone(UTC),(start+dt.timedelta(days=1)).astimezone(UTC)

def sanitized_rows(rows):
    out=[]
    for r in rows:
        text=r['text'] or ''
        text=re.sub(r'\b\d{7,12}:[A-Za-z0-9_-]{25,}\b','[REDACTED_BOT_TOKEN]',text)
        text=re.sub(r'\b(?:sk-|AIza)[A-Za-z0-9_-]{20,}\b','[REDACTED_API_KEY]',text)
        text=re.sub(r'\b[A-Fa-f0-9]{32,}\b','[REDACTED_LONG_HEX]',text)
        out.append({k:r[k] for k in ('chat_id','chat_title','message_id','timestamp','outgoing','reply_to_message_id')}|{'text':text})
    return out

def verify_content(result,rows):
    by={(r['chat_id'],r['message_id']):r for r in rows}
    sources=[];keys=set()
    for s in result['sources']:
        if not re.fullmatch('[A-Za-z0-9_-]+',s['key']) or s['key'] in keys:raise ValueError('Invalid evidence key')
        keys.add(s['key'])
        r=by.get((s['chat_id'],s['message_id']))
        if r is None or not s['quote'].strip() or s['quote'] not in r['text']:raise ValueError('Citation does not match source')
        chat_id=r['chat_id']
        url=f'https://t.me/c/{str(chat_id)[4:]}/{r["message_id"]}' if str(chat_id).startswith('-100') else None
        sources.append(s|{'title':r['chat_title'],'time':dt.datetime.fromisoformat(r['timestamp']).astimezone(LOCAL).strftime('%H:%M'),'url':url})
    grouped=collections.defaultdict(list)
    for r in rows:grouped[r['chat_id']].append(r)
    descriptions={c['chat_id']:c['summary'] for c in result['chat_summaries']}
    if len(descriptions)!=len(result['chat_summaries']) or set(descriptions)!=set(grouped):
        raise ValueError('Some chats have not been summarized')
    for item in result['highlights']+result['actions']:
        if not item['evidence'] or not set(item['evidence'])<=keys:raise ValueError('Unreferenced finding')
    chats=[{'title':items[0]['chat_title'],'count':len(items),'summary':descriptions[cid]} for cid,items in sorted(grouped.items(),key=lambda p:-len(p[1]))]
    if sum(c['count'] for c in chats)!=len(rows):raise ValueError('Coverage mismatch')
    return sources,chats
