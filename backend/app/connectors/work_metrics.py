"""Parse only work records returned by authenticated creator-list pages."""
import re
from datetime import datetime, timezone

ALIASES = {'views':('view_count','play_count','playCount','readCount'), 'likes':('like_count','digg_count','diggCount','likeCount','favCount'),
           'comments':('comment_count','commentCount'), 'shares':('share_count','shareCount','forwardCount')}


def extract_records(payload, platform):
    records = []
    def visit(value, depth=0):
        if depth > 12: return
        if isinstance(value, list):
            for item in value[:1000]: visit(item, depth+1)
        elif isinstance(value, dict):
            identifier = (value.get('aweme_id') or (value.get('id') if 'metrics' in value else None)) if platform == 'douyin' else value.get('objectId')
            if identifier is not None and not isinstance(identifier, (dict,list,bool)):
                stats = value.get('metrics') or value.get('statistics') or value.get('statistic') or value.get('stats') or value
                metrics = {}
                for key, aliases in ALIASES.items():
                    for alias in aliases:
                        number = stats.get(alias) if isinstance(stats, dict) else None
                        if isinstance(number, (int,float,str)) and not isinstance(number,bool) and re.fullmatch(r'\d+', str(number)):
                            metrics[key] = int(number); break
                desc = value.get('desc') or value.get('description') or value.get('title') or ''
                if isinstance(desc, dict): desc = desc.get('description') or ''
                timestamp = value.get('create_time') or value.get('createTime')
                if metrics:
                    records.append({'post_id':str(identifier), 'description':str(desc).strip(),
                                    'created_at':timestamp, '_priority':2 if 'metrics' in value else 1, **metrics})
                    return
            for child in value.values():
                if isinstance(child,(dict,list)): visit(child,depth+1)
    visit(payload)
    return records


def match_records(targets, records, complete):
    # Conflicting duplicates from different responses are not summed.
    by_id = {}
    for record in records:
        previous = by_id.get(record['post_id'])
        if not previous or record.get('_priority',0) >= previous.get('_priority',0):
            by_id[record['post_id']] = record
    items = {}
    for target in targets:
        if target.get('post_id'):
            candidates = [by_id[target['post_id']]] if target['post_id'] in by_id else []
        elif complete:
            expected = (target['title'] + ('\n' + target['description'] if target.get('description') else '')).strip()
            candidates = []
            claimed = {t['post_id'] for t in targets if t.get('post_id')}
            for record in by_id.values():
                if record['post_id'] in claimed: continue
                text = record['description']
                normalize = lambda text: re.sub(r'\s+', ' ', text).strip()
                if normalize(text) not in {normalize(target['title']), normalize(expected), normalize(target.get('description') or '')}: continue
                # Titles may be repeated by matrix/retry jobs. Match both text
                # and the publication time, never an arbitrary first result.
                try:
                    created = datetime.fromisoformat(target['created_at'])
                    if created.tzinfo is None: created = created.replace(tzinfo=timezone.utc)
                    timestamp = float(record['created_at'])
                    if timestamp > 10**12: timestamp /= 1000
                    delta = timestamp-created.timestamp()
                    if delta < -300 or delta > 86400: continue
                except (ValueError, TypeError, KeyError): continue
                candidates.append(record)
            # Two local jobs near the same timestamp cannot both claim a work.
            if len(candidates) == 1:
                other_targets = [t for t in targets if t['job_id'] != target['job_id'] and
                                 t['title'] == target['title'] and not t.get('post_id')]
                for other in other_targets:
                    other_expected = {normalize(other['title']), normalize(other.get('description') or ''), normalize(other['title']+'\n'+(other.get('description') or ''))}
                    if normalize(candidates[0]['description']) not in other_expected: continue
                    try:
                        other_time = datetime.fromisoformat(other['created_at'])
                        if other_time.tzinfo is None: other_time=other_time.replace(tzinfo=timezone.utc)
                        stamp=float(candidates[0]['created_at'])
                        if stamp>10**12:stamp/=1000
                        if -300 <= stamp-other_time.timestamp() <= 86400:
                            candidates=[];break
                    except (ValueError,TypeError,KeyError): candidates=[];break
        else:
            candidates = []
        if len(candidates) == 1: items[target['job_id']] = candidates[0]
    return items
