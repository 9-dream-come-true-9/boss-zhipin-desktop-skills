"""Fixed pywinauto/UIA runner for BOSS candidate messaging.

对外固定 4 个业务能力：
  能力一 根据上传文档回消息      parse-docs + open-next-unread + reply-current
  能力二 消息页批量发信息        batch-message
  能力三 推荐页批量打招呼        batch-greet
  能力四 给指定人发信息          send-to-contact
其余命令为内部实现命令，不作为对外功能颗粒度。"""

from __future__ import annotations
import argparse, hashlib, json, os, shutil, sys, time
from pathlib import Path

PID_TITLE="BOSS直聘"
INPUT_AIDS={"bosschat-global-input","boss-chat-editor-input"}

def fail(code, message, **extra):
    raise RuntimeError(json.dumps({"code":code,"message":message,**extra},ensure_ascii=False))

def deps():
    if os.name!="nt": fail("WINDOWS_REQUIRED","BOSS desktop automation requires Windows")
    try:
        from pywinauto import Desktop, keyboard
        from docx import Document
    except Exception as e: fail("RUNTIME_MISSING",str(e))
    return Desktop, keyboard, Document

def window(wait=True):
    Desktop,_,_=deps()
    for _ in range(12 if wait else 1):
        wins=[w for w in Desktop(backend="uia").windows(title=PID_TITLE,visible_only=True)]
        if len(wins)==1 and len(wins[0].descendants())>100: return wins[0]
        time.sleep(.5)
    fail("ACCESSIBILITY_UNAVAILABLE",f"expected one semantic BOSS window, got {len(wins)}")

def invoke(c):
    """Use UIA patterns first; fall back to element-relative click only, never coordinates."""
    try:
        c.iface_invoke.Invoke();return
    except Exception:pass
    try:
        c.invoke();return
    except Exception:pass
    try:
        c.click_input();return
    except Exception as exc:
        fail("SEMANTIC_ACTION_FAILED",f"could not activate {c.element_info.control_type}: {exc}")

def exact(w,typ,text,parent_type=None):
    xs=[]
    for c in w.descendants(control_type=typ):
        try:
            if c.is_visible() and c.window_text().strip()==text and (parent_type is None or c.parent().element_info.control_type==parent_type): xs.append(c)
        except Exception:pass
    if len(xs)!=1: fail("ELEMENT_NOT_UNIQUE",f"{typ} {text!r} count={len(xs)}")
    return xs[0]

def normalize(s): return s.replace("\r\n","\n").replace("\r","\n").strip()

def compact_job_text(value):
    """Normalize presentation-only separators without weakening semantic matching."""
    value=normalize(value).replace("＿","_")
    return "".join(value.split())

def job_base(value):
    """Return the job-name component before the UI's region/pay suffix."""
    value=normalize(value)
    if " _ " in value:return value.split(" _ ",1)[0].strip()
    if "_" in value:return value.split("_",1)[0].strip()
    return value

def visible_job_options(w):
    """Read currently exposed job categories from UIA ListItem children."""
    options=[]
    for c in w.descendants(control_type="Text"):
        try:
            if not c.is_visible() or c.parent().element_info.control_type!="ListItem":continue
            text=normalize(c.window_text())
            r=c.rectangle()
            if text and 350<r.left<1100 and r.top<900 and (text=="全部职位" or "_" in text):
                options.append(c)
        except Exception:pass
    # Deduplicate by RuntimeId/text while preserving controls.
    unique=[];seen=set()
    for c in options:
        try:key=(normalize(c.window_text()),tuple(c.element_info.element.GetRuntimeId()))
        except Exception:key=(normalize(c.window_text()),id(c))
        if key not in seen:seen.add(key);unique.append(c)
    return unique

def resolve_job_option(w, requested_job):
    """Resolve a caller job safely: full display text or a unique exact base name."""
    requested=normalize(requested_job);options=visible_job_options(w)
    if not options:fail("JOB_OPTIONS_UNAVAILABLE","job dropdown exposed no UIA category nodes")
    # 1) Exact display match, tolerant only to presentation whitespace around separators.
    full=[c for c in options if compact_job_text(c.window_text())==compact_job_text(requested)]
    if len(full)==1:return full[0]
    if len(full)>1:fail("JOB_NOT_UNIQUE",f"full job match count={len(full)}")
    # 2) Exact semantic base match. This is not substring/fuzzy matching.
    base=[c for c in options if compact_job_text(job_base(c.window_text()))==compact_job_text(requested)]
    if len(base)==1:return base[0]
    candidates=[normalize(c.window_text()) for c in (base if base else options)]
    if len(base)>1:fail("JOB_DISAMBIGUATION_REQUIRED","multiple categories share this job name",requested=requested,candidates=candidates)
    fail("JOB_NOT_FOUND","no exact display or unique base-name match",requested=requested,candidates=candidates)

def selected_job_anchor(w):
    anchors=[c for c in w.descendants(control_type="Text") if c.is_visible() and c.rectangle().top<180 and 350<c.rectangle().left<1100 and (normalize(c.window_text())=="全部职位" or "_" in normalize(c.window_text()))]
    if len(anchors)!=1:fail("JOB_NOT_EXACT",f"job anchor count={len(anchors)}")
    return anchors[0]

def default_send_ledger_path():
    """Persistent runtime state outside the Skill directory."""
    root=Path(os.environ.get("LOCALAPPDATA") or Path.home())/"CyberNüwa"/"boss-candidate-messaging"
    return root/"sent-ledger.jsonl"

def message_digest(message):
    return hashlib.sha256(normalize(message).encode("utf-8")).hexdigest()

def ledger_key(job,identity,message):
    return {"job":compact_job_text(job_base(job)),"identity":normalize(identity),"message_sha256":message_digest(message)}

def load_send_ledger(path=None):
    target=Path(path) if path else default_send_ledger_path()
    records=set()
    if not target.exists():return target,records
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            item=json.loads(line)
            records.add((item["job"],item["identity"],item["message_sha256"]))
        except Exception:continue
    return target,records

def ledger_contains(records,job,identity,message):
    key=ledger_key(job,identity,message)
    return (key["job"],key["identity"],key["message_sha256"]) in records

def append_send_ledger(path,records,job,identity,message,sent):
    key=ledger_key(job,identity,message)
    tuple_key=(key["job"],key["identity"],key["message_sha256"])
    if tuple_key in records:return False
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    record={**key,"sent_at":time.strftime("%Y-%m-%dT%H:%M:%S%z"),"message_container":sent.get("conversation_message_id","")}
    with target.open("a",encoding="utf-8") as handle:
        handle.write(json.dumps(record,ensure_ascii=False,separators=(",",":"))+"\n")
        handle.flush();os.fsync(handle.fileno())
    records.add(tuple_key)
    return True

def current_chat_exact_message(w,message):
    """Find an already existing exact message container in the loaded chat history.

    This backfills the ledger for messages sent before ledger support. We intentionally
    accept either bubble direction: an exact echo is safer to skip than to resend.
    """
    wanted=[normalize(x) for x in normalize(message).split("\n")]
    matches=[]
    for item in w.descendants(control_type="ListItem"):
        aid=str(item.element_info.automation_id)
        if not aid.startswith("mid-"):continue
        texts=[normalize(t.window_text()) for t in item.descendants(control_type="Text") if normalize(t.window_text()) and normalize(t.window_text()) not in {"送达","已读"}]
        # Ignore a leading timestamp exposed in the same container.
        candidates=[texts,texts[1:] if len(texts)>1 else []]
        if any(value==wanted or (wanted and all(q in value for q in wanted)) for value in candidates):
            matches.append({"conversation_message_id":aid,"texts":texts})
    return matches[0] if matches else None

def editor(w):
    xs=[c for c in w.descendants(control_type="Group") if c.is_visible() and c.element_info.automation_id in INPUT_AIDS]
    if len(xs)!=1: fail("EDITOR_NOT_UNIQUE",f"editor count={len(xs)}")
    return xs[0]

def activate_editor(w,g):
    w.set_focus()
    try:g.iface_legacyIAccessible.DoDefaultAction()
    except Exception:g.set_focus()
    time.sleep(.2)

def wait_editor(timeout=8):
    deadline=time.time()+timeout
    last_count=0
    while time.time()<deadline:
        current=window()
        matches=[c for c in current.descendants(control_type="Group") if c.is_visible() and c.element_info.automation_id in INPUT_AIDS]
        last_count=len(matches)
        if len(matches)==1:return current,matches[0]
        time.sleep(.25)
    fail("EDITOR_NOT_READY",f"editor did not become unique; last count={last_count}")

def candidate_identity(item):
    values=[]
    for image in item.descendants(control_type="Image"):
        value=normalize(image.window_text())
        if value:values.append(value)
    unique=list(dict.fromkeys(values))
    return unique[0] if len(unique)==1 else None

def wait_conversation_switch(identity, timeout=6):
    if not identity:return wait_editor(timeout)
    deadline=time.time()+timeout
    while time.time()<deadline:
        current=window()
        exact_nodes=[c for c in current.descendants() if c.is_visible() and normalize(c.window_text())==identity]
        editors=[c for c in current.descendants(control_type="Group") if c.is_visible() and c.element_info.automation_id in INPUT_AIDS]
        # One identity remains in the card; a second exact node proves the sidebar/chat switched.
        if len(exact_nodes)>=2 and len(editors)==1:return current,editors[0]
        time.sleep(.25)
    fail("CONVERSATION_NOT_READY","conversation identity/editor did not become ready")

def semantic_write_and_send(message):
    _,keyboard,_=deps(); w,g=wait_editor(); before={i.element_info.automation_id for i in w.descendants(control_type="ListItem") if str(i.element_info.automation_id).startswith("mid-")}
    activate_editor(w,g); keyboard.send_keys("^a{BACKSPACE}",pause=.02)
    lines=normalize(message).split("\n")
    for n,line in enumerate(lines):
        keyboard.send_keys(line,with_spaces=True,pause=.002)
        if n<len(lines)-1: keyboard.send_keys("+{ENTER}",pause=.03)
    time.sleep(.25); _,current_editor=wait_editor(); actual=normalize(current_editor.legacy_properties().get("Value",""))
    if actual!=normalize(message): fail("DRAFT_MISMATCH","full draft readback mismatch",expected=normalize(message),actual=actual)
    keyboard.send_keys("{ENTER}"); time.sleep(.4); w,g=wait_editor()
    if normalize(g.legacy_properties().get("Value","")): fail("SEND_VERIFICATION_FAILED","editor not cleared; do not retry")
    new=[]
    for item in w.descendants(control_type="ListItem"):
        aid=str(item.element_info.automation_id)
        if aid.startswith("mid-") and aid not in before:
            texts=[normalize(t.window_text()) for t in item.descendants(control_type="Text") if normalize(t.window_text()) and normalize(t.window_text())!="送达"]
            if texts:new.append({"conversation_message_id":aid,"texts":texts})
    wanted=[normalize(x) for x in lines]
    matches=[x for x in new if x["texts"]==wanted or all(q in x["texts"] for q in wanted)]
    if len(matches)!=1: fail("SEND_VERIFICATION_FAILED","one new message container was not verified; do not retry",new_containers=new)
    return matches[0]

def open_recommend_job(job):
    w=window(); nav=[c for c in w.descendants(control_type="Hyperlink") if c.is_visible() and normalize(c.window_text())=="推荐"]
    if len(nav)!=1: fail("ELEMENT_NOT_UNIQUE",f"recommend nav count={len(nav)}")
    invoke(nav[0]);time.sleep(1);w=window()
    headers=[c for c in w.descendants(control_type="Text") if c.is_visible() and " _ " in normalize(c.window_text()) and c.rectangle().top<180]
    if len(headers)!=1: fail("JOB_NOT_EXACT",f"current job anchor count={len(headers)}")
    if normalize(headers[0].window_text())==job:return w
    options=[c for c in w.descendants(control_type="Text") if c.is_visible() and normalize(c.window_text())==job and c.parent().element_info.control_type=="ListItem"]
    if not options:
        invoke(headers[0]);time.sleep(.5);w=window()
        options=[c for c in w.descendants(control_type="Text") if c.is_visible() and normalize(c.window_text())==job and c.parent().element_info.control_type=="ListItem"]
    if len(options)!=1:fail("JOB_NOT_EXACT",f"job option count={len(options)}")
    invoke(options[0]);time.sleep(1);w=window()
    selected=[c for c in w.descendants(control_type="Text") if c.is_visible() and c.rectangle().top<180 and normalize(c.window_text())==job]
    if len(selected)!=1:fail("JOB_NOT_EXACT","selected job readback mismatch")
    return w

def card_texts(item):
    return [normalize(t.window_text()) for t in item.descendants(control_type="Text") if normalize(t.window_text())]

def candidate_list(w):
    lists=[]
    for value in w.descendants(control_type="List"):
        try:
            children=value.children()
            if len(children)>=5 and all(x.element_info.control_type=="ListItem" for x in children):
                # Candidate lists contain action buttons; navigation/tab lists do not.
                if any(any(normalize(b.window_text()) in {"打招呼","继续沟通"} for b in item.descendants(control_type="Button")) for item in children):
                    lists.append(value)
        except Exception:pass
    if len(lists)!=1:fail("CANDIDATE_LIST_NOT_EXACT",f"candidate list count={len(lists)}")
    return lists[0]

def card_signature(item):
    return tuple(card_texts(item))

def occupies_window(control, w, min_width=20, min_height=20):
    """Return True only when a UIA control occupies the current BOSS viewport.

    BOSS keeps virtualised off-screen ListItems in the UIA tree with an empty
    rectangle.  ``is_visible()`` alone is therefore not sufficient evidence
    that an item can be clicked.
    """
    try:
        r=control.rectangle();wr=w.rectangle()
        visible_width=min(r.right,wr.right)-max(r.left,wr.left)
        visible_height=min(r.bottom,wr.bottom)-max(r.top,wr.top)
        return (r.width()>min_width and r.height()>min_height and
                visible_width>min_width and visible_height>min_height)
    except Exception:return False

def visible_candidate_cards(w):
    """Locate the recommendation list first, then return clickable visible cards."""
    listing=candidate_list(w)
    rows=[x for x in listing.children() if occupies_window(x,w)]
    rows.sort(key=lambda x:(x.rectangle().top,x.rectangle().left))
    return rows

def visible_message_rows(w):
    """Return only conversation rows currently occupying the left list viewport."""
    rows=[x for x in message_conversation_rows(w) if occupies_window(x["item"],w)]
    rows.sort(key=lambda x:(x["item"].rectangle().top,x["item"].rectangle().left))
    for row in rows:row["visible"]=True
    return rows

def viewport_signature(items, signature_fn):
    return tuple(signature_fn(x) for x in items)

def wheel_visible_list(w, items, signature_fn, *, direction, wheel_notches=5, wait_seconds=3.0, refresh_items):
    """Wheel over geometry derived from visible rows and verify viewport change.

    Five notches intentionally preserve overlap between adjacent viewports so
    traversal can detect omissions and avoid skipping candidates.
    """
    if not items:fail("CANDIDATE_LIST_VIEWPORT_NOT_FOUND","no visible candidate rows; cannot derive a safe scroll point")
    try:from pywinauto import mouse
    except Exception as exc:fail("RUNTIME_MISSING",str(exc))
    rects=[x["item"].rectangle() if isinstance(x,dict) else x.rectangle() for x in items]
    left=max(r.left for r in rects);right=min(r.right for r in rects)
    if right<=left:left=min(r.left for r in rects);right=max(r.right for r in rects)
    top=min(r.top for r in rects);bottom=max(r.bottom for r in rects)
    x=int((left+right)/2);y=int((top+bottom)/2)
    before=viewport_signature(items,signature_fn)
    dist=abs(wheel_notches) if direction=="up" else -abs(wheel_notches)
    mouse.scroll(coords=(x,y),wheel_dist=dist)
    deadline=time.time()+wait_seconds;latest=before
    while time.time()<deadline:
        time.sleep(.25);current=window();now=refresh_items(current);latest=viewport_signature(now,signature_fn)
        if latest and latest!=before:return {"advanced":True,"direction":direction,"viewport":latest}
    return {"advanced":False,"direction":direction,"reason":"viewport_unchanged","viewport":latest}

def seek_message_list_top(w, max_rounds=40):
    """Move to a verified top boundary before sweeping candidate conversations down."""
    moved=0;stable=0
    for _ in range(max_rounds):
        rows=visible_message_rows(w)
        result=wheel_visible_list(w,rows,lambda x:x["runtime_id"],direction="up",wheel_notches=7,wait_seconds=1.4,refresh_items=visible_message_rows)
        if result["advanced"]:moved+=1;stable=0;w=window()
        else:
            stable+=1
            if stable>=2:return {"moved_rounds":moved,"window":window()}
    fail("CANDIDATE_SEARCH_LIMIT_REACHED","message list top search reached safety limit",direction="up",max_rounds=max_rounds)

def advance_recommendation_page(w):
    """Advance the recommendation viewport with a real wheel event and overlap."""
    rows=visible_candidate_cards(w)
    return wheel_visible_list(w,rows,card_signature,direction="down",wheel_notches=5,wait_seconds=3.0,refresh_items=visible_candidate_cards)

def eligible_greet_target(w):
    """Find one eligible card by sweeping overlapping visible viewports."""
    seen_viewports=set()
    while True:
        current=tuple(card_signature(x) for x in visible_candidate_cards(w))
        if current in seen_viewports:return None
        seen_viewports.add(current)
        candidates=[]
        for item in visible_candidate_cards(w):
            try:
                buttons=[b for b in item.descendants(control_type="Button") if normalize(b.window_text())=="打招呼"]
                if len(buttons)==1:candidates.append((item,buttons[0],card_texts(item)))
            except Exception:pass
        visible=[x for x in candidates if x[0].is_visible() and x[1].is_visible()]
        if visible:return visible[0]
        page=advance_recommendation_page(w)
        if not page.get("advanced"):return None
        w=window()

def same_card_by_signature(w, signature):
    matches=[]
    for item in w.descendants(control_type="ListItem"):
        try:
            texts=card_texts(item)
            # The action label may change from 打招呼 to 继续沟通; compare stable card text only.
            stable=[x for x in texts if x not in {"打招呼","继续沟通"}]
            wanted=[x for x in signature if x not in {"打招呼","继续沟通"}]
            if stable==wanted:matches.append(item)
        except Exception:pass
    if len(matches)!=1:fail("CARD_NOT_EXACT",f"same candidate card count={len(matches)}")
    return matches[0]

def suppress_greet_notice(w):
    notices=[c for c in w.descendants(control_type="Text") if c.is_visible() and normalize(c.window_text())=="已向牛人发送招呼"]
    if not notices:return w
    checks=[c for c in w.descendants(control_type="CheckBox") if c.is_visible() and normalize(c.window_text())=="不再显示"]
    if len(checks)==1:
        try:
            if checks[0].get_toggle_state()==0:checks[0].iface_toggle.Toggle()
        except Exception:invoke(checks[0])
        time.sleep(.2);w=window()
    buttons=[c for c in w.descendants(control_type="Button") if c.is_visible() and normalize(c.window_text())=="知道了"]
    if len(buttons)==1:invoke(buttons[0]);time.sleep(.4);w=window()
    return w

def greet_next_prepared(message):
    """Process one eligible card on an already prepared recommendation page."""
    w=window();target=eligible_greet_target(w)
    if not target:fail("NO_ELIGIBLE_CANDIDATE","no semantic candidate card with one greet button")
    signature=target[2] if len(target)>2 else card_texts(target[0])
    identity=candidate_identity(target[0])
    invoke(target[1]);time.sleep(.35);w=suppress_greet_notice(window())
    card=same_card_by_signature(w,signature)
    buttons=[b for b in card.descendants(control_type="Button") if b.is_visible() and normalize(b.window_text())=="继续沟通"]
    if len(buttons)!=1:fail("ELEMENT_NOT_UNIQUE",f"continue button in same card count={len(buttons)}")
    invoke(buttons[0]);wait_conversation_switch(identity)
    sent=semantic_write_and_send(message)
    return {"status":"SENT_VERIFIED","message":sent}

def greet_one(job,message):
    open_recommend_job(job)
    return greet_next_prepared(message)

def batch_greet(job, message, limit=None, process_all=False):
    """Send caller-provided text to a bounded count or all currently discoverable eligible cards."""
    if process_all:
        ceiling=200
    else:
        if not isinstance(limit,int) or limit<1 or limit>50:fail("INVALID_LIMIT","limit must be 1-50 unless --all is used")
        ceiling=limit
    results=[]
    open_recommend_job(job)
    for sequence in range(1,ceiling+1):
        try:
            result=greet_next_prepared(message)
            results.append({"sequence":sequence,"status":"SENT_VERIFIED","message":result["message"]})
        except RuntimeError as exc:
            try:detail=json.loads(str(exc))
            except Exception:detail={"code":type(exc).__name__,"message":str(exc)}
            code=detail.get("code")
            if code=="NO_ELIGIBLE_CANDIDATE":
                return {"status":"COMPLETED_NO_MORE_ELIGIBLE","mode":"all" if process_all else "limit","requested":None if process_all else limit,"completed":len(results),"results":results}
            if code in {"DRAFT_MISMATCH","SEND_VERIFICATION_FAILED","ACCESSIBILITY_UNAVAILABLE","EDITOR_NOT_READY","CONVERSATION_NOT_READY"}:
                fail("BATCH_STOPPED_UNCERTAIN","batch stopped without retry",completed=results,error=detail)
            fail("BATCH_STOPPED","batch stopped",completed=results,error=detail)
    if process_all:fail("BATCH_SAFETY_CEILING","stopped at safety ceiling",completed=results)
    return {"status":"COMPLETED","mode":"limit","requested":limit,"completed":len(results),"results":results}

def conversation_cards(w):
    cards=[]
    for item in w.descendants(control_type="ListItem"):
        try:
            r=item.rectangle(); texts=[normalize(t.window_text()) for t in item.descendants(control_type="Text") if normalize(t.window_text())]
            if item.is_visible() and 400<=r.left<1200 and texts:
                cards.append({"item":item,"texts":texts})
        except Exception:pass
    return cards

def open_conversation_exact(contact_name, job, exact_latest_message):
    """Open one chat using exact visible identity and message evidence; never fuzzy match."""
    w=open_message_job(job)
    matches=[]
    for card in conversation_cards(w):
        if exact_latest_message in card["texts"]:
            matches.append(card["item"])
    if len(matches)!=1: fail("CONVERSATION_NOT_EXACT",f"conversation by exact message count={len(matches)}")
    # Chromium exposes neither InvokePattern nor SelectionItemPattern reliably for these rows.
    # click_input remains element-relative: the target is a verified UIA ListItem, not a coordinate.
    matches[0].click_input();time.sleep(1);w=window()
    names=[c for c in w.descendants(control_type="Text") if c.is_visible() and normalize(c.window_text())==contact_name]
    if len(names)!=1: fail("CONVERSATION_NOT_EXACT",f"contact title {contact_name!r} count={len(names)}")
    current_jobs=[c for c in w.descendants(control_type="Text") if c.is_visible() and normalize(c.window_text()) in {job,job.split(" _ ",1)[0]} and c.rectangle().left>1900]
    if not current_jobs: fail("CONVERSATION_CHANGED","current chat job mismatch")
    return w

def open_message_job(job):
    w=window(); nav=[c for c in w.descendants(control_type="Hyperlink") if c.is_visible() and normalize(c.window_text()).startswith("消息")]
    if len(nav)!=1: fail("ELEMENT_NOT_UNIQUE",f"message nav count={len(nav)}")
    invoke(nav[0]);time.sleep(1);w=window();anchor=selected_job_anchor(w)
    invoke(anchor);time.sleep(.4);w=window();option=resolve_job_option(w,job);selected=normalize(option.window_text());invoke(option);time.sleep(1);w=window()
    actual=normalize(selected_job_anchor(w).window_text())
    if compact_job_text(actual)!=compact_job_text(selected):fail("JOB_SELECTION_NOT_CONFIRMED",f"expected {selected!r}, got {actual!r}")
    return w

def prepare_message_job(job):
    """Open Message, select one exact job, and force the conversation scope to 全部."""
    w=open_message_job(job)
    all_tabs=[c for c in w.descendants(control_type="Text") if c.is_visible() and normalize(c.window_text())=="全部" and 260<c.rectangle().top<350]
    if len(all_tabs)!=1:fail("MESSAGE_SCOPE_NOT_EXACT",f"全部 scope count={len(all_tabs)}")
    invoke(all_tabs[0]);time.sleep(.5)
    return window()

def message_conversation_rows(w):
    rows=[]
    for item in w.descendants(control_type="ListItem"):
        try:
            r=item.rectangle();texts=[normalize(c.window_text()) for c in item.descendants(control_type="Text") if normalize(c.window_text())]
            # Candidate conversation rows belong to the left pane. Chat-history
            # ListItems begin near x=1198 and are much wider, so require the row
            # itself to end inside the left list boundary.
            if 400<=r.left<1200 and r.right<=1200 and 500<r.width()<1000 and r.height()>100 and texts:
                runtime_id=tuple(item.element_info.element.GetRuntimeId())
                rows.append({"item":item,"signature":tuple(texts),"runtime_id":runtime_id,"visible":item.is_visible()})
        except Exception:pass
    return rows

def current_chat_identity(w):
    """Read the chat title using window-relative geometry."""
    wr=w.rectangle(); rows=visible_message_rows(w)
    pane_right=max((x.rectangle().right for x in rows),default=wr.left+500)
    nodes=[]
    for c in w.descendants(control_type="Text"):
        try:
            r=c.rectangle(); value=normalize(c.window_text())
            if c.is_visible() and value and pane_right<r.left<wr.right-150 and wr.top<r.top<wr.top+105 and r.height()>=15:nodes.append(c)
        except Exception:pass
    if not nodes:fail("CHAT_IDENTITY_NOT_EXACT","chat title is absent")
    nodes=sorted(nodes,key=lambda c:(c.rectangle().top,c.rectangle().left));first_top=nodes[0].rectangle().top
    identity="".join(normalize(c.window_text()) for c in nodes if abs(c.rectangle().top-first_top)<=3)
    if not identity:fail("CHAT_IDENTITY_NOT_EXACT",f"chat title count={len(nodes)}")
    return identity

def current_chat_job(w, expected_job):
    short=expected_job.split(" _ ",1)[0]
    nodes=[c for c in w.descendants(control_type="Text") if c.is_visible() and c.rectangle().left>1900 and 250<c.rectangle().top<420 and normalize(c.window_text())==short]
    if len(nodes)!=1:fail("CONVERSATION_CHANGED",f"current chat job count={len(nodes)}")
    return short

def open_message_row(row, expected_job, timeout=7):
    row["item"].click_input();deadline=time.time()+timeout
    while time.time()<deadline:
        w=window()
        editors=[g for g in w.descendants(control_type="Group") if g.is_visible() and g.element_info.automation_id in INPUT_AIDS]
        if len(editors)==1:
            identity=current_chat_identity(w);current_chat_job(w,expected_job)
            return w,editors[0],identity
        time.sleep(.25)
    fail("CONVERSATION_NOT_READY","message row did not open a unique editor")

def advance_message_list(w, known_runtime_ids):
    """Advance the visible conversation list; never target an off-screen zero rectangle."""
    rows=visible_message_rows(w)
    result=wheel_visible_list(w,rows,lambda x:x["runtime_id"],direction="down",wheel_notches=5,wait_seconds=3.0,refresh_items=visible_message_rows)
    current=visible_message_rows(window())
    runtime_ids={x["runtime_id"] for x in current};result["known"]=set(known_runtime_ids)|runtime_ids
    result["new_rows"]=len(runtime_ids-set(known_runtime_ids))
    return result

def next_unprocessed_message_row(w, processed_identities, processed_runtime_ids, message):
    # Only return rows proven to occupy the current viewport. The caller scrolls
    # the list when this overlapping segment is exhausted.
    rows=visible_message_rows(w)
    pending=[x for x in rows if x["runtime_id"] not in processed_runtime_ids and normalize(message) not in x["signature"]]
    return pending[0] if pending else None

def send_message_current(expected_identity, expected_job, message):
    w=window()
    if current_chat_identity(w)!=expected_identity:fail("CONVERSATION_CHANGED","chat identity changed before send")
    current_chat_job(w,expected_job)
    return semantic_write_and_send(message)

def batch_message(job, message, limit=None, process_all=False):
    """Send one caller-provided message to existing conversations under an exact job."""
    if process_all:ceiling=500
    else:
        if not isinstance(limit,int) or limit<1 or limit>100:fail("INVALID_LIMIT","limit must be 1-100 unless --all is used")
        ceiling=limit
    w=prepare_message_job(job)
    # Locate the candidate conversation viewport and normalise to its top before
    # opening any row. This prevents a batch from silently starting mid-list.
    top=seek_message_list_top(w);w=top["window"]
    selected_job=normalize(selected_job_anchor(w).window_text());ledger_path,ledger_records=load_send_ledger();processed_identities=set();initial_rows=visible_message_rows(w);processed_runtime_ids=set();known={x["runtime_id"] for x in initial_rows};results=[];skipped_ledger=[]
    while len(results)<ceiling:
        w=window();row=next_unprocessed_message_row(w,processed_identities,processed_runtime_ids,message)
        if not row:
            page=advance_message_list(w,known)
            known=page.get("known",known)
            if not page.get("advanced"):
                return {"status":"COMPLETED_NO_MORE_CONVERSATIONS","mode":"all" if process_all else "limit","completed":len(results),"skipped_already_sent":len(skipped_ledger),"results":results}
            continue
        processed_runtime_ids.add(row["runtime_id"])
        try:
            w,g,identity=open_message_row(row,selected_job)
            if identity in processed_identities:continue
            # Cross-run duplicate prevention must be identity based. A candidate reply changes
            # the list preview, so preview text is never sufficient evidence of not-sent.
            if ledger_contains(ledger_records,selected_job,identity,message):
                processed_identities.add(identity);skipped_ledger.append(identity);continue
            historical=current_chat_exact_message(w,message)
            if historical:
                append_send_ledger(ledger_path,ledger_records,selected_job,identity,message,historical)
                processed_identities.add(identity);skipped_ledger.append(identity);continue
            sent=send_message_current(identity,selected_job,message)
            append_send_ledger(ledger_path,ledger_records,selected_job,identity,message,sent)
            processed_identities.add(identity)
            results.append({"sequence":len(results)+1,"status":"SENT_VERIFIED","message":sent})
        except RuntimeError as exc:
            try:detail=json.loads(str(exc))
            except Exception:detail={"code":type(exc).__name__,"message":str(exc)}
            if detail.get("code") in {"DRAFT_MISMATCH","SEND_VERIFICATION_FAILED","ACCESSIBILITY_UNAVAILABLE","EDITOR_NOT_READY","CONVERSATION_NOT_READY","CONVERSATION_CHANGED"}:
                fail("BATCH_MESSAGE_STOPPED_UNCERTAIN","message batch stopped without retry",completed=results,error=detail)
            fail("BATCH_MESSAGE_STOPPED","message batch stopped",completed=results,error=detail)
    if process_all:fail("BATCH_MESSAGE_SAFETY_CEILING","stopped at 500-conversation safety ceiling",completed=results)
    return {"status":"COMPLETED","mode":"limit","requested":limit,"completed":len(results),"skipped_already_sent":len(skipped_ledger),"results":results}

def open_next_unread(job):
    w=open_message_job(job);invoke(exact(w,"Text","未读"));time.sleep(.8);w=window()
    conversations=[]
    for item in w.descendants(control_type="ListItem"):
        try:
            r=item.rectangle(); texts=[normalize(t.window_text()) for t in item.descendants(control_type="Text") if normalize(t.window_text())]
            if item.is_visible() and r.left>=400 and r.right<=1300 and texts: conversations.append(item)
        except Exception:pass
    if not conversations: fail("NO_UNREAD","no unread conversation exposed")
    invoke(conversations[0]);time.sleep(.8);w=window();g=editor(w)
    msgs=[]
    for item in w.descendants(control_type="ListItem"):
        aid=str(item.element_info.automation_id)
        if aid.startswith("mid-"):
            texts=[normalize(t.window_text()) for t in item.descendants(control_type="Text") if normalize(t.window_text()) and normalize(t.window_text())!="送达"]
            if texts:msgs.append({"id":aid,"texts":texts})
    cid=str(g.parent().element_info.automation_id or g.rectangle())
    return {"conversation_id":cid,"messages":msgs,"latest_candidate_message":msgs[-1]["texts"] if msgs else []}

def reply_current(cid,text):
    w=window();g=editor(w);actual=str(g.parent().element_info.automation_id or g.rectangle())
    if actual!=cid: fail("CONVERSATION_CHANGED","current conversation changed")
    return {"status":"SENT_VERIFIED","message":semantic_write_and_send(text)}

def runtime_id_of(control):
    try:return tuple(control.element_info.element.GetRuntimeId())
    except Exception as exc:fail("RUNTIME_ID_UNAVAILABLE",str(exc))

def open_surface(surface):
    """Open one top-level business surface without selecting a job or starting a batch."""
    labels={"recommend":"推荐","message":"消息"}
    if surface not in labels:fail("INVALID_SURFACE",f"unsupported surface: {surface}")
    w=window();label=labels[surface]
    links=[c for c in w.descendants(control_type="Hyperlink") if c.is_visible() and (normalize(c.window_text())==label if surface=="recommend" else normalize(c.window_text()).startswith(label))]
    if len(links)!=1:fail("ELEMENT_NOT_UNIQUE",f"{surface} navigation count={len(links)}")
    invoke(links[0]);time.sleep(.5);return {"surface":surface,"status":"OPENED"}

def select_job(surface, job):
    """Select a full display job or a unique exact base name; no list item is opened."""
    if surface=="recommend":w=open_recommend_job(job);selected=job
    elif surface=="message":w=open_message_job(job);selected=normalize(selected_job_anchor(w).window_text())
    else:fail("INVALID_SURFACE",f"unsupported surface: {surface}")
    return {"surface":surface,"requested_job":job,"selected_job":selected,"status":"SELECTED","descendants":len(w.descendants())}

def list_candidate_cards():
    """Return currently loaded candidate cards as data, without greeting anyone."""
    w=window();records=[]
    for item in visible_candidate_cards(w):
        buttons=[normalize(b.window_text()) for b in item.descendants(control_type="Button") if normalize(b.window_text())]
        state="greet" if "打招呼" in buttons else "continue" if "继续沟通" in buttons else "other"
        records.append({"runtime_id":runtime_id_of(item),"state":state,"visible":item.is_visible(),"texts":card_texts(item)})
    return records

def find_runtime_item(runtime_id, source):
    expected=tuple(runtime_id)
    matches=[x for x in source if runtime_id_of(x)==expected]
    if len(matches)!=1:fail("RUNTIME_ITEM_NOT_EXACT",f"runtime item count={len(matches)}")
    return matches[0]

def open_candidate_card(runtime_id, suppress_notice=True):
    """Open one exact candidate card; sending text remains a separate capability."""
    w=window();item=find_runtime_item(runtime_id,visible_candidate_cards(w));signature=card_texts(item);identity=candidate_identity(item)
    buttons=[b for b in item.descendants(control_type="Button") if b.is_visible() and normalize(b.window_text()) in {"打招呼","继续沟通"}]
    if len(buttons)!=1:fail("ELEMENT_NOT_UNIQUE",f"candidate action count={len(buttons)}")
    action=normalize(buttons[0].window_text());invoke(buttons[0]);time.sleep(.35)
    w=window()
    if action=="打招呼" and suppress_notice:w=suppress_greet_notice(w)
    if action=="打招呼":
        item=same_card_by_signature(w,signature);continues=[b for b in item.descendants(control_type="Button") if b.is_visible() and normalize(b.window_text())=="继续沟通"]
        if len(continues)!=1:fail("ELEMENT_NOT_UNIQUE",f"continue button count={len(continues)}")
        invoke(continues[0])
    w,g=wait_conversation_switch(identity)
    return {"status":"OPENED","action":action,"identity":identity,"editor_id":g.element_info.automation_id}

def list_message_rows():
    """Return loaded message rows as data; no conversation is opened."""
    return [{"runtime_id":x["runtime_id"],"visible":True,"texts":list(x["signature"])} for x in visible_message_rows(window())]

def open_message_runtime(runtime_id, expected_job=None):
    """Open one loaded message row by RuntimeId; sending remains separate."""
    w=window();rows=visible_message_rows(w);matches=[x for x in rows if tuple(x["runtime_id"])==tuple(runtime_id)]
    if len(matches)!=1:fail("RUNTIME_ITEM_NOT_EXACT",f"message row count={len(matches)}")
    job=expected_job
    if not job:
        anchors=[c for c in w.descendants(control_type="Text") if c.is_visible() and c.rectangle().top<180 and " _ " in normalize(c.window_text())]
        if len(anchors)!=1:fail("JOB_NOT_EXACT",f"current message job count={len(anchors)}")
        job=normalize(anchors[0].window_text())
    w,g,identity=open_message_row(matches[0],job)
    return {"status":"OPENED","identity":identity,"job":job,"editor_id":g.element_info.automation_id}

def inspect_current_chat():
    """Read current chat identity, job and messages without sending."""
    w=window();identity=current_chat_identity(w)
    jobs=[normalize(c.window_text()) for c in w.descendants(control_type="Text") if c.is_visible() and c.rectangle().left>1900 and 250<c.rectangle().top<420 and normalize(c.window_text())]
    messages=[]
    for item in w.descendants(control_type="ListItem"):
        aid=str(item.element_info.automation_id)
        if aid.startswith("mid-"):
            texts=[normalize(t.window_text()) for t in item.descendants(control_type="Text") if normalize(t.window_text())]
            if texts:messages.append({"id":aid,"texts":texts})
    return {"identity":identity,"job_candidates":jobs,"messages":messages,"editor_id":editor(w).element_info.automation_id}

def send_current(message, expected_identity=None, expected_job=None):
    """Send text in the already-open chat, optionally guarded by identity/job."""
    w=window()
    if expected_identity and current_chat_identity(w)!=expected_identity:fail("CONVERSATION_CHANGED","chat identity mismatch")
    if expected_job:current_chat_job(w,expected_job)
    return semantic_write_and_send(message)

def advance_list(surface):
    """Advance one list segment only; no item is opened or messaged."""
    w=window()
    if surface=="recommend":return advance_recommendation_page(w)
    if surface=="message":
        known={x["runtime_id"] for x in message_conversation_rows(w)}
        return advance_message_list(w,known)
    fail("INVALID_SURFACE",f"unsupported surface: {surface}")

def open_contact_search(w=None):
    """Open message-page contact search without fixed screen coordinates."""

    if w is None:open_surface("message");w=window()
    wr=w.rectangle()
    existing=[e for e in w.descendants(control_type="Edit") if e.is_visible() and normalize(e.window_text())=="搜索姓名/群聊"]
    if len(existing)==1:return w,existing[0]
    if len(existing)>1:fail("CONTACT_SEARCH_NOT_UNIQUE",f"search edit count={len(existing)}")
    rows=visible_message_rows(w);pane_right=max((x.rectangle().right for x in rows),default=0)
    if not pane_right:
        editors=[c for c in w.descendants(control_type="Group") if c.is_visible() and c.element_info.automation_id in INPUT_AIDS]
        if len(editors)==1:pane_right=editors[0].rectangle().left-7
    anchors=[c for c in w.descendants(control_type="Text") if c.is_visible() and wr.top<c.rectangle().top<wr.top+100 and wr.left+120<c.rectangle().left<wr.left+520 and (normalize(c.window_text())=="全部职位" or "_" in normalize(c.window_text()))]
    if len(anchors)!=1:fail("CONTACT_SEARCH_ANCHOR_NOT_UNIQUE",f"job anchor count={len(anchors)}")
    if not pane_right:fail("CONTACT_LIST_UNAVAILABLE","no visible conversation rows for pane geometry")
    ar=anchors[0].rectangle();w.click_input(coords=(pane_right-31-wr.left,(ar.top+ar.bottom)//2-wr.top));time.sleep(.35)
    current=window();edits=[e for e in current.descendants(control_type="Edit") if e.is_visible() and normalize(e.window_text())=="搜索姓名/群聊"]
    if len(edits)!=1:fail("CONTACT_SEARCH_NOT_READY",f"search edit count={len(edits)}")
    return current,edits[0]

def open_contact_by_exact_name(contact_name,timeout=8):
    """Search one exact contact name and open its chat, with title verification."""
    requested=normalize(contact_name)
    if not requested:fail("CONTACT_NAME_REQUIRED","contact name is empty")
    _,keyboard,_=deps();w,search=open_contact_search();search.click_input();keyboard.send_keys("^a{BACKSPACE}",pause=.02);keyboard.send_keys(requested,with_spaces=True,pause=.02)
    deadline=time.time()+timeout;header=None
    while time.time()<deadline:
        current=window();docs=" ".join(normalize(c.window_text()) for c in current.descendants(control_type="Document"));headers=[c for c in current.descendants(control_type="Text") if c.is_visible() and normalize(c.window_text())=="联系人"]
        if requested in docs and headers:header=headers[0];w=current;break
        time.sleep(.25)
    if header is None:fail("CONTACT_NOT_FOUND","no contact result for exact name",contact=requested)
    wr=w.rectangle();sr=search.rectangle();hr=header.rectangle();w.click_input(coords=((sr.left+sr.right)//2-wr.left,hr.bottom+40-wr.top));time.sleep(.7)
    deadline=time.time()+timeout
    while time.time()<deadline:
        current=window();editors=[c for c in current.descendants(control_type="Group") if c.is_visible() and c.element_info.automation_id in INPUT_AIDS];title_nodes=[c for c in current.descendants(control_type="Text") if c.is_visible() and normalize(c.window_text())==requested]
        if len(editors)==1 and title_nodes:
            actual=current_chat_identity(current)
            if actual!=requested:fail("CONTACT_IDENTITY_MISMATCH","opened chat title differs",expected=requested,actual=actual)
            return {"status":"OPENED","identity":actual}
        time.sleep(.25)
    fail("CONTACT_CONVERSATION_NOT_READY","contact result did not open",contact=requested)

def send_message_to_contact(contact_name,message):
    """Exact-name search, verified open, then one verified send."""
    opened=open_contact_by_exact_name(contact_name);sent=semantic_write_and_send(message)
    return {"status":"SENT_VERIFIED","identity":opened["identity"],**sent}

def doc_text(path):
    _,_,Document=deps();d=Document(path);return [p.text.strip() for p in d.paragraphs if p.text.strip()]

def parse_runtime_id(value):
    try:
        data=json.loads(value)
        if not isinstance(data,list):raise ValueError("RuntimeId must be a JSON array")
        return tuple(int(x) for x in data)
    except Exception as exc:fail("INVALID_RUNTIME_ID",str(exc))

def main():
    p=argparse.ArgumentParser(description="BOSS candidate messaging runner: 4 business capabilities (按文档回消息 / 消息页批量发信息 / 推荐页批量打招呼 / 给指定人发信息) plus internal implementation commands.")
    subs=p.add_subparsers(dest="cmd",required=True)
    subs.add_parser("inspect",help="使用前检查：运行环境与 UIA 可读性")
    # 能力一：根据上传文档回消息（3 个步骤命令）
    d=subs.add_parser("parse-docs",help="能力一·步骤1：解析本次上传的问题/回答文档");d.add_argument("--question-docx",required=True);d.add_argument("--answer-docx",required=True)
    u=subs.add_parser("open-next-unread",help="能力一·步骤2：打开指定岗位的下一条未读会话");u.add_argument("--job",required=True)
    r=subs.add_parser("reply-current",help="能力一·步骤3：生成并发送有依据的回复");r.add_argument("--conversation-id",required=True);r.add_argument("--reply-file",required=True)
    # 能力二：批量在消息页面发信息
    m=subs.add_parser("batch-message",help="能力二：消息页面向已有会话批量发信息");m.add_argument("--job",required=True);m.add_argument("--message-file",required=True);mm=m.add_mutually_exclusive_group(required=True);mm.add_argument("--limit",type=int);mm.add_argument("--all",action="store_true",dest="process_all")
    # 能力三：批量在推荐页面打招呼
    b=subs.add_parser("batch-greet",help="能力三：推荐页面向未沟通候选人批量打招呼");b.add_argument("--job",required=True);b.add_argument("--message-file",required=True);mode=b.add_mutually_exclusive_group(required=True);mode.add_argument("--limit",type=int);mode.add_argument("--all",action="store_true",dest="process_all")
    # 能力四：给指定人发信息
    sn=subs.add_parser("send-to-contact",help="能力四：给指定联系人发一条信息");sn.add_argument("--contact-name",required=True);sn.add_argument("--message-file",required=True)
    # 内部实现命令（不作为对外功能颗粒度）
    op=subs.add_parser("open-surface",help="内部实现：打开指定 surface");op.add_argument("--surface",choices=["recommend","message"],required=True)
    sj=subs.add_parser("select-job",help="内部实现：在指定 surface 精确选择岗位");sj.add_argument("--surface",choices=["recommend","message"],required=True);sj.add_argument("--job",required=True)
    subs.add_parser("list-candidates",help="内部实现：列出推荐页候选人卡片")
    oc=subs.add_parser("open-candidate",help="内部实现：打开候选人卡片");oc.add_argument("--runtime-id",required=True);oc.add_argument("--keep-notice",action="store_true")
    subs.add_parser("list-conversations",help="内部实现：列出消息页会话行")
    om=subs.add_parser("open-conversation",help="内部实现：按 RuntimeId 打开消息会话");om.add_argument("--runtime-id",required=True);om.add_argument("--expected-job")
    subs.add_parser("inspect-chat",help="内部实现：检查当前会话")
    sc=subs.add_parser("send-current",help="内部实现：发送当前编辑器草稿");sc.add_argument("--message-file",required=True);sc.add_argument("--expected-identity");sc.add_argument("--expected-job")
    al=subs.add_parser("advance-list",help="内部实现：推进消息/推荐列表");al.add_argument("--surface",choices=["recommend","message"],required=True)
    g=subs.add_parser("greet-one",help="内部实现：对单个候选人打招呼");g.add_argument("--job",required=True);g.add_argument("--message-file",required=True)
    x=subs.add_parser("open-conversation-exact",help="内部实现：按精确联系人+最新消息打开会话");x.add_argument("--job",required=True);x.add_argument("--contact-name",required=True);x.add_argument("--latest-message",required=True)
    a=p.parse_args()
    try:
        if a.cmd=="inspect":res={"status":"READY","descendants":len(window().descendants())}
        elif a.cmd=="parse-docs":
            q=doc_text(a.question_docx);ans=doc_text(a.answer_docx)
            if len(q)<2 or len(ans)<2:fail("INPUT_DOCUMENT_REQUIRED","DOCX has no filled business content")
            res={"question_message":"\n".join(q[1:]),"answer_source":"\n".join(ans[1:])}
        elif a.cmd=="open-surface":res=open_surface(a.surface)
        elif a.cmd=="select-job":res=select_job(a.surface,a.job)
        elif a.cmd=="list-candidates":res=list_candidate_cards()
        elif a.cmd=="open-candidate":res=open_candidate_card(parse_runtime_id(a.runtime_id),not a.keep_notice)
        elif a.cmd=="list-conversations":res=list_message_rows()
        elif a.cmd=="open-conversation":res=open_message_runtime(parse_runtime_id(a.runtime_id),a.expected_job)
        elif a.cmd=="inspect-chat":res=inspect_current_chat()
        elif a.cmd=="send-current":res=send_current(Path(a.message_file).read_text(encoding="utf-8"),a.expected_identity,a.expected_job)
        elif a.cmd=="send-to-contact":res=send_message_to_contact(a.contact_name,Path(a.message_file).read_text(encoding="utf-8"))
        elif a.cmd=="advance-list":res=advance_list(a.surface)
        elif a.cmd=="greet-one":res=greet_one(a.job,Path(a.message_file).read_text(encoding="utf-8"))
        elif a.cmd=="batch-greet":res=batch_greet(a.job,Path(a.message_file).read_text(encoding="utf-8"),a.limit,a.process_all)
        elif a.cmd=="batch-message":res=batch_message(a.job,Path(a.message_file).read_text(encoding="utf-8"),a.limit,a.process_all)
        elif a.cmd=="open-next-unread":res=open_next_unread(a.job)
        elif a.cmd=="open-conversation-exact":
            ww=open_conversation_exact(a.contact_name,a.job,a.latest_message);res={"status":"OPENED","contact":a.contact_name,"editor_id":editor(ww).element_info.automation_id}
        else:res=reply_current(a.conversation_id,Path(a.reply_file).read_text(encoding="utf-8"))
        print(json.dumps({"ok":True,"result":res},ensure_ascii=False));return 0
    except Exception as exc:
        try:detail=json.loads(str(exc))
        except:detail={"code":type(exc).__name__,"message":str(exc)}
        print(json.dumps({"ok":False,"error":detail},ensure_ascii=False),file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
