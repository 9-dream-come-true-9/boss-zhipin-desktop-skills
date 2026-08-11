"""Deterministic rubric building and scoring for one BOSS candidate snapshot."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def load_scoring_runtime():
    path = Path(__file__).resolve().with_name("boss_scoring_runtime.py")
    spec = importlib.util.spec_from_file_location("boss_scoring_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load scoring runtime: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALLOWED_SOURCES = {
    "messages.new_greetings",
    "messages.current_conversation",
    "messages.current_profile",
}
ALLOWED_FIELDS = {
    "education",
    "major",
    "availability",
    "desired_role",
    "experience_summary",
    "skills",
}
ALLOWED_KINDS = {"GATE", "WEIGHTED"}
VALUE_TYPES = {
    "education_at_least",
    "number_at_least",
    "positive_term_any",
    "positive_term_all",
}
REQUIREMENT_KEYS = {
    "source_pointer",
    "source_span",
    "field",
    "canonical_value",
    "value_type",
    "modality",
}
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*")

PRIORITY_THRESHOLD = 80
PROMISING_THRESHOLD = 55
MINIMUM_COVERAGE = 0.45
RUBRIC_POLICY_VERSION = "auto-jd-v1"

EDUCATION_LEVELS = (
    "初中及以下",
    "中专/中技",
    "高中",
    "大专",
    "本科",
    "硕士",
    "博士",
)
EDUCATION_RANK = {level: index for index, level in enumerate(EDUCATION_LEVELS)}
EDUCATION_ALIASES = {
    "初中": "初中及以下",
    "中专": "中专/中技",
    "中技": "中专/中技",
    "专科": "大专",
    "学士": "本科",
    "研究生": "硕士",
}
NUMBER_UNITS = {"months", "days_per_week"}

MODALITY_ALIASES = {
    "required": "required",
    "mandatory": "required",
    "must": "required",
    "explicit_required": "required",
    "必须": "required",
    "要求": "required",
    "preferred": "preferred",
    "bonus": "preferred",
    "优先": "preferred",
    "加分": "preferred",
    "neutral": "core",
    "standard": "core",
    "core": "core",
    "一般": "core",
}
MODALITY_POLICY = {
    "required": ("GATE", 0.0),
    "core": ("WEIGHTED", 2.0),
    "preferred": ("WEIGHTED", 1.0),
}
MODALITY_ORDER = {"required": 0, "core": 1, "preferred": 2}

SENSITIVE_FIELDS = {
    "name",
    "display_name",
    "photo",
    "appearance",
    "gender",
    "sex",
    "age",
    "birth_date",
    "marital_status",
    "pregnancy",
    "fertility",
    "race",
    "ethnicity",
    "religion",
    "health",
    "disability",
    "biometric",
    "household_registration",
    "native_place",
}
SENSITIVE_TEXT_PATTERN = re.compile(
    "|".join(
        re.escape(term)
        for term in (
            "姓名",
            "名字",
            "照片",
            "头像",
            "外貌",
            "颜值",
            "形象",
            "性别",
            "男性",
            "女性",
            "男士",
            "女士",
            "年龄",
            "年轻",
            "婚育",
            "已婚",
            "未婚",
            "结婚",
            "生育",
            "怀孕",
            "妊娠",
            "民族",
            "种族",
            "宗教",
            "信仰",
            "健康",
            "疾病",
            "病史",
            "残障",
            "残疾",
            "身高",
            "体重",
            "户籍",
            "籍贯",
            "基因",
            "生物识别",
        )
    ),
    re.IGNORECASE,
)
SENSITIVE_ENGLISH_PATTERN = re.compile(
    r"\b(?:name|photo|appearance|gender|sex|age|marital|marriage|pregnan(?:t|cy)|"
    r"fertility|race|ethnicity|religion|health|disability|disabled|biometric)\b",
    re.IGNORECASE,
)
AGE_PATTERN = re.compile(r"(?<!\d)(?:1[6-9]|[2-5]\d)\s*岁")


class ScoringError(ValueError):
    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": self.details}


def read_json_value(path: str) -> Any:
    return json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))


def read_json(path: str) -> dict[str, Any]:
    value = read_json_value(path)
    if not isinstance(value, dict):
        raise ScoringError("INVALID_JSON", "JSON root must be an object")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def stable_hash(*parts: Any) -> str:
    return hashlib.sha256(canonical_json(parts).encode("utf-8")).hexdigest()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(normalize_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(normalize_text(item) for item in value)
    return re.sub(r"\s+", " ", str(value)).strip()


def is_sensitive_condition(*values: Any) -> bool:
    text = normalize_text(values)
    return bool(
        SENSITIVE_TEXT_PATTERN.search(text)
        or SENSITIVE_ENGLISH_PATTERN.search(text)
        or AGE_PATTERN.search(text)
    )


def validate_string_list(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ScoringError("INVALID_RUBRIC", f"{label} must be an array")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ScoringError(
                "INVALID_RUBRIC",
                f"{label}[{index}] must be a non-empty string",
            )
        normalized = item.strip()
        if normalized not in result:
            result.append(normalized)
    return result


def normalize_terms(value: Any, *, label: str, error_code: str) -> list[str]:
    raw = [value] if isinstance(value, str) else value
    if not isinstance(raw, list) or not raw:
        raise ScoringError(error_code, f"{label} must be a string or non-empty array")
    terms: list[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise ScoringError(
                error_code, f"{label}[{index}] must be a non-empty string"
            )
        normalized = item.strip()
        if normalized not in terms:
            terms.append(normalized)
    return terms


def normalize_education(value: Any, *, error_code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScoringError(error_code, "education level must be a non-empty string")
    text = normalize_text(value)
    if text in EDUCATION_RANK:
        return text
    if text in EDUCATION_ALIASES:
        return EDUCATION_ALIASES[text]
    for level in reversed(EDUCATION_LEVELS):
        if level in text:
            return level
    for alias, level in EDUCATION_ALIASES.items():
        if alias in text:
            return level
    raise ScoringError(error_code, f"unsupported education level: {text}")


def normalize_number_target(value: Any, *, error_code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScoringError(
            error_code,
            "number_at_least canonical_value must contain value and unit",
        )
    if set(value) != {"value", "unit"}:
        raise ScoringError(
            error_code,
            "number_at_least canonical_value must contain only value and unit",
        )
    number = value["value"]
    unit = value["unit"]
    if (
        not isinstance(number, (int, float))
        or isinstance(number, bool)
        or float(number) <= 0
    ):
        raise ScoringError(error_code, "number_at_least value must be positive")
    if unit not in NUMBER_UNITS:
        raise ScoringError(
            error_code,
            "number_at_least unit must be months or days_per_week",
        )
    normalized_number: int | float = float(number)
    if normalized_number.is_integer():
        normalized_number = int(normalized_number)
    return {"value": normalized_number, "unit": unit}


def normalize_typed_value(
    value_type: str,
    canonical_value: Any,
    *,
    field: str,
    error_code: str,
) -> Any:
    if value_type == "education_at_least":
        if field != "education":
            raise ScoringError(
                error_code, "education_at_least may only use education"
            )
        return normalize_education(canonical_value, error_code=error_code)
    if value_type == "number_at_least":
        if field != "availability":
            raise ScoringError(
                error_code, "number_at_least may only use availability"
            )
        return normalize_number_target(canonical_value, error_code=error_code)
    if value_type in {"positive_term_any", "positive_term_all"}:
        return normalize_terms(
            canonical_value, label="canonical_value", error_code=error_code
        )
    raise ScoringError(error_code, f"unsupported value_type: {value_type}")


def validate_rubric(value: dict[str, Any]) -> dict[str, Any]:
    allowed_root = {
        "version",
        "source_hash",
        "requirements_hash",
        "priority_threshold",
        "promising_threshold",
        "minimum_coverage",
        "criteria",
    }
    unknown_root = sorted(set(value) - allowed_root)
    if unknown_root:
        raise ScoringError(
            "INVALID_RUBRIC",
            "rubric contains unsupported keys",
            keys=unknown_root,
        )
    version = value.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ScoringError("INVALID_RUBRIC", "rubric version is required")
    priority = value.get("priority_threshold", PRIORITY_THRESHOLD)
    promising = value.get("promising_threshold", PROMISING_THRESHOLD)
    minimum_coverage = value.get("minimum_coverage", MINIMUM_COVERAGE)
    for label, threshold in (
        ("priority_threshold", priority),
        ("promising_threshold", promising),
    ):
        if (
            not isinstance(threshold, int)
            or isinstance(threshold, bool)
            or not 0 <= threshold <= 100
        ):
            raise ScoringError(
                "INVALID_RUBRIC", f"{label} must be an integer from 0 to 100"
            )
    if promising > priority:
        raise ScoringError(
            "INVALID_RUBRIC",
            "promising_threshold cannot exceed priority_threshold",
        )
    if (
        not isinstance(minimum_coverage, (int, float))
        or isinstance(minimum_coverage, bool)
        or not 0 <= float(minimum_coverage) <= 1
    ):
        raise ScoringError(
            "INVALID_RUBRIC", "minimum_coverage must be between 0 and 1"
        )
    raw_criteria = value.get("criteria")
    if not isinstance(raw_criteria, list) or not raw_criteria:
        raise ScoringError(
            "INVALID_RUBRIC", "rubric must contain at least one criterion"
        )
    allowed_criterion = {
        "criterion_id",
        "field",
        "expected",
        "kind",
        "weight",
        "value_type",
        "canonical_value",
        "any_terms",
        "all_terms",
        "mismatch_terms",
        "allow_partial",
    }
    normalized_criteria: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_criteria):
        if not isinstance(raw, dict):
            raise ScoringError(
                "INVALID_RUBRIC", f"criteria[{index}] must be an object"
            )
        unknown = sorted(set(raw) - allowed_criterion)
        if unknown:
            raise ScoringError(
                "INVALID_RUBRIC",
                f"criteria[{index}] contains unsupported keys",
                keys=unknown,
            )
        criterion_id = raw.get("criterion_id")
        if not isinstance(criterion_id, str) or not ID_PATTERN.fullmatch(criterion_id):
            raise ScoringError(
                "INVALID_RUBRIC", f"criteria[{index}].criterion_id is invalid"
            )
        if criterion_id in seen_ids:
            raise ScoringError(
                "INVALID_RUBRIC", f"duplicate criterion_id: {criterion_id}"
            )
        seen_ids.add(criterion_id)
        field = raw.get("field")
        if field not in ALLOWED_FIELDS:
            raise ScoringError(
                "UNSAFE_SCORING_CRITERION",
                f"criterion {criterion_id} uses a prohibited or unsupported field",
                field=field,
            )
        expected = raw.get("expected")
        if not isinstance(expected, str) or not expected.strip():
            raise ScoringError(
                "INVALID_RUBRIC",
                f"criteria[{index}].expected must be a non-empty string",
            )
        kind = raw.get("kind", "WEIGHTED")
        if kind not in ALLOWED_KINDS:
            raise ScoringError(
                "INVALID_RUBRIC",
                f"criteria[{index}].kind must be GATE or WEIGHTED",
            )
        weight = raw.get("weight", 1.0)
        if (
            not isinstance(weight, (int, float))
            or isinstance(weight, bool)
            or float(weight) < 0
        ):
            raise ScoringError(
                "INVALID_RUBRIC", f"criteria[{index}].weight must be non-negative"
            )
        if kind == "WEIGHTED" and float(weight) <= 0:
            raise ScoringError(
                "INVALID_RUBRIC",
                f"weighted criterion {criterion_id} must have positive weight",
            )
        value_type = raw.get("value_type")
        has_canonical = "canonical_value" in raw
        if (value_type is None) != (not has_canonical):
            raise ScoringError(
                "INVALID_RUBRIC",
                f"criterion {criterion_id} must provide value_type and canonical_value together",
            )
        canonical_value: Any = None
        if value_type is not None:
            if value_type not in VALUE_TYPES:
                raise ScoringError(
                    "INVALID_RUBRIC", f"unsupported value_type: {value_type}"
                )
            canonical_value = normalize_typed_value(
                value_type,
                raw["canonical_value"],
                field=field,
                error_code="INVALID_RUBRIC",
            )
        any_terms = validate_string_list(
            raw.get("any_terms", []), label=f"criteria[{index}].any_terms"
        )
        all_terms = validate_string_list(
            raw.get("all_terms", []), label=f"criteria[{index}].all_terms"
        )
        mismatch_terms = validate_string_list(
            raw.get("mismatch_terms", []),
            label=f"criteria[{index}].mismatch_terms",
        )
        if value_type == "positive_term_any":
            any_terms = list(canonical_value)
        elif value_type == "positive_term_all":
            all_terms = list(canonical_value)
        elif value_type is None and not any_terms and not all_terms and not mismatch_terms:
            raise ScoringError(
                "INVALID_RUBRIC",
                f"criterion {criterion_id} must define a typed value or terms",
            )
        if is_sensitive_condition(
            field,
            expected,
            canonical_value,
            any_terms,
            all_terms,
            mismatch_terms,
        ):
            raise ScoringError(
                "UNSAFE_SCORING_CRITERION",
                f"criterion {criterion_id} contains a protected or sensitive condition",
            )
        allow_partial = raw.get("allow_partial", True)
        if not isinstance(allow_partial, bool):
            raise ScoringError(
                "INVALID_RUBRIC",
                f"criteria[{index}].allow_partial must be boolean",
            )
        normalized = {
            "criterion_id": criterion_id,
            "field": field,
            "expected": expected.strip(),
            "kind": kind,
            "weight": float(weight),
            "any_terms": any_terms,
            "all_terms": all_terms,
            "mismatch_terms": mismatch_terms,
            "allow_partial": allow_partial,
        }
        if value_type is not None:
            normalized["value_type"] = value_type
            normalized["canonical_value"] = canonical_value
        normalized_criteria.append(normalized)
    result: dict[str, Any] = {
        "version": version.strip(),
        "priority_threshold": priority,
        "promising_threshold": promising,
        "minimum_coverage": float(minimum_coverage),
        "criteria": normalized_criteria,
    }
    for key in ("source_hash", "requirements_hash"):
        item = value.get(key)
        if item is not None:
            if not isinstance(item, str) or not item.strip():
                raise ScoringError("INVALID_RUBRIC", f"{key} must be non-empty")
            result[key] = item.strip()
    return result


def normalize_job_source(value: dict[str, Any]) -> dict[str, Any]:
    required = {"title", "description", "education", "internship", "source_hash"}
    allowed = required | {"job_key", "publish_run_id", "source"}
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing or unknown:
        raise ScoringError(
            "INVALID_JOB_SOURCE",
            "job_source keys are invalid",
            missing=missing,
            unknown=unknown,
        )
    title = value["title"]
    description = value["description"]
    education = value["education"]
    source_hash = value["source_hash"]
    if not isinstance(title, str) or not title.strip():
        raise ScoringError("INVALID_JOB_SOURCE", "title must be non-empty")
    if not isinstance(description, str) or not description.strip():
        raise ScoringError("INVALID_JOB_SOURCE", "description must be non-empty")
    if not isinstance(education, str) or not education.strip():
        raise ScoringError("INVALID_JOB_SOURCE", "education must be non-empty")
    if not isinstance(source_hash, str) or not source_hash.strip():
        raise ScoringError("INVALID_JOB_SOURCE", "source_hash must be non-empty")
    internship = value["internship"]
    if not isinstance(internship, dict) or set(internship) != {
        "minimum_months",
        "days_per_week",
    }:
        raise ScoringError(
            "INVALID_JOB_SOURCE",
            "internship must contain only minimum_months and days_per_week",
        )
    minimum_months = internship["minimum_months"]
    days_per_week = internship["days_per_week"]
    if (
        not isinstance(minimum_months, int)
        or isinstance(minimum_months, bool)
        or not 1 <= minimum_months <= 12
    ):
        raise ScoringError(
            "INVALID_JOB_SOURCE", "minimum_months must be an integer from 1 to 12"
        )
    if (
        not isinstance(days_per_week, int)
        or isinstance(days_per_week, bool)
        or not 1 <= days_per_week <= 7
    ):
        raise ScoringError(
            "INVALID_JOB_SOURCE", "days_per_week must be an integer from 1 to 7"
        )
    result = {
        "title": normalize_text(title),
        "description": description.replace("\r\n", "\n").strip(),
        "education": normalize_text(education),
        "internship": {
            "minimum_months": minimum_months,
            "days_per_week": days_per_week,
        },
        "source_hash": source_hash.strip(),
    }
    for key in ("job_key", "publish_run_id"):
        item = value.get(key)
        if item is not None:
            if not isinstance(item, str) or not item.strip():
                raise ScoringError("INVALID_JOB_SOURCE", f"{key} must be non-empty")
            result[key] = item.strip()
    source = value.get("source")
    if source is not None:
        if not isinstance(source, str) or not source.strip():
            raise ScoringError("INVALID_JOB_SOURCE", "source must be non-empty")
        result["source"] = source.strip()
    return result


def normalize_modality(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScoringError("INVALID_REQUIREMENTS", "modality must be non-empty")
    normalized = MODALITY_ALIASES.get(value.strip().casefold())
    if normalized is None:
        normalized = MODALITY_ALIASES.get(value.strip())
    if normalized is None:
        raise ScoringError(
            "INVALID_REQUIREMENTS", f"unsupported modality: {value}"
        )
    return normalized


def source_text_for_pointer(job_source: dict[str, Any], pointer: str) -> str:
    if pointer.startswith("/description"):
        return job_source["description"]
    if pointer.startswith("/title"):
        return job_source["title"]
    if pointer.startswith("/education"):
        return job_source["education"]
    if pointer.startswith("/internship/minimum_months"):
        return str(job_source["internship"]["minimum_months"])
    if pointer.startswith("/internship/days_per_week"):
        return str(job_source["internship"]["days_per_week"])
    return ""


def normalize_requirements(
    job_source: dict[str, Any], requirements: Any
) -> list[dict[str, Any]]:
    if not isinstance(requirements, list):
        raise ScoringError("INVALID_REQUIREMENTS", "requirements must be an array")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(requirements):
        if not isinstance(raw, dict):
            raise ScoringError(
                "INVALID_REQUIREMENTS", f"requirements[{index}] must be an object"
            )
        unknown = sorted(set(raw) - REQUIREMENT_KEYS)
        missing = sorted(REQUIREMENT_KEYS - set(raw))
        if unknown or missing:
            raise ScoringError(
                "INVALID_REQUIREMENTS",
                f"requirements[{index}] keys are invalid",
                missing=missing,
                unknown=unknown,
            )
        pointer = raw["source_pointer"]
        span = raw["source_span"]
        field = raw["field"]
        value_type = raw["value_type"]
        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise ScoringError(
                "INVALID_REQUIREMENTS",
                f"requirements[{index}].source_pointer must be a JSON pointer",
            )
        if not isinstance(span, str) or not span.strip():
            raise ScoringError(
                "INVALID_REQUIREMENTS",
                f"requirements[{index}].source_span must be non-empty",
            )
        if not isinstance(field, str) or not field.strip():
            raise ScoringError(
                "INVALID_REQUIREMENTS",
                f"requirements[{index}].field must be non-empty",
            )
        normalized_field = field.strip()
        if normalized_field.casefold() in SENSITIVE_FIELDS:
            continue
        if normalized_field not in ALLOWED_FIELDS:
            raise ScoringError(
                "UNSAFE_SCORING_CRITERION",
                f"requirements[{index}] uses a prohibited or unsupported field",
                field=normalized_field,
            )
        if not isinstance(value_type, str) or value_type not in VALUE_TYPES:
            raise ScoringError(
                "INVALID_REQUIREMENTS",
                f"requirements[{index}].value_type is unsupported",
            )
        if is_sensitive_condition(span, raw["canonical_value"]):
            continue
        source_text = source_text_for_pointer(job_source, pointer)
        if not source_text or normalize_text(span) not in normalize_text(source_text):
            raise ScoringError(
                "UNGROUNDED_REQUIREMENT",
                f"requirements[{index}].source_span is not grounded in job_source",
                source_pointer=pointer,
            )
        canonical_value = normalize_typed_value(
            value_type,
            raw["canonical_value"],
            field=normalized_field,
            error_code="INVALID_REQUIREMENTS",
        )
        if is_sensitive_condition(canonical_value):
            continue
        normalized.append(
            {
                "source_pointer": pointer,
                "source_span": normalize_text(span),
                "field": normalized_field,
                "canonical_value": canonical_value,
                "value_type": value_type,
                "modality": normalize_modality(raw["modality"]),
            }
        )
    normalized.sort(
        key=lambda item: (
            item["field"],
            item["value_type"],
            canonical_json(item["canonical_value"]),
            MODALITY_ORDER[item["modality"]],
            item["source_pointer"],
            item["source_span"],
        )
    )
    return normalized


def title_terms(title: str) -> list[str]:
    terms = [normalize_text(title)]
    stripped = re.sub(r"(?:实习生招聘|实习生|实习岗位|实习)$", "", terms[0]).strip()
    if stripped and stripped not in terms:
        terms.append(stripped)
    return terms


def typed_criterion(
    *,
    criterion_id: str,
    field: str,
    expected: str,
    kind: str,
    weight: float,
    value_type: str,
    canonical_value: Any,
) -> dict[str, Any]:
    return {
        "criterion_id": criterion_id,
        "field": field,
        "expected": expected,
        "kind": kind,
        "weight": weight,
        "value_type": value_type,
        "canonical_value": canonical_value,
        "allow_partial": True,
    }


def build_rubric(
    job_source: dict[str, Any], requirements: Any
) -> dict[str, Any]:
    """Build one reproducible rubric from a job source and bounded extraction."""

    source = normalize_job_source(job_source)
    normalized_requirements = normalize_requirements(source, requirements)
    criteria: list[dict[str, Any]] = []
    signatures: set[tuple[str, str, str]] = set()

    def add(item: dict[str, Any]) -> None:
        signature = (
            item["field"],
            item["value_type"],
            canonical_json(item["canonical_value"]),
        )
        if signature not in signatures:
            signatures.add(signature)
            criteria.append(item)

    if not is_sensitive_condition(source["title"]):
        add(
            typed_criterion(
                criterion_id="job_title_alignment",
                field="desired_role",
                expected=f"求职方向与{source['title']}相关",
                kind="WEIGHTED",
                weight=1.0,
                value_type="positive_term_any",
                canonical_value=title_terms(source["title"]),
            )
        )

    if source["education"] not in {"不限", "无要求"}:
        education = normalize_education(
            source["education"], error_code="INVALID_JOB_SOURCE"
        )
        add(
            typed_criterion(
                criterion_id="structured_education",
                field="education",
                expected=f"{education}及以上",
                kind="GATE",
                weight=0.0,
                value_type="education_at_least",
                canonical_value=education,
            )
        )

    months = source["internship"]["minimum_months"]
    add(
        typed_criterion(
            criterion_id="structured_availability_months",
            field="availability",
            expected=f"可连续实习至少{months}个月",
            kind="GATE",
            weight=0.0,
            value_type="number_at_least",
            canonical_value={"value": months, "unit": "months"},
        )
    )
    days = source["internship"]["days_per_week"]
    add(
        typed_criterion(
            criterion_id="structured_availability_days",
            field="availability",
            expected=f"每周到岗至少{days}天",
            kind="GATE",
            weight=0.0,
            value_type="number_at_least",
            canonical_value={"value": days, "unit": "days_per_week"},
        )
    )

    for requirement in normalized_requirements:
        kind, weight = MODALITY_POLICY[requirement["modality"]]
        suffix = stable_hash(
            requirement["field"],
            requirement["value_type"],
            requirement["canonical_value"],
        )[:10]
        add(
            typed_criterion(
                criterion_id=f"requirement_{requirement['field']}_{suffix}",
                field=requirement["field"],
                expected=requirement["source_span"],
                kind=kind,
                weight=weight,
                value_type=requirement["value_type"],
                canonical_value=requirement["canonical_value"],
            )
        )

    if not criteria:
        raise ScoringError(
            "NO_SCORABLE_JOB_CRITERIA",
            "job source contains no safe job-related scoring criteria",
        )
    requirements_hash = stable_hash(normalized_requirements)
    version_hash = stable_hash(
        RUBRIC_POLICY_VERSION, source["source_hash"], normalized_requirements
    )[:16]
    return validate_rubric(
        {
            "version": f"{RUBRIC_POLICY_VERSION}-{version_hash}",
            "source_hash": source["source_hash"],
            "requirements_hash": requirements_hash,
            "priority_threshold": PRIORITY_THRESHOLD,
            "promising_threshold": PROMISING_THRESHOLD,
            "minimum_coverage": MINIMUM_COVERAGE,
            "criteria": criteria,
        }
    )


def validate_snapshot(value: dict[str, Any]) -> dict[str, Any]:
    candidate_ref = value.get("candidate_ref")
    if not isinstance(candidate_ref, dict):
        raise ScoringError("INVALID_SNAPSHOT", "candidate_ref is required")
    job_key = candidate_ref.get("job_key")
    candidate_key = candidate_ref.get("candidate_key")
    display_name = candidate_ref.get("display_name")
    if not isinstance(job_key, str) or not job_key:
        raise ScoringError("INVALID_SNAPSHOT", "candidate_ref.job_key is required")
    if not isinstance(candidate_key, str) or not candidate_key:
        raise ScoringError(
            "INVALID_SNAPSHOT", "candidate_ref.candidate_key is required"
        )
    if not isinstance(display_name, str) or not display_name.strip():
        raise ScoringError(
            "INVALID_SNAPSHOT", "candidate_ref.display_name is required"
        )
    source = value.get("source")
    if source not in ALLOWED_SOURCES:
        raise ScoringError(
            "UNSUPPORTED_SOURCE",
            "only snapshots captured from the BOSS Message entry are accepted",
            source=source,
        )
    profile = value.get("profile")
    if not isinstance(profile, dict):
        raise ScoringError("INVALID_SNAPSHOT", "profile must be an object")
    evidence_refs = value.get("evidence_refs", [])
    if not isinstance(evidence_refs, list) or not all(
        isinstance(item, str) for item in evidence_refs
    ):
        raise ScoringError(
            "INVALID_SNAPSHOT", "evidence_refs must be an array of strings"
        )
    embedded_hash = value.get("content_hash")
    if not isinstance(embedded_hash, str) or not HASH_PATTERN.fullmatch(embedded_hash):
        raise ScoringError("INVALID_SNAPSHOT", "content_hash must be SHA-256")
    computed_hash = stable_hash(candidate_key, source, profile)
    if computed_hash != embedded_hash:
        raise ScoringError(
            "STALE_OR_TAMPERED_SNAPSHOT",
            "embedded snapshot hash does not match the selected candidate evidence",
            embedded=embedded_hash,
            computed=computed_hash,
        )
    return value


def candidate_information(profile: dict[str, Any]) -> dict[str, Any]:
    """Return an evidence-preserving, user-facing candidate information view.

    No visible fact is discarded: raw_profile_texts remains authoritative. The
    categorized arrays are additive indexes, not lossy summaries. When a detail
    cannot be parsed safely it stays in other_profile_facts instead of vanishing.
    """
    raw = profile.get("raw_profile_texts")
    if not isinstance(raw, list):
        raw = []
    texts = []
    for item in raw:
        text = normalize_text(item)
        if text and text not in texts:
            texts.append(text)
    if not texts:
        # Backward-compatible snapshots still expose all legacy fields.
        for key in ("education", "major", "availability", "desired_role", "experience_summary", "skills"):
            value = profile.get(key)
            values = value if isinstance(value, list) else [value]
            for item in values:
                text = normalize_text(item)
                if text and text not in texts:
                    texts.append(text)
    education_markers = ("大学", "学院", "学校", "专业", "本科", "硕士", "博士", "大专", "毕业", "在读")
    experience_markers = ("实习", "工作经历", "任职", "负责", "职责", "公司", "产品", "运营", "研发", "算法")
    project_markers = ("项目", "成果", "上线", "增长", "提升", "优化", "落地")
    skill_markers = ("python", "java", "aigc", "figma", "cursor", "claude", "rpa", "ai", "技能", "工具", "原型", "prd")
    availability_markers = ("到岗", "每周", "个月", "长期实习", "出勤", "应届", "在校")
    def selected(markers: tuple[str, ...]) -> list[str]:
        return [t for t in texts if any(m.casefold() in t.casefold() for m in markers)]
    education = selected(education_markers)
    experience = selected(experience_markers)
    projects = selected(project_markers)
    skills = selected(skill_markers)
    availability = selected(availability_markers)
    desired = [t for t in texts if t.startswith("期望") or "期望职位" in t]
    categorized = set(education + experience + projects + skills + availability + desired)
    return {
        "desired_role": desired or ([normalize_text(profile.get("desired_role"))] if profile.get("desired_role") else []),
        "availability_facts": availability,
        "education_facts": education,
        "experience_facts": experience,
        "project_facts": projects,
        "skill_facts": skills,
        "other_profile_facts": [t for t in texts if t not in categorized],
        "raw_profile_texts": texts,
        "completeness": {
            "visible_text_count": len(texts),
            "raw_text_preserved": bool(profile.get("raw_profile_texts")),
            "status": "COMPLETE" if profile.get("raw_profile_texts") else "LEGACY_SNAPSHOT_PARTIAL",
        },
    }


def criterion_source_texts(profile: dict[str, Any], criterion: dict[str, Any]) -> list[str]:
    info = candidate_information(profile)
    mapping = {
        "education": "education_facts",
        "major": "education_facts",
        "availability": "availability_facts",
        "desired_role": "desired_role",
        "experience_summary": "experience_facts",
        "skills": "skill_facts",
    }
    values = list(info.get(mapping.get(criterion["field"], "raw_profile_texts"), []))
    if not values:
        values = list(info["raw_profile_texts"])
    return values


def contains(text: str, term: str) -> bool:
    return normalize_text(term).casefold() in text.casefold()


def observed_education(text: str) -> str | None:
    hits: list[str] = []
    for level in EDUCATION_LEVELS:
        if level in text:
            hits.append(level)
    for alias, level in EDUCATION_ALIASES.items():
        if alias in text:
            hits.append(level)
    if not hits:
        return None
    return max(hits, key=lambda item: EDUCATION_RANK[item])


CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}


def parse_number_token(value: str) -> float | None:
    if value in CHINESE_NUMBERS:
        return float(CHINESE_NUMBERS[value])
    try:
        return float(value)
    except ValueError:
        return None


def observed_number(text: str, unit: str) -> float | None:
    token = r"(?:\d+(?:\.\d+)?|十二|十一|十|[一二两三四五六七八九])"
    if unit == "months":
        patterns = [rf"({token})\s*(?:个)?月"]
    else:
        patterns = [
            rf"每周\s*({token})\s*[天日]",
            rf"({token})\s*[天日]\s*(?:/|每)\s*周",
        ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return parse_number_token(match.group(1))
    return None


def evaluate_typed_criterion(
    observed: str, criterion: dict[str, Any]
) -> tuple[str, str, float]:
    value_type = criterion["value_type"]
    target = criterion["canonical_value"]
    if value_type == "education_at_least":
        level = observed_education(observed)
        if level is None:
            return "UNKNOWN", "学历文本无法映射到受支持等级", 0.35
        if EDUCATION_RANK[level] >= EDUCATION_RANK[target]:
            return "MATCH", f"已核验学历达到{target}及以上", 1.0
        return "MISMATCH", f"已核验学历低于{target}要求", 1.0
    if value_type == "number_at_least":
        number = observed_number(observed, target["unit"])
        if number is None:
            return "UNKNOWN", "到岗文本没有可核验的对应数值", 0.35
        if number >= float(target["value"]):
            return "MATCH", f"已核验数值达到最低要求：{number:g}", 1.0
        return "MISMATCH", f"已核验数值低于最低要求：{number:g}", 1.0
    terms = list(target)
    hits = [term for term in terms if contains(observed, term)]
    if value_type == "positive_term_any":
        if hits:
            return "MATCH", "命中规则关键词：" + "、".join(hits), 1.0
        return "UNKNOWN", "字段已有信息，但没有可核验的正向命中", 0.35
    if len(hits) == len(terms):
        return "MATCH", "命中全部规则关键词：" + "、".join(hits), 1.0
    if hits and criterion["allow_partial"]:
        return "PARTIAL", "部分命中规则关键词：" + "、".join(hits), 0.65
    return "UNKNOWN", "字段已有信息，但没有可核验的完整命中", 0.35


def evaluate_criterion(
    profile: dict[str, Any],
    evidence_refs: list[str],
    criterion: dict[str, Any],
) -> dict[str, Any]:
    observed = normalize_text(profile.get(criterion["field"]))
    if not observed:
        outcome, summary, confidence = (
            "UNKNOWN",
            "当前消息入口没有可核验信息",
            0.0,
        )
    elif "value_type" in criterion:
        outcome, summary, confidence = evaluate_typed_criterion(observed, criterion)
    else:
        mismatch_hits = [
            term for term in criterion["mismatch_terms"] if contains(observed, term)
        ]
        any_hits = [
            term for term in criterion["any_terms"] if contains(observed, term)
        ]
        all_hits = [
            term for term in criterion["all_terms"] if contains(observed, term)
        ]
        all_ok = not criterion["all_terms"] or len(all_hits) == len(
            criterion["all_terms"]
        )
        any_ok = not criterion["any_terms"] or bool(any_hits)
        if mismatch_hits:
            outcome = "MISMATCH"
            summary = "命中排除关键词：" + "、".join(mismatch_hits)
            confidence = 1.0
        elif all_ok and any_ok:
            outcome = "MATCH"
            hits = list(dict.fromkeys([*any_hits, *all_hits]))
            summary = (
                "命中规则关键词：" + "、".join(hits)
                if hits
                else "字段存在可核验信息"
            )
            confidence = 1.0
        elif criterion["allow_partial"] and (any_hits or all_hits):
            outcome = "PARTIAL"
            hits = list(dict.fromkeys([*any_hits, *all_hits]))
            summary = "部分命中规则关键词：" + "、".join(hits)
            confidence = 0.65
        else:
            outcome = "UNKNOWN"
            summary = "字段已有信息，但未命中已配置的规则关键词"
            confidence = 0.35
    source_texts = criterion_source_texts(profile, criterion)
    return {
        "criterion_id": criterion["criterion_id"],
        "kind": criterion["kind"],
        "expected": criterion["expected"],
        "jd_requirement": criterion["expected"],
        "candidate_field": criterion["field"],
        "candidate_facts": source_texts,
        "candidate_source_texts": source_texts,
        "outcome": outcome,
        "observed_summary": summary,
        "evidence_refs": evidence_refs,
        "confidence": confidence,
        "weight": criterion["weight"],
    }


def score_candidate(snapshot: dict[str, Any], rubric: dict[str, Any]) -> dict[str, Any]:
    """Score one immutable message-entry snapshot without UI or persistence."""

    snapshot = validate_snapshot(snapshot)
    rubric = validate_rubric(rubric)
    evidence = [
        evaluate_criterion(
            snapshot["profile"],
            list(snapshot.get("evidence_refs", [])),
            criterion,
        )
        for criterion in rubric["criteria"]
    ]
    gates = [item for item in evidence if item["kind"] == "GATE"]
    if any(item["outcome"] == "MISMATCH" for item in gates):
        hard_gate = "FAIL"
    elif not gates or all(item["outcome"] == "MATCH" for item in gates):
        hard_gate = "PASS"
    else:
        hard_gate = "UNKNOWN"
    weighted = [item for item in evidence if item["kind"] == "WEIGHTED"]
    known_weighted = [item for item in weighted if item["outcome"] != "UNKNOWN"]
    total_weight = sum(item["weight"] for item in weighted)
    known_weight = sum(item["weight"] for item in known_weighted)
    if known_weight > 0:
        points = sum(
            item["weight"]
            * {"MATCH": 1.0, "PARTIAL": 0.55, "MISMATCH": 0.0}[
                item["outcome"]
            ]
            for item in known_weighted
        )
        score: int | None = max(0, min(100, round(100 * points / known_weight)))
    else:
        score = None
    coverage = round(known_weight / total_weight, 4) if total_weight > 0 else 0.0
    gaps = [item["expected"] for item in evidence if item["outcome"] == "UNKNOWN"]
    conflicts = [
        item["observed_summary"]
        for item in evidence
        if item["outcome"] == "MISMATCH"
    ]
    reason_codes: list[str] = []
    if hard_gate == "FAIL":
        band = "NOT_RECOMMENDED"
        reason_codes.append("HARD_GATE_FAILED")
    elif hard_gate == "UNKNOWN":
        band = "INSUFFICIENT_EVIDENCE"
        reason_codes.append("HARD_GATE_NEEDS_EVIDENCE")
    elif coverage < rubric["minimum_coverage"] or score is None:
        band = "INSUFFICIENT_EVIDENCE"
        reason_codes.append("LOW_EVIDENCE_COVERAGE")
    elif score >= rubric["priority_threshold"]:
        band = "PRIORITY_REVIEW"
    elif score >= rubric["promising_threshold"]:
        band = "PROMISING_WITH_GAPS"
    else:
        band = "REVIEW_WITH_GAPS"
        reason_codes.append("LOW_JOB_RELATED_SCORE")
    if any(item["outcome"] == "UNKNOWN" for item in weighted):
        reason_codes.append("WEIGHTED_EVIDENCE_INCOMPLETE")
    candidate_ref = snapshot["candidate_ref"]
    return {
        "job_key": candidate_ref["job_key"],
        "candidate_key": candidate_ref["candidate_key"],
        "candidate_name": candidate_ref["display_name"].strip(),
        "snapshot_source": snapshot["source"],
        "snapshot_content_hash": snapshot["content_hash"],
        "candidate_information": candidate_information(snapshot["profile"]),
        "assessment": {
            "rubric_version": rubric["version"],
            "hard_gate": hard_gate,
            "score": score,
            "coverage": coverage,
            "band": band,
            "evidence": evidence,
            "reason_codes": reason_codes,
            "gaps": gaps,
            "conflicts": conflicts,
            "calculation": {
                "known_weight": known_weight,
                "total_weight": total_weight,
                "known_points": (round(points, 4) if known_weight > 0 else None),
                "formula": "round(100 * known_points / known_weight); UNKNOWN items excluded from score denominator",
            },
            "assessed_at": datetime.now(UTC).isoformat(),
        },
    }


def score_query(
    job_query: str,
    requirements_wrapper: dict[str, Any],
    *,
    candidate_query: str | None = None,
    limit: int = 50,
    job_context: dict[str, Any] | None = None,
    runtime_module: Any | None = None,
) -> dict[str, Any]:
    """Collect current BOSS Message evidence and score each named candidate."""

    if set(requirements_wrapper) != {"source_hash", "requirements"}:
        raise ScoringError(
            "INVALID_REQUIREMENTS",
            "requirements file must contain only source_hash and requirements",
            keys=sorted(requirements_wrapper),
        )
    source_hash = requirements_wrapper.get("source_hash")
    if not isinstance(source_hash, str) or not HASH_PATTERN.fullmatch(source_hash):
        raise ScoringError(
            "INVALID_REQUIREMENTS",
            "requirements source_hash must be SHA-256",
        )
    runtime_module = runtime_module or load_scoring_runtime()
    collected = runtime_module.collect_message_candidates(
        job_query,
        candidate_query=candidate_query,
        limit=limit,
        expected_source_hash=source_hash,
        job_context=job_context,
    )
    job_source = collected["job_source"]
    if source_hash != job_source.get("source_hash"):
        raise ScoringError(
            "STALE_JOB_SOURCE",
            "requirements were extracted from a different job description",
            expected=source_hash,
            current=job_source.get("source_hash"),
        )
    rubric = build_rubric(job_source, requirements_wrapper.get("requirements"))
    candidates = [
        score_candidate(snapshot, rubric)
        for snapshot in collected["candidate_snapshots"]
    ]
    return {
        "job": {
            "job_key": collected["job_ref"]["job_key"],
            "title": job_source["title"],
            "source": job_source["source"],
            "source_hash": job_source["source_hash"],
        },
        "rubric": {
            "version": rubric["version"],
            "requirements_hash": rubric["requirements_hash"],
            "criteria_count": len(rubric["criteria"]),
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
        "boss_launched": collected["boss_launched"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("runtime")
    commands.add_parser("inspect")
    context = commands.add_parser("job-context")
    context.add_argument("--job-query", required=True)
    query = commands.add_parser("score-query")
    query.add_argument("--job-query", required=True)
    query.add_argument("--candidate-query")
    query.add_argument("--requirements-file", required=True)
    query.add_argument("--job-context-file", required=True)
    query.add_argument("--limit", type=int, default=50)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "runtime":
            _, result = load_scoring_runtime().runtime()
        elif args.command == "inspect":
            runtime_module = load_scoring_runtime()
            candidate_module, provenance = runtime_module.runtime()
            from boss_candidates.ui.adapter import LiveBossAdapter

            result = {
                "runtime": provenance,
                "environment": LiveBossAdapter(
                    config=candidate_module.DEFAULT_CONFIG,
                    restart_for_accessibility=False,
                ).inspect_environment(),
            }
        elif args.command == "job-context":
            result = load_scoring_runtime().read_job_context(args.job_query)
        elif args.command == "score-query":
            cached_context = read_json(args.job_context_file)
            if cached_context.get("ok") is True and isinstance(cached_context.get("result"), dict):
                cached_context = cached_context["result"]
            result = score_query(
                args.job_query,
                read_json(args.requirements_file),
                candidate_query=args.candidate_query,
                limit=args.limit,
                job_context=cached_context,
            )
        else:
            raise ScoringError(
                "INVALID_COMMAND",
                "only runtime, inspect, job-context, and score-query are public",
            )
    except Exception as exc:
        details = (
            exc.as_dict()
            if callable(getattr(exc, "as_dict", None))
            else {"code": type(exc).__name__, "message": str(exc), "details": {}}
        )
        print(
            json.dumps({"ok": False, "error": details}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
