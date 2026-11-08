"""Grounded unresolved-ending detection and 20-60 second promo window assembly."""
from __future__ import annotations
import re
from collections import Counter
from .core import all_events, episode_bounds, evidence, seconds, timestamp

MIN_LENGTH, MAX_LENGTH = 20.0, 60.0

def cut_after(t, events, max_delay=.8):
    """Prefer a shot boundary following completed dialogue without drifting."""
    cuts = [e['t0'] for e in events if e['type'] == 'camera' and t - .04 <= e['t0'] <= t + max_delay]
    return min(cuts) if cuts else round(t, 2)

def proposed_cliff(e,events):
    s=e.get('content','').lower()
    end=e['t1']
    if e['type']=='dialogue':
        if re.search(r'accept my hand|marry me|will you marry|be my wife',s):
            return 'unanswered_proposal',98,'Will the marriage proposal be accepted?',cut_after(end,events)
        if re.search(r'under arrest|sentenced? to (?:death|hang)|hang\w* from the gallows|will (?:hang|die|burn)|execution|kill (?:him|her)|she is a witch|you.re (?:a|the) poisoner|take her to (?:the )?dungeon|death warrant',s):
            return 'life_or_freedom_at_risk',97,'Can the threatened character escape the consequence?',cut_after(end,events)
        if re.search(r'will not marry|marriage (?:is|was) (?:invalid|void)|not legally married|not your wife|you cannot (?:marry|be|inherit)|lose her twice|ten days.*(?:lose|marriage|witness|council)',s):
            return 'relationship_or_status_at_risk',95,'Can the couple protect their marriage and position?',cut_after(end,events)
        if re.search(r'seize her|arrest him|arrest her|guards!|remove her|take her away|put out your hands|bring her in|let her go|stand aside',s):
            return 'arrest_or_conflict_pending',92,'Will someone stop the order from being carried out?',cut_after(end,events)
        if re.search(r'please! someone|somebody help|help me|save me|let me go|i can.t breathe|you have to help',s):
            return 'desperate_plea',90,'Will help reach the person in time?',cut_after(end,events)
        if re.search(r'he is your duke|the true duke|you.re the duke|you are my son|you cannot be him|he is alive|this is (?:your|my) son|the rightful duke|the crown.*proof|evidence of (?:treason|poisoning)|everyone believes you are dead|people believe you are dead',s):
            return 'identity_revelation_pending',89,'How will those exposed react to the revelation?',cut_after(end,events)
        if re.search(r'poison\w*|arsenic|witchcraft|treason|i found|the culprit|you stole|it was you|you planted|you were told|betrayed',s):
            return 'accusation_or_reveal',85,'What happens after this startling accusation or revelation?',cut_after(end,events)
        if re.search(r'you will (?:regret|pay)|i will (?:destroy|return|take back|come for)|i am (?:taking|bringing)|you have (?:ten|two|three) days|i intend|no one will|make sure no one',s):
            return 'future_threat_or_plan',80,'Will the promised plan or retaliation succeed?',cut_after(end,events)
        if '?' in s:
            # Do not make every question a cliffhanger: the spoken line itself
            # must establish the stakes, without relying on outside backstory.
            question_stakes = r'\b(?:die|kill|arrest|gallows|poison|marry|wedding|husband|wife|duke|duchess|daughter|father|son|treason|betray|save|rescue|witch|alive|dead|murder|prison|execution|burn|threat|inherit|steal|stole)\b'
            if re.search(question_stakes,s):
                return 'unanswered_high_stakes_question',76,'A consequential question is left unanswered.',cut_after(end,events)
            return None
        if re.search(r'discarded daughter|you leave|not anymore|it isn.t you|you are nothing|you have no right|leave this house',s):
            return 'rejection_or_ultimatum',72,'Will the rejected character fight back?',cut_after(end,events)
    elif e['type']=='action':
        if re.search(r'guards? .*grab|drag\w*|forcefully|forcibly|struggl\w*.*guards|restrain|handcuff|seiz\w*|bound|shackl\w*',s):
            return 'danger_unresolved',89,'Will the character escape captivity or harm?',cut_after(end,events)
        if re.search(r'fire.*spread|flames.*(?:door|inside|around)|smoke.*(?:fill|pour)|trapped|explosion|blast|crash.*door',s):
            return 'immediate_physical_danger',95,'Will the character survive the immediate danger?',cut_after(end,events)
        if re.search(r'overhear|eavesdrop|witness|sees? .*embrace|discover|stunned .*revelation|shocked.*(?:sight|secret)|opens? (?:the|a) door',s):
            return 'secret_discovered',91,'What will the unexpected witness do with the secret?',cut_after(end,events)
        if re.search(r'(?:reach\w* into|slip\w* into).*pocket|unseal|reveals? a sealed|hold\w*.*(?:letter|document)|hidden passage|unlock\w*.*door',s):
            return 'mystery_reveal_pending',77,'What will the concealed evidence or opening reveal?',cut_after(end,events)
        if re.search(r'(?:one knee|kneel\w*).*?(?:ring|propos)|offer\w*.*ring',s):
            return 'unexpected_proposal_pending',87,'Will the unexpected proposal be accepted?',cut_after(end,events)
    return None

def detect_cliffhangers(ep):
    events = all_events(ep)
    lo, hi = episode_bounds(ep)
    options = []
    for e in events:
        result = proposed_cliff(e, events)
        if result:
            kind, score, question, end = result
            # A real unresolved end must have some continuation or response still to come.
            if end < lo or end > hi:
                continue
            options.append({'end_seconds': round(end, 2), 'end': timestamp(end),
                            'cliffhanger_type': kind, 'cliffhanger_score': score,
                            'cliffhanger': question, 'evidence': evidence(e)})
        # An edit before a burst of violence creates an unresolved imminent confrontation,
        # but only if threat/guard confrontation immediately precedes it.
        if e['type'] == 'action' and re.search(r'blocks? .*strike|drives? .*strike|slap|shoot|attacks?|punch|swings? (?:his|her|the) (?:sword|fist)|brandishes?', e.get('content', ''), re.I):
            earlier = [x for x in events if 0 <= e['t0'] - x['t1'] <= 10 and
                       re.search(r'guard|let her go|stand aside|threat|stop|attack', x.get('content', ''), re.I)]
            if earlier:
                t = e['t0']
                options.append({'end_seconds': t, 'end': timestamp(t),
                                'cliffhanger_type': 'imminent_attack', 'cliffhanger_score': 96,
                                'cliffhanger': 'Will the armed confrontation turn into a fight?',
                                'evidence': evidence(e)})
    # Preserve a tense scene break (before a new scene's reveal), only if its
    # concluding action shows danger, distress or conflict.
    for scene in ep['scenes'][:-1]:
        end = seconds(scene['end'])
        tail = [x for x in events if x['t0'] <= end and x['t1'] >= end - 4.0 and x['type'] in {'dialogue', 'action'}]
        # A plea/tears are not imminent rescue danger. Require physical action.
        tense = [x for x in tail if x['type']=='action' and re.search(
            r'\b(?:guard.*(?:drag|grab|seiz|haul)|drag\w*|grab\w*|attack\w*|strik\w*|punch\w*|flames|smoke.*(?:fill|pour)|fire|shoot\w*|stab\w*|explos\w*|chok\w*|handcuff\w*|shackl\w*|restrain\w*)\b', x.get('content', ''), re.I)]
        if tense:
            options.append({'end_seconds': end, 'end': timestamp(end),
                            'cliffhanger_type': 'danger_at_scene_break', 'cliffhanger_score': 94,
                            'cliffhanger': 'Who will rescue the character from immediate danger?',
                            'evidence': evidence(tense[-1])})
    # Episode-final cuts are especially valuable when the last moments explicitly
    # leave danger, deception or the protagonist's future unresolved. Do not count
    # gentle romantic closure or ordinary "cut to black" as a cliff by itself.
    final_events=[e for e in events if e['t1']>=hi-10 and e['type'] in {'dialogue','action'}]
    ending_text=' '.join(e.get('content','') for e in final_events[-6:]).lower()
    danger_patterns=(r'\b(?:arrest|hang|death|die|kill|poison|witch|gallows|attack|flames|fire|gun|blood|guards|court|dungeon|imposter|impostor|conspir|betray|secret|witness|scandal|blackmail|threat|discover|expos|no one sees|priest|explosion|stranger|execute|ten days|take back|wife home|going somewhere|did not know|shocked|stifles a cry|cannot marry|unlawful|invalid)\b')
    if final_events and re.search(danger_patterns,ending_text,re.I):
        evidence_event=final_events[-1]
        # Give priority to the most recent dramatic evidence rather than camera fade.
        for candidate in reversed(final_events):
            if re.search(danger_patterns,candidate.get('content',''),re.I):
                evidence_event=candidate
                break
        options.append({'end_seconds':round(hi,2),'end':timestamp(hi),
                        'cliffhanger_type':'episode_end_open_loop','cliffhanger_score':84,
                        'cliffhanger':'The episode ends while the danger, deception, or announced plan remains unresolved.',
                        'evidence':evidence(evidence_event)})
    # Deduplicate endpoints within 0.3 seconds in favor of stronger evidence.
    options.sort(key=lambda c: (-c['cliffhanger_score'], c['end_seconds']))
    selected = []
    for c in options:
        if all(abs(c['end_seconds'] - x['end_seconds']) > .30 for x in selected):
            selected.append(c)
    return sorted(selected, key=lambda x: x['end_seconds'])

def cut_has_partial_dialogue(events, start, end):
    # The start/end of an EDIT must not cut speech mid-line (tiny tolerance for annotations).
    starts = [e for e in events if e['type'] == 'dialogue' and e['t0'] < start - .055 and e['t1'] > start + .12]
    ends = [e for e in events if e['type'] == 'dialogue' and e['t0'] < end - .12 and e['t1'] > end + .055]
    return starts, ends

def context_metrics(events,start,end,hook):
    """Transparent, non-trained proxies; no claim to predict actual engagement."""
    segment=[e for e in events if e['t0'] < end and e['t1']>start and e['type'] in {'dialogue','action'}]
    first=[e for e in segment if e['t0']<=start+7]
    text=' '.join(e.get('content','') for e in segment).lower()
    opening=' '.join(e.get('content','') for e in first).lower()
    themes=[
       r'wedding|wife|husband|marry|ring|propos|bride|love|priest|divorc',
       r'guard|seiz|grab|drag|rescu|strik|figh|thug|prison|arrest|shackl',
       r'family|father|mother|sister|son|daughter|lord|heir|duke|duchess',
       r'witch|poison|arsenic|herb|remedy|ill|cure|fever|blood|sick',
       r'court|crown|king|treason|document|proof|evidence|title|estate|decree',
       r'secret|lying|lie|betray|stole|steal|planted|conspir|fraud|hid|disguis',
       r'fire|burn|explos|death|die|dying|gallows|threat|endang|scream|cry',
       r'humiliat|disown|worthless|abandon|disgrace|scandal|kiss|intimate|affair',
    ]
    story=sum(bool(re.search(q,text,re.I)) for q in themes)
    obvious=bool(re.search(r'guard|drag|grab|strik|blood|burn|fire|die|dying|poison|wedding|stole|arrest|gallows|your grace|duke|marry|ring|prison|scandal|betray',opening,re.I))
    statements=sum(e['type']=='dialogue' for e in segment)
    actions=sum(e['type']=='action' for e in segment)
    unique_speakers=len({e.get('label','').split('(')[0].strip() for e in segment if e['type']=='dialogue'})
    fragment=bool(re.match(r'^\s*["“]?(?:\.\.\.|and |because |but |or |i said|not anymore)',hook.get('reason',''),re.I))
    clarity=49+6*story+(9 if obvious else 0)+min(8,statements/3)+(3 if unique_speakers>1 else 0)-(18 if fragment else 0)
    if statements<=1:clarity-=12
    if not first:clarity-=15
    arc=47+5*story+min(13,statements)+min(10,actions*2)
    if story<2:arc-=9
    return int(max(20,min(100,clarity))),int(max(20,min(100,arc))),segment

def grounded_why(hook,cliff):
    raw=hook['reason'].strip().strip('"“”')
    raw=' '.join(raw.split())
    if len(raw)>103: raw=raw[:99].rsplit(' ',1)[0]+'…'
    evidence=cliff['evidence']['content'].strip().strip('"“”')
    evidence=' '.join(evidence.split())
    if len(evidence)>85: evidence=evidence[:81].rsplit(' ',1)[0]+'…'
    if cliff['cliffhanger_type']=='imminent_attack':
        return f'Opens on “{raw}”; the cut comes just before an imminent attack, withholding the outcome.'
    return f'Opens on “{raw}” and cuts around “{evidence}”, leaving the next consequence unresolved.'

def assemble_promos(ep, hooks, top_pool=100):
    events = all_events(ep)
    endings = detect_cliffhangers(ep)
    candidates, stats = [], Counter()
    for hook in hooks:
        start = hook['start_seconds']
        for cliff in endings:
            end = cliff['end_seconds']
            duration = round(end - start, 2)
            if not MIN_LENGTH <= duration <= MAX_LENGTH:
                stats['duration_outside_20_60'] += 1
                continue
            previous, trailing = cut_has_partial_dialogue(events, start, end)
            if previous or trailing:
                stats['partial_dialogue_cut'] += 1
                continue
            # Reject if proposed endpoint appears before the cliff's evidence, except an
            # intentional before-impact cut, for which the danger must be visible already.
            if cliff['cliffhanger_type'] != 'imminent_attack' and seconds(cliff['evidence']['start']) >= end + .02:
                stats['unsupported_cliff'] += 1
                continue
            clarity, arc, selected_events = context_metrics(events, start, end, hook)
            if len(selected_events) < 5:
                stats['insufficient_context'] += 1
                continue
            # Penalize overly short windows and unclear start context.
            duration_score = max(58, 100 - abs(duration - 42) * 1.3)
            raw = (.30 * hook['hook_score'] + .31 * cliff['cliffhanger_score'] +
                   .23 * clarity + .11 * arc + .05 * duration_score)
            flags = []
            if clarity < 74:
                flags.append('May require backstory to understand without watching the show')
            if hook['source_event']['type'] == 'camera':
                flags.append('Hook is based on a shot description; confirm in rendered footage')
            if cliff['cliffhanger_type'] in {'unanswered_question', 'rejection_or_ultimatum'}:
                flags.append('Ending may be too mild to force a next-episode click')
            flags.append('Timecodes are script annotations; verify against final picture and audio')
            # The rare violence-to-romantic-commitment reversal is a strong
            # narrative turn, rather than a generic impact-only promo.
            reversal = 3.8 if (hook['hook_type']=='physical_attack' and
                               cliff['cliffhanger_type']=='unanswered_proposal') else 0
            score = round(max(0, min(100, raw + reversal - (5 if clarity < 70 else 0))), 1)
            end_location = [e for e in selected_events if e['t1'] >= end - 5]
            episodes_scenes = sorted({e['scene_id'] for e in selected_events})
            candidates.append({'id': f"P-{ep['_episode_id']}-{int(round(start*100)):06d}-{int(round(end*100)):06d}",
                'segments': [{'episode': ep['_episode_id'], 'start': timestamp(start),
                              'end': timestamp(end), 'start_seconds': start,
                              'end_seconds': end, 'duration_seconds': duration}],
                'duration_seconds': duration, 'scene_ids': episodes_scenes,
                'hook': {'text': hook['reason'], 'type': hook['hook_type'],
                         'score': hook['hook_score'], 'source': hook['source_event'],
                         'occurs_within_first_seconds': round(max(0.0, seconds(hook['source_event']['start'])-start), 2)},
                'cliffhanger': {'text': cliff['cliffhanger'], 'type': cliff['cliffhanger_type'],
                                'score': cliff['cliffhanger_score'], 'source': cliff['evidence']},
                'scores': {'overall': score, 'hook': hook['hook_score'], 'cliffhanger': cliff['cliffhanger_score'],
                           'standalone_clarity_proxy': clarity, 'narrative_arc_proxy': arc,
                           'duration': round(duration_score, 1)},
                'why_it_works': grounded_why(hook,cliff),
                'evidence_at_end': [evidence(e) for e in end_location[-3:]],
                'quality_flags': flags})
            stats['valid_windows'] += 1
    candidates.sort(key=lambda c: (-c['scores']['overall'], -c['scores']['standalone_clarity_proxy'], c['segments'][0]['start_seconds']))
    return candidates[:top_pool], dict(stats), endings

def interval_iou(a, b):
    aa, bb = a['segments'][0], b['segments'][0]
    if aa['episode'] != bb['episode']:
        return 0
    x = max(0, min(aa['end_seconds'], bb['end_seconds']) - max(aa['start_seconds'], bb['start_seconds']))
    union = max(aa['end_seconds'], bb['end_seconds']) - min(aa['start_seconds'], bb['start_seconds'])
    return x / union if union else 0

def choose_diverse(candidates, n=4):
    """Avoid showing many frame-shifted versions of the same story beat."""
    selected = []
    for c in candidates:
        if any(interval_iou(c, x) >= .50 or
               (c['segments'][0]['episode'] == x['segments'][0]['episode'] and
                abs(c['segments'][0]['end_seconds'] - x['segments'][0]['end_seconds']) < 1.5 and
                abs(c['segments'][0]['start_seconds'] - x['segments'][0]['start_seconds']) < 15)
               for x in selected):
            continue
        selected.append(c)
        if len(selected) >= n:
            break
    for i, c in enumerate(selected, 1):
        c['rank'] = i
        c['editorial_status'] = 'provisional_review_required'
    return selected
