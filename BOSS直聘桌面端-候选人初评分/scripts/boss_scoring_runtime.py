"""Fixed read-only BOSS UI orchestration for candidate scoring."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


EXPECTED_VERSION = "0.4.3"
EXPECTED_BUILD_ID = "boss-candidate-pipeline-20260803-v9"
EXPECTED_SELECTOR_PROFILE = "boss-1.7.4.963-candidate-pipeline-v6"


class ScoringRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": self.details}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def scoring_source_hash(value: dict[str, Any]) -> str:
    scoring_fields = {
        "title": value.get("title"),
        "description": value.get("description"),
        "education": value.get("education"),
        "internship": value.get("internship"),
    }
    return hashlib.sha256(canonical_json(scoring_fields).encode("utf-8")).hexdigest()


def runtime() -> tuple[Any, dict[str, str]]:
    import boss_candidates
    from boss_candidates.ui.selectors import SELECTOR_PROFILE

    provenance = {
        "python_executable": sys.executable,
        "module_path": str(Path(boss_candidates.__file__).resolve()),
        "runtime_version": boss_candidates.__version__,
        "distribution_version": importlib.metadata.version(
            "boss-candidate-pipeline-automation"
        ),
        "runtime_build_id": boss_candidates.RUNTIME_BUILD_ID,
        "selector_profile": SELECTOR_PROFILE,
    }
    expected = {
        "runtime_version": EXPECTED_VERSION,
        "distribution_version": EXPECTED_VERSION,
        "runtime_build_id": EXPECTED_BUILD_ID,
        "selector_profile": EXPECTED_SELECTOR_PROFILE,
    }
    mismatches = {
        key: {"expected": expected_value, "actual": provenance.get(key)}
        for key, expected_value in expected.items()
        if provenance.get(key) != expected_value
    }
    if mismatches:
        raise ScoringRuntimeError(
            "RUNTIME_MISMATCH",
            "BOSS candidate runtime provenance mismatch; run ensure_runtime.py",
            mismatches=mismatches,
        )
    return boss_candidates, provenance


def _launch_boss_if_needed(module: Any, *, timeout: float = 20.0) -> bool:
    from boss_candidates.ui.adapter import LiveBossAdapter
    from boss_candidates.errors import AmbiguousWindow
    from boss_candidates.ui.session import (
        BossCandidateSession,
        locate_executable,
    )

    adapter = LiveBossAdapter(
        config=module.DEFAULT_CONFIG,
        restart_for_accessibility=False,
    )
    environment = adapter.inspect_environment()
    if not environment.get("installed"):
        raise ScoringRuntimeError("APP_NOT_INSTALLED", "未找到 BOSS 直聘桌面客户端")

    def main_window_ready() -> bool:
        probe = BossCandidateSession(
            config=module.DEFAULT_CONFIG,
            maximize=False,
            restart_for_accessibility=False,
        )
        try:
            probe._attach_unique_window()
        except AmbiguousWindow:
            return False
        return probe.window is not None

    if environment.get("running") and main_window_ready():
        return False
    executable = locate_executable(module.DEFAULT_CONFIG)
    subprocess.Popen(
        [str(executable)],
        cwd=str(executable.parent),
        close_fds=True,
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if (
            adapter.inspect_environment().get("running")
            and main_window_ready()
        ):
            return True
        time.sleep(0.25)
    raise ScoringRuntimeError(
        "APP_START_TIMEOUT",
        "BOSS 客户端已启动但未在限定时间出现唯一主窗口",
        timeout_seconds=timeout,
    )


@contextmanager
def pipeline_session() -> Iterator[tuple[Any, Any, dict[str, str], bool]]:
    module, provenance = runtime()
    launched = _launch_boss_if_needed(module)
    from boss_candidates.ledger import CandidateLedger
    from boss_candidates.ui.adapter import LiveBossAdapter

    # Scoring is intentionally stateless.  A temporary ledger preserves the
    # shared global UI lock while preventing cross-run candidate merging.
    with tempfile.TemporaryDirectory(prefix="boss-candidate-scoring-") as directory:
        ledger = CandidateLedger(
            Path(directory) / "scoring-ledger.sqlite3",
            config=module.DEFAULT_CONFIG,
        )
        pipeline = module.BossCandidatePipeline(
            LiveBossAdapter(
                config=module.DEFAULT_CONFIG,
                restart_for_accessibility=False,
            ),
            ledger=ledger,
            config=module.DEFAULT_CONFIG,
        )
        yield module, pipeline, provenance, launched


def _resolve_job_source(
    module: Any,
    pipeline: Any,
    *,
    job_query: str,
) -> tuple[Any, dict[str, Any]]:
    """Bind the unique open job and read its edit form as the only JD source."""
    query = " ".join(str(job_query).split())
    if not query:
        raise ScoringRuntimeError("INVALID_QUERY", "job_query 不能为空")
    job = pipeline.bind_published_job(module.JobBindingHint(title=query))
    source = pipeline.read_job_scoring_context(job)
    source = {
        "job_key": job.job_key,
        "title": source.get("title"),
        "description": source.get("description"),
        "education": source.get("education"),
        "internship": source.get("internship"),
        "source": source.get("source") or "boss_job_edit_form",
        "source_hash": source.get("source_hash"),
    }
    if source.get("title") != job.title:
        raise ScoringRuntimeError(
            "JOB_SOURCE_UNAVAILABLE",
            "岗位评分源标题与已绑定岗位不一致",
            expected=job.title, actual=source.get("title"),
        )
    expected_hash = scoring_source_hash(source)
    if source.get("source_hash") != expected_hash:
        raise ScoringRuntimeError(
            "STALE_JOB_SOURCE",
            "岗位评分源哈希校验失败",
            embedded=source.get("source_hash"), computed=expected_hash,
        )
    return job, source


def _cached_job_context(
    module: Any, cached: dict[str, Any], *, job_query: str
) -> tuple[Any, dict[str, Any]]:
    """Restore an already verified task-local JD without reopening Positions."""
    if not isinstance(cached, dict):
        raise ScoringRuntimeError("INVALID_JOB_CONTEXT", "job context cache 必须是对象")
    job_ref = cached.get("job_ref")
    source = cached.get("job_source")
    if not isinstance(job_ref, dict) or not isinstance(source, dict):
        raise ScoringRuntimeError(
            "INVALID_JOB_CONTEXT", "job context cache 缺少 job_ref/job_source"
        )
    query = " ".join(str(job_query).split())
    if source.get("title") != query or job_ref.get("title") != query:
        raise ScoringRuntimeError(
            "CONTEXT_MISMATCH", "缓存岗位与查询岗位不一致",
            expected=query, cached=source.get("title"),
        )
    if source.get("source") != "boss_job_edit_form":
        raise ScoringRuntimeError(
            "INVALID_JOB_CONTEXT", "JD 必须来自 BOSS 职位→开放中编辑页",
            source=source.get("source"),
        )
    if source.get("job_key") != job_ref.get("job_key"):
        raise ScoringRuntimeError("CONTEXT_MISMATCH", "缓存岗位标识不一致")
    expected_hash = scoring_source_hash(source)
    if source.get("source_hash") != expected_hash:
        raise ScoringRuntimeError(
            "STALE_OR_TAMPERED_JOB_CONTEXT", "缓存 JD 完整性校验失败",
            embedded=source.get("source_hash"), computed=expected_hash,
        )
    required = ("job_key", "title", "status")
    if any(not job_ref.get(key) for key in required):
        raise ScoringRuntimeError("INVALID_JOB_CONTEXT", "缓存 job_ref 字段不完整")
    job = module.JobRef(
        job_key=job_ref["job_key"],
        title=job_ref["title"],
        city=job_ref.get("city"),
        salary=job_ref.get("salary"),
        status=job_ref["status"],
        platform_job_id=job_ref.get("platform_job_id"),
        company=job_ref.get("company"),
        recruitment_type=job_ref.get("recruitment_type"),
        binding_evidence=tuple(job_ref.get("binding_evidence") or ()),
        source_publish_run_id=job_ref.get("source_publish_run_id"),
    )
    return job, dict(source)

def read_job_context(job_query: str) -> dict[str, Any]:
    with pipeline_session() as (module, pipeline, provenance, launched):
        job, source = _resolve_job_source(
            module,
            pipeline,
            job_query=job_query,
        )
        return {
            "runtime": provenance,
            "boss_launched": launched,
            "job_ref": job.as_dict(),
            "job_source": source,
        }



def _document_text_control(session: Any) -> Any:
    """Return the largest BOSS UIA Document exposing TextPattern."""
    documents: list[tuple[int, Any]] = []
    if session.window is None:
        raise ScoringRuntimeError("APP_NOT_RUNNING", "BOSS 会话尚未连接")
    for document in session.window.descendants(control_type="Document"):
        try:
            text = document.iface_text.DocumentRange.GetText(-1)
        except Exception:
            continue
        if text:
            documents.append((len(text), document))
    if not documents:
        raise ScoringRuntimeError(
            "MESSAGE_TEXT_DOCUMENT_NOT_FOUND",
            "BOSS 消息页未暴露可用的 UIA Document TextPattern",
        )
    return max(documents, key=lambda item: item[0])[1]


def _find_text_ranges(document: Any, needle: str) -> list[Any]:
    root = document.iface_text.DocumentRange
    cursor = root.Clone()
    ranges: list[Any] = []
    while True:
        found = cursor.FindText(needle, False, True)
        if not found:
            break
        ranges.append(found)
        cursor.MoveEndpointByRange(0, found, 1)
        if cursor.CompareEndpoints(0, root, 1) >= 0:
            break
    return ranges


def _row_session_identity(row: Any, *, job_key: str) -> str:
    """Return a collision-resistant row identity for this connected UIA session.

    Electron runtime IDs are not persisted across connections, but they are the
    strongest identity available while one pywinauto session remains open.  A
    text fallback is used only when the provider does not expose a runtime ID.
    """
    from boss_candidates.models import stable_hash
    from boss_candidates.ui.adapter import _safe_visible_texts

    runtime_id = tuple(getattr(row.element_info, "runtime_id", ()) or ())
    raw_texts = []
    try:
        raw_texts.append(row.window_text())
    except Exception:
        pass
    try:
        raw_texts.extend(child.window_text() for child in row.descendants())
    except Exception:
        pass
    texts = _safe_visible_texts(raw_texts)
    if runtime_id:
        return stable_hash("message-row-runtime", job_key, runtime_id, texts)
    return stable_hash("message-row-text", job_key, texts)


def _visible_candidate_rows(adapter: Any, session: Any) -> list[Any]:
    """Return only candidate rows that currently occupy the list viewport."""
    if session.window is None:
        return []
    window_rect = session.window.rectangle()
    visible: list[Any] = []
    for row in adapter._candidate_message_rows(session):
        try:
            rect = row.rectangle()
        except Exception:
            continue
        if rect.width() <= 20 or rect.height() <= 20:
            continue
        if (
            rect.right <= window_rect.left
            or rect.left >= window_rect.right
            or rect.bottom <= window_rect.top
            or rect.top >= window_rect.bottom
        ):
            continue
        visible.append(row)
    visible.sort(key=lambda item: (item.rectangle().top, item.rectangle().left))
    return visible


def _viewport_signature(rows: list[Any], *, job_key: str) -> tuple[str, ...]:
    return tuple(_row_session_identity(row, job_key=job_key) for row in rows)


def _scroll_message_viewport(
    adapter: Any,
    session: Any,
    job: Any,
    *,
    direction: str,
    wheel_notches: int = 5,
    wait_seconds: float = 3.0,
) -> tuple[bool, tuple[str, ...]]:
    """Wheel the candidate list at a geometry-derived point with overlap.

    BOSS exposes off-screen ListItems with empty rectangles and does not expose
    ScrollPattern on the virtualised list.  TextRange.ScrollIntoView therefore
    cannot enumerate the list reliably.  A real pywinauto mouse wheel event is
    sent over the centre of the *currently visible candidate rows*.  Five
    notches moves less than one viewport, preserving overlap for omission checks.
    """
    from pywinauto import mouse

    rows = _visible_candidate_rows(adapter, session)
    before = _viewport_signature(rows, job_key=job.job_key)
    if not rows:
        raise ScoringRuntimeError(
            "MESSAGE_LIST_VIEWPORT_NOT_FOUND",
            "未找到当前可见的候选人消息行，无法安全滚动",
        )
    rects = [row.rectangle() for row in rows]
    left = max(rect.left for rect in rects)
    right = min(rect.right for rect in rects)
    if right <= left:
        left = min(rect.left for rect in rects)
        right = max(rect.right for rect in rects)
    top = min(rect.top for rect in rects)
    bottom = max(rect.bottom for rect in rects)
    x = int((left + right) / 2)
    y = int((top + bottom) / 2)
    wheel_dist = abs(wheel_notches) if direction == "up" else -abs(wheel_notches)
    mouse.scroll(coords=(x, y), wheel_dist=wheel_dist)

    deadline = time.monotonic() + wait_seconds
    latest = before
    while time.monotonic() < deadline:
        time.sleep(0.25)
        session.refresh()
        current_rows = _visible_candidate_rows(adapter, session)
        latest = _viewport_signature(current_rows, job_key=job.job_key)
        if latest and latest != before:
            return True, latest
    return False, latest


def _seek_message_list_top(
    adapter: Any,
    session: Any,
    job: Any,
    *,
    max_rounds: int = 40,
) -> int:
    """Normalise the virtual list to its newest/top boundary before sweeping down."""
    moved_rounds = 0
    stable = 0
    for _ in range(max_rounds):
        moved, _ = _scroll_message_viewport(
            adapter, session, job, direction="up", wheel_notches=7,
            wait_seconds=1.4,
        )
        if moved:
            moved_rounds += 1
            stable = 0
        else:
            stable += 1
            if stable >= 2:
                return moved_rounds
    raise ScoringRuntimeError(
        "CANDIDATE_SEARCH_LIMIT_REACHED",
        "向上定位消息列表边界达到轮次上限",
        direction="up",
        max_rounds=max_rounds,
    )


def _collect_new_greeting_profiles_single_session(
    module: Any, pipeline: Any, job: Any, *, limit: int,
    max_load_rounds: int = 80,
    queue_selector: Any | None = None, queue_label: str = "新招呼",
) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    """Read message rows and their profiles without reopening the job per candidate.

    BOSS 1.7.4.963 exposes the conversation list rows without candidate names.
    Opening each profile through ``read_message_candidate_profile`` creates a
    fresh adapter connection, navigates to Messages, and selects the job again.
    Apart from visible UI churn, Electron runtime IDs are connection-local.
    This routine keeps one connected UIA session, selects the job/new-greetings
    queue once, and reads each row in place.  Identity remains bounded by the
    clicked row plus the unique visible profile header and mid-* chat anchor.
    """
    from boss_candidates.models import CandidateRef, CandidateSnapshot, IdentityConfidence, stable_hash
    from boss_candidates.ui import selectors
    from boss_candidates.ui.adapter import _likely_name, _profile_from_texts, _safe_visible_texts

    adapter = pipeline.adapter
    snapshots: list[dict[str, Any]] = []
    with adapter._connected() as session:
        adapter._navigate(session, selectors.NAV_MESSAGES, label="消息")
        adapter._select_job(session, job)
        selected_queue = queue_selector or selectors.MESSAGES_NEW_GREETINGS
        adapter._click_message_header_tab(
            session, job, selected_queue, label=queue_label
        )
        session.refresh()
        # First move upward to a verified boundary, then sweep downward through
        # overlapping viewports. This is essential because BOSS keeps many
        # off-screen ListItems in UIA with rectangle=(0,0,0,0).
        upward_rounds = _seek_message_list_top(adapter, session, job)
        scroll_rounds = 0
        seen_rows: set[str] = set()
        exhausted_reason = "limit_reached"
        while len(snapshots) < limit:
            rows = _visible_candidate_rows(adapter, session)
            pending_rows: list[tuple[Any, str]] = []
            for row in rows:
                row_fingerprint = _row_session_identity(
                    row, job_key=job.job_key
                )
                if row_fingerprint not in seen_rows:
                    pending_rows.append((row, row_fingerprint))
            for row, row_fingerprint in pending_rows:
                if len(snapshots) >= limit:
                    break
                seen_rows.add(row_fingerprint)
                session.activate(row)
                session.refresh()
                if not session.wait_for(
                    lambda: bool(session.find_all_alternatives(
                        selectors.CHAT_EDITOR, actionable_only=False
                    )),
                    timeout=session.wait_timeout,
                ):
                    raise ScoringRuntimeError(
                        "ACCESSIBILITY_UNAVAILABLE",
                        "打开候选人行后聊天编辑器未加载",
                    )
                chat_scope = adapter._chat_scope(session)
                editor_rect = adapter._chat_editor(session).rectangle()
                entries = adapter._visible_chat_text_entries(
                    session, scope=chat_scope
                )
                # The Electron Document spans the whole page.  Restrict profile
                # parsing to the detail/chat pane to prevent other list rows from
                # contaminating the current candidate profile.
                detail_entries = [
                    entry for entry in entries
                    if entry[2].left >= editor_rect.left
                ]
                name = adapter._visible_chat_header_name(
                    session, chat_scope=chat_scope, entries=detail_entries
                )
                if not name:
                    # In this BOSS grey UI the name and age are stacked rather
                    # than on one row, so the upstream name-age pairing returns
                    # no result.  Use only the narrow visible header band of the
                    # detail pane; never infer a name from list previews/messages.
                    scope_rect = chat_scope.rectangle()
                    header_bottom = scope_rect.top + max(
                        1, (editor_rect.top - scope_rect.top) * 0.12
                    )
                    excluded = {
                        "刚刚活跃", "今日活跃", "在线", "牛人分析器",
                        "附件简历", "沟通职位", "期望", "更多",
                    }
                    header_names = {
                        text for _, text, rect in detail_entries
                        if rect.top <= header_bottom
                        and rect.left <= editor_rect.left + 220
                        and 2 <= len(text) <= 8
                        and not any(char.isdigit() for char in text)
                        and not any(mark in text for mark in "_·：:，,。！？!?/")
                        and text not in excluded
                        and not text.endswith("活跃")
                    }
                    if len(header_names) == 1:
                        name = next(iter(header_names))
                if not name:
                    raise ScoringRuntimeError(
                        "CANDIDATE_IDENTITY_CONFLICT",
                        "当前候选人详情头未暴露唯一姓名",
                        row_fingerprint=row_fingerprint,
                    )
                message_rows = adapter._chat_message_controls(
                    session, scope=chat_scope
                )
                message_candidates = []
                for message_row in message_rows:
                    message_id = " ".join(str(
                        getattr(message_row.element_info, "automation_id", "")
                    ).split())
                    if not message_id.startswith("mid-"):
                        continue
                    texts = _safe_visible_texts(session.texts_within(message_row))
                    text = max(texts, key=len) if texts else ""
                    if text:
                        message_candidates.append((message_id, text))
                if not message_candidates:
                    raise ScoringRuntimeError(
                        "CANDIDATE_IDENTITY_CONFLICT",
                        "当前聊天没有可校验的 mid-* 会话锚点",
                        candidate=name,
                    )
                anchor_id, anchor_text = min(message_candidates, key=lambda x: int(x[0][4:]))
                detail_texts = _safe_visible_texts(text for _, text, _ in detail_entries)
                if not any(job.title in value for value in detail_texts):
                    raise ScoringRuntimeError(
                        "CONTEXT_MISMATCH",
                        "当前候选人详情的沟通职位与绑定岗位不一致",
                        candidate=name,
                    )
                # v2 evidence-preserving profile: keep every safe visible detail text.
                # The legacy parser remains as a compatibility view for deterministic
                # rubric matching, while raw_profile_texts is the authoritative source
                # for later structured extraction and human-readable evidence.
                all_profile_texts = list(_safe_visible_texts((*detail_texts, anchor_text)))
                profile = _profile_from_texts(tuple(all_profile_texts))
                profile["raw_profile_texts"] = all_profile_texts
                profile["raw_profile_text"] = "\n".join(all_profile_texts)
                profile["visible_text_count"] = len(all_profile_texts)
                profile["latest_message_preview"] = anchor_text
                profile["_conversation_anchor"] = anchor_id
                candidate_key = stable_hash(
                    "message-candidate", job.job_key, anchor_id, name
                )
                ref = CandidateRef(
                    candidate_key=candidate_key,
                    job_key=job.job_key,
                    display_name=name,
                    conversation_id=anchor_id,
                    identity_confidence=IdentityConfidence.EXACT,
                )
                snapshot = CandidateSnapshot.create(
                    ref,
                    source="messages.current_profile",
                    profile=profile,
                    evidence_refs=(
                        f"当前岗位={job.title}",
                        f"消息队列={queue_label}",
                        f"conversation-anchor:{anchor_id}",
                        f"message-row:{row_fingerprint}",
                    ),
                )
                snapshots.append(snapshot.as_dict())
            if len(snapshots) >= limit:
                break
            if scroll_rounds >= max_load_rounds:
                raise ScoringRuntimeError(
                    "CANDIDATE_SEARCH_LIMIT_REACHED",
                    "候选人消息向下滚动达到轮次上限",
                    collected=len(snapshots),
                    scroll_rounds=scroll_rounds,
                    max_scroll_rounds=max_load_rounds,
                )
            moved, _ = _scroll_message_viewport(
                adapter, session, job, direction="down",
                wheel_notches=5, wait_seconds=3.0,
            )
            if not moved:
                exhausted_reason = "bottom_boundary"
                break
            scroll_rounds += 1
            session.refresh()
    return snapshots, None, [
        f"当前岗位={job.title}",
        f"消息标签={queue_label}",
        "滚动策略=pywinauto鼠标滚轮；先向上归一到顶部，再重叠向下遍历",
        f"向上归一轮次={upward_rounds}",
        f"向下滚动轮次={scroll_rounds}",
        f"已处理会话行={len(seen_rows)}",
        f"停止原因={exhausted_reason}",
    ]

def collect_message_candidates(
    job_query: str,
    *,
    candidate_query: str | None = None,
    limit: int = 50,
    expected_source_hash: str | None = None,
    job_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
        raise ScoringRuntimeError("INVALID_QUERY", "limit 必须是 1 到 200 的整数")
    normalized_candidate = (
        " ".join(candidate_query.split()).casefold()
        if candidate_query and candidate_query.strip()
        else None
    )
    display_candidate = (
        " ".join(candidate_query.split())
        if candidate_query and candidate_query.strip()
        else None
    )
    with pipeline_session() as (module, pipeline, provenance, launched):
        if job_context is None:
            raise ScoringRuntimeError(
                "JOB_CONTEXT_REQUIRED",
                "score-query 需要 --job-context-file；请先执行 job-context。",
            )
        job, source = _cached_job_context(
            module, job_context, job_query=job_query
        )
        if (
            expected_source_hash is not None
            and source.get("source_hash") != expected_source_hash
        ):
            raise ScoringRuntimeError(
                "STALE_JOB_SOURCE",
                "岗位描述已变化；候选人采集尚未开始",
                expected=expected_source_hash,
                current=source.get("source_hash"),
            )
        if display_candidate:
            from boss_candidates.models import IdentityConfidence, stable_hash

            # A named query searches only the fixed queues under Messages.
            # The adapter requires an exact visible name plus the bound job
            # and stops on ambiguity; this is lookup, not candidate merging.
            selected = [
                module.CandidateRef(
                    candidate_key=stable_hash(
                        "candidate-query",
                        job.job_key,
                        normalized_candidate,
                    ),
                    job_key=job.job_key,
                    display_name=display_candidate,
                    identity_confidence=IdentityConfidence.POSSIBLE,
                )
            ]
            snapshots = [
                pipeline.read_message_candidate_profile(
                    job, selected[0]
                ).as_dict()
            ]
            next_cursor = None
            context_evidence = [
                f"当前岗位={job.title}",
                "消息范围=固定队列精确姓名查询",
            ]
        else:
            snapshots, next_cursor, context_evidence = (
                _collect_new_greeting_profiles_single_session(
                    module, pipeline, job, limit=limit
                )
            )
            if not snapshots:
                raise ScoringRuntimeError(
                    "CANDIDATE_NOT_FOUND",
                    "当前岗位消息的新招呼中没有可评估候选人",
                    job_query=job_query,
                    scanned=0,
                )
        return {
            "runtime": provenance,
            "boss_launched": launched,
            "job_ref": job.as_dict(),
            "job_source": source,
            "candidate_query": candidate_query,
            "candidate_snapshots": snapshots,
            "next_cursor": next_cursor,
            "context_evidence": context_evidence,
        }
