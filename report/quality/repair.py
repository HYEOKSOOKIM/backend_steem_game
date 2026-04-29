"""Build dry-run repair plans for semantic report QA failures.

This module does not mutate report payloads. It turns semantic-gate failures
into explicit actions or holds so we can avoid regeneration loops and avoid
inventing unsupported copy.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .claim_ledger import build_claim_ledger
from .phrase_bank import build_phrase_bank
from .semantic_gate import evaluate_report_semantics
from .text_features import families, jaccard, tokens


AUTO_REPAIR_TYPES = {"duplicate_claim", "generic_copy", "theme_drift", "evidence_mismatch"}
HOLD_TYPES = {"unsupported_claim", "weak_support"}


def build_repair_plan(
    report_payload: dict[str, Any],
    *,
    semantic_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a dry-run repair plan for one generated report payload."""
    semantic = semantic_result or evaluate_report_semantics(report_payload)
    claims = build_claim_ledger(report_payload)
    claim_map = {str(claim.get("claim_id", "")): claim for claim in claims}
    phrase_bank = build_phrase_bank(claims)

    actions: list[dict[str, Any]] = []
    holds: list[dict[str, Any]] = []
    rewrite_sources: set[tuple[str, str]] = set()
    invalid_rewrite_claim_ids: set[str] = _mismatched_claim_ids(semantic)

    for failure in list(semantic.get("failures", []) or []):
        failure_type = str(failure.get("type", "")).strip()
        if failure_type == "duplicate_claim":
            action = _plan_duplicate_claim_action(failure, claim_map)
            if action:
                actions.append(action)
                claim_id = str(action.get("claim_id", "")).strip()
                if claim_id:
                    invalid_rewrite_claim_ids.add(claim_id)
            else:
                holds.append(_hold("duplicate_claim_unresolved", failure, "중복 claim을 안전하게 판정하지 못했습니다."))
            continue

        if failure_type == "generic_copy":
            action = _plan_copy_rewrite_action(failure, claims, phrase_bank)
            if action:
                source_hold = _rewrite_source_hold(action, failure, rewrite_sources, invalid_rewrite_claim_ids)
                if source_hold:
                    holds.append(source_hold)
                else:
                    actions.append(action)
            else:
                holds.append(_hold("generic_copy_unresolved", failure, "대체할 근거 phrase를 찾지 못했습니다."))
            continue

        if failure_type == "theme_drift":
            action = _plan_theme_drift_action(failure, claim_map, phrase_bank)
            if action:
                source_hold = _rewrite_source_hold(action, failure, rewrite_sources, invalid_rewrite_claim_ids)
                if source_hold:
                    holds.append(source_hold)
                else:
                    actions.append(action)
            else:
                holds.append(_hold("theme_drift_hold", failure, "연결 가능한 evidence claim이 부족합니다."))
            continue

        if failure_type == "evidence_mismatch":
            action = _plan_evidence_mismatch_action(failure, claim_map)
            if action:
                actions.append(action)
            else:
                holds.append(_hold(f"{failure_type}_hold", failure, _hold_reason(failure_type)))
            continue

        if failure_type == "evidence_theme_title_mismatch":
            action = _plan_evidence_theme_title_action(failure, claim_map)
            if action:
                actions.append(action)
            else:
                holds.append(_hold(f"{failure_type}_hold", failure, _hold_reason(failure_type)))
            continue

        if failure_type in HOLD_TYPES:
            holds.append(_hold(f"{failure_type}_hold", failure, _hold_reason(failure_type)))
            continue

        holds.append(_hold("unknown_failure_hold", failure, "알 수 없는 실패 유형이라 자동 수정하지 않습니다."))

    status = _plan_status(actions, holds, semantic)
    requires_review = any(str(action.get("safety_level")) == "review_required" for action in actions)
    return {
        "status": status,
        "can_apply_safely": bool(actions)
        and not holds
        and all(str(action.get("safety_level")) == "safe" for action in actions),
        "requires_review": requires_review,
        "semantic_status": semantic.get("status"),
        "failure_count": int(semantic.get("failure_count", 0) or 0),
        "critical_failure_count": int(semantic.get("critical_failure_count", 0) or 0),
        "action_count": len(actions),
        "hold_count": len(holds),
        "actions": actions,
        "holds": holds,
    }


def apply_safe_repair_actions(
    report_payload: dict[str, Any],
    repair_plan: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply only deterministic safe repair actions to a report payload.

    At the moment, the only safe action is dropping a duplicate evidence block.
    Text rewrites and evidence reselection remain review-only.
    """
    plan = repair_plan or build_repair_plan(report_payload)
    next_payload = deepcopy(report_payload)
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for action in list(plan.get("actions", []) or []):
        if str(action.get("safety_level", "")).strip() != "safe":
            skipped.append(_skip_action(action, "not_safe"))
            continue
        if str(action.get("action", "")).strip() != "drop_duplicate_claim":
            skipped.append(_skip_action(action, "unsupported_safe_action"))
            continue
        result = _apply_drop_duplicate_claim(next_payload, action)
        if result.get("applied"):
            applied.append(result)
        else:
            skipped.append(result)

    return next_payload, {
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "applied": applied,
        "skipped": skipped,
    }


def apply_review_repair_actions(
    report_payload: dict[str, Any],
    *,
    repair_plan: dict[str, Any] | None = None,
    llm_repairer: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply review-required repair actions using an optional LLM slot repairer.

    This keeps the existing report and edits only the fields that failed QA.
    Unsupported display claims are dropped deterministically when possible.
    """
    plan = repair_plan or build_repair_plan(report_payload)
    next_payload = deepcopy(report_payload)
    claims = build_claim_ledger(next_payload)
    claim_map = {str(claim.get("claim_id", "")): claim for claim in claims}
    phrase_bank = build_phrase_bank(claims)
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for hold in list(plan.get("holds", []) or []):
        result = _apply_supported_hold(next_payload, hold)
        if result.get("applied"):
            applied.append(result)
            continue
        llm_action = _plan_hold_llm_rewrite_action(hold, claims, phrase_bank)
        if llm_action and llm_repairer is not None:
            claim = _claim_for_action(llm_action, claims)
            repair_result = llm_repairer.repair_slot(
                report_payload=next_payload,
                repair_action=llm_action,
                claim=claim,
            )
            applied_result = _apply_llm_repair_result(next_payload, llm_action, repair_result)
            if applied_result.get("applied"):
                applied.append(applied_result)
                continue
            skipped.append(applied_result)
            continue
        if result.get("attempted"):
            skipped.append(result)

    for action in list(plan.get("actions", []) or []):
        safety_level = str(action.get("safety_level", "")).strip()
        if safety_level == "safe":
            continue
        if str(action.get("action", "")).strip() == "reselect_evidence_snippets":
            result = _apply_reselect_evidence_snippets(next_payload, action)
            if result.get("applied"):
                applied.append(result)
            else:
                skipped.append(result)
            continue
        if safety_level != "review_required":
            skipped.append(_skip_action(action, "unsupported_review_action"))
            continue
        if llm_repairer is None:
            skipped.append(_skip_action(action, "missing_llm_repairer"))
            continue
        claim = claim_map.get(str(action.get("claim_id", "")).strip())
        repair_result = llm_repairer.repair_slot(
            report_payload=next_payload,
            repair_action=action,
            claim=claim,
        )
        applied_result = _apply_llm_repair_result(next_payload, action, repair_result)
        if applied_result.get("applied"):
            applied.append(applied_result)
        else:
            skipped.append(applied_result)

    return next_payload, {
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "applied": applied,
        "skipped": skipped,
    }


def _apply_supported_hold(payload: dict[str, Any], hold: dict[str, Any]) -> dict[str, Any]:
    hold_type = str(hold.get("hold_type", "")).strip()
    field = str(hold.get("field", "")).strip()
    if hold_type not in {"unsupported_claim_hold", "weak_support_hold"}:
        return {
            "attempted": False,
            "applied": False,
            "reason": "unsupported_hold_type",
            "hold_type": hold_type,
            "field": field,
        }
    if not field:
        return {
            "attempted": False,
            "applied": False,
            "reason": "missing_field",
            "hold_type": hold_type,
        }
    result = _drop_display_field(payload, field, reason=hold_type)
    result["hold_type"] = hold_type
    return result


def _plan_hold_llm_rewrite_action(
    hold: dict[str, Any],
    claims: list[dict[str, Any]],
    phrase_bank: dict[str, list[str]],
) -> dict[str, Any] | None:
    hold_type = str(hold.get("hold_type", "")).strip()
    field = str(hold.get("field", "")).strip()
    if hold_type not in {"unsupported_claim_hold", "weak_support_hold"}:
        return None
    if field not in {"headline", "buy_timing_summary", "recent_state.summary"}:
        return None
    claim = _highest_support_claim(claims, stance=_field_stance(field))
    if claim is None:
        return None
    replacement = _rewrite_from_claim(field=field, claim=claim, phrase_bank=phrase_bank)
    return {
        "action": "rewrite_hold_field",
        "failure_type": str(hold.get("failure_type", "") or hold_type),
        "field": field,
        "claim_id": claim.get("claim_id"),
        "reason": "Rewrite a non-droppable display field using the strongest grounded claim.",
        "current_text": str(hold.get("text", "") or "").strip(),
        "replacement_text": replacement,
        "safety_level": "review_required",
        "requires_review": True,
    }


def _claim_for_action(action: dict[str, Any], claims: list[dict[str, Any]]) -> dict[str, Any] | None:
    claim_id = str(action.get("claim_id", "")).strip()
    if not claim_id:
        return None
    for claim in claims:
        if str(claim.get("claim_id", "")).strip() == claim_id:
            return claim
    return None


def _apply_llm_repair_result(
    payload: dict[str, Any],
    action: dict[str, Any],
    repair_result: Any,
) -> dict[str, Any]:
    if not isinstance(repair_result, dict):
        return _skip_action(action, "invalid_llm_result")

    mode = str(repair_result.get("mode", "")).strip().lower()
    field = str(repair_result.get("field") or action.get("field") or "").strip()
    if mode == "drop":
        result = _drop_display_field(payload, field, reason="llm_drop")
        result["llm_mode"] = mode
        return result
    if mode == "replace":
        value = repair_result.get("value")
        if field.startswith("evidence_sections."):
            result = _apply_evidence_block_value(payload, field, value)
            result["llm_mode"] = mode
            return result
        result = _apply_display_field_value(payload, field, value)
        result["llm_mode"] = mode
        return result
    return _skip_action(action, "unsupported_llm_mode")


def _apply_drop_duplicate_claim(payload: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    section = str(action.get("section", "")).strip()
    claim_id = str(action.get("claim_id", "")).strip()
    if section not in {"strengths", "risks"}:
        return _skip_action(action, "invalid_section")
    if not claim_id:
        return _skip_action(action, "missing_claim_id")

    evidence_sections = payload.get("evidence_sections")
    if not isinstance(evidence_sections, dict):
        return _skip_action(action, "missing_evidence_sections")
    blocks = evidence_sections.get(section)
    if not isinstance(blocks, list):
        return _skip_action(action, "missing_section")

    kept: list[Any] = []
    removed: list[dict[str, Any]] = []
    for block in blocks:
        if isinstance(block, dict) and str(block.get("block_id", "")).strip() == claim_id:
            removed.append(block)
            continue
        kept.append(block)

    if len(removed) != 1:
        return {
            **_skip_action(action, "target_not_unique"),
            "matched_count": len(removed),
        }

    evidence_sections[section] = kept
    return {
        "applied": True,
        "action": action.get("action"),
        "claim_id": claim_id,
        "keep_claim_id": action.get("keep_claim_id"),
        "section": section,
        "removed_title": removed[0].get("title"),
    }


def _apply_reselect_evidence_snippets(payload: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    claim_id = str(action.get("claim_id", "")).strip()
    section = str(action.get("section", "")).strip()
    selected = [str(item).strip() for item in list(action.get("replacement_text", []) or []) if str(item).strip()]
    if section not in {"strengths", "risks"}:
        return _skip_action(action, "invalid_section")
    if not claim_id or len(selected) < 2:
        return _skip_action(action, "missing_reselection_data")

    evidence_sections = payload.get("evidence_sections")
    if not isinstance(evidence_sections, dict):
        return _skip_action(action, "missing_evidence_sections")
    blocks = evidence_sections.get(section)
    if not isinstance(blocks, list):
        return _skip_action(action, "missing_section")

    matched = None
    for block in blocks:
        if isinstance(block, dict) and str(block.get("block_id", "")).strip() == claim_id:
            matched = block
            break
    if matched is None:
        return _skip_action(action, "claim_block_not_found")

    matched["evidence_snippets"] = selected[:3]
    _sync_evidence_reviews_from_sections(payload)
    return {
        "applied": True,
        "action": action.get("action"),
        "claim_id": claim_id,
        "section": section,
        "snippet_count": len(matched["evidence_snippets"]),
    }


def _drop_display_field(payload: dict[str, Any], field: str, *, reason: str) -> dict[str, Any]:
    report_display = payload.get("report_display")
    if not isinstance(report_display, dict):
        return {
            "attempted": True,
            "applied": False,
            "reason": "missing_report_display",
            "field": field,
        }

    if "[" not in field or not field.endswith("]"):
        return {
            "attempted": True,
            "applied": False,
            "reason": "drop_not_supported_for_field",
            "field": field,
        }

    group, index = _parse_indexed_field(field)
    if group not in {"good_for", "not_good_for", "top_strengths", "top_risks"} or index is None:
        return {
            "attempted": True,
            "applied": False,
            "reason": "drop_not_supported_for_field",
            "field": field,
        }

    items = report_display.get(group)
    if not isinstance(items, list):
        return {
            "attempted": True,
            "applied": False,
            "reason": "missing_display_list",
            "field": field,
        }

    zero_index = index - 1
    if zero_index < 0 or zero_index >= len(items):
        return {
            "attempted": True,
            "applied": False,
            "reason": "field_index_out_of_range",
            "field": field,
        }

    removed = items.pop(zero_index)
    _sync_display_mirrors(payload)
    return {
        "attempted": True,
        "applied": True,
        "action": "drop_field_item",
        "field": field,
        "reason": reason,
        "removed": removed,
    }


def _apply_display_field_value(payload: dict[str, Any], field: str, value: Any) -> dict[str, Any]:
    report_display = payload.get("report_display")
    if not isinstance(report_display, dict):
        return {
            "applied": False,
            "reason": "missing_report_display",
            "field": field,
        }
    if not field:
        return {
            "applied": False,
            "reason": "missing_field",
        }

    if field in {"headline", "buy_timing_summary"}:
        if not isinstance(value, str) or not value.strip():
            return {"applied": False, "reason": "invalid_string_value", "field": field}
        report_display[field] = value.strip()
        _sync_display_mirrors(payload)
        return {"applied": True, "action": "replace_field", "field": field}

    if field == "recent_state.summary":
        if not isinstance(value, str) or not value.strip():
            return {"applied": False, "reason": "invalid_string_value", "field": field}
        recent_state = dict(report_display.get("recent_state", {}) or {})
        recent_state["summary"] = value.strip()
        report_display["recent_state"] = recent_state
        _sync_display_mirrors(payload)
        return {"applied": True, "action": "replace_field", "field": field}

    group, index = _parse_indexed_field(field)
    if group in {"good_for", "not_good_for"}:
        if not isinstance(value, str) or not value.strip() or index is None:
            return {"applied": False, "reason": "invalid_string_value", "field": field}
        items = report_display.get(group)
        if not isinstance(items, list) or index < 1 or index > len(items):
            return {"applied": False, "reason": "field_index_out_of_range", "field": field}
        items[index - 1] = value.strip()
        _sync_display_mirrors(payload)
        return {"applied": True, "action": "replace_field", "field": field}

    if group in {"top_strengths", "top_risks"}:
        if not isinstance(value, dict) or index is None:
            return {"applied": False, "reason": "invalid_card_value", "field": field}
        title = str(value.get("title", "") or "").strip()
        summary = str(value.get("summary", "") or "").strip()
        if not title or not summary:
            return {"applied": False, "reason": "invalid_card_value", "field": field}
        items = report_display.get(group)
        if not isinstance(items, list) or index < 1 or index > len(items):
            return {"applied": False, "reason": "field_index_out_of_range", "field": field}
        items[index - 1] = {"title": title, "summary": summary}
        _sync_display_mirrors(payload)
        return {"applied": True, "action": "replace_field", "field": field}

    return {"applied": False, "reason": "unsupported_field", "field": field}


def _apply_evidence_block_value(payload: dict[str, Any], field: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"applied": False, "reason": "invalid_evidence_value", "field": field}
    title = str(value.get("title", "") or "").strip()
    why = str(value.get("why_it_matters", "") or "").strip()
    explanation = str(value.get("explanation", "") or "").strip()
    if not title or not why or not explanation:
        return {"applied": False, "reason": "invalid_evidence_value", "field": field}

    section_name, index = _parse_evidence_field(field)
    if section_name not in {"strengths", "risks"} or index is None:
        return {"applied": False, "reason": "unsupported_field", "field": field}
    evidence_sections = payload.get("evidence_sections")
    if not isinstance(evidence_sections, dict):
        return {"applied": False, "reason": "missing_evidence_sections", "field": field}
    blocks = evidence_sections.get(section_name)
    if not isinstance(blocks, list) or index < 1 or index > len(blocks):
        return {"applied": False, "reason": "field_index_out_of_range", "field": field}
    block = blocks[index - 1]
    if not isinstance(block, dict):
        return {"applied": False, "reason": "invalid_evidence_block", "field": field}
    block["title"] = title
    block["why_it_matters"] = why
    block["explanation"] = explanation
    _sync_evidence_reviews_from_sections(payload)
    return {"applied": True, "action": "replace_field", "field": field}


def _sync_display_mirrors(payload: dict[str, Any]) -> None:
    report_display = payload.get("report_display")
    if not isinstance(report_display, dict):
        return
    for key in (
        "headline",
        "buy_recommendation",
        "buy_timing_summary",
        "good_for",
        "not_good_for",
        "top_strengths",
        "top_risks",
        "recent_state",
    ):
        if key in payload:
            payload[key] = deepcopy(report_display.get(key))


def _sync_evidence_reviews_from_sections(payload: dict[str, Any]) -> None:
    evidence_sections = payload.get("evidence_sections")
    if not isinstance(evidence_sections, dict):
        return
    merged: list[dict[str, Any]] = []
    for section_name in ("strengths", "risks"):
        blocks = evidence_sections.get(section_name)
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            next_block = deepcopy(block)
            next_block["section"] = section_name
            merged.append(next_block)
    payload["evidence_reviews"] = merged


def _parse_indexed_field(field: str) -> tuple[str, int | None]:
    if "[" not in field or not field.endswith("]"):
        return field, None
    group, _, tail = field.partition("[")
    try:
        index = int(tail[:-1])
    except ValueError:
        return group, None
    return group, index


def _parse_evidence_field(field: str) -> tuple[str, int | None]:
    prefix = "evidence_sections."
    if not field.startswith(prefix):
        return field, None
    tail = field[len(prefix):]
    return _parse_indexed_field(tail)


def _skip_action(action: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "applied": False,
        "reason": reason,
        "action": action.get("action"),
        "claim_id": action.get("claim_id"),
        "section": action.get("section"),
        "safety_level": action.get("safety_level"),
    }


def _plan_status(
    actions: list[dict[str, Any]],
    holds: list[dict[str, Any]],
    semantic: dict[str, Any],
) -> str:
    if semantic.get("status") == "pass":
        return "no_repair_needed"
    if actions and holds:
        return "repairable_with_holds"
    if actions and any(str(action.get("safety_level")) == "review_required" for action in actions):
        return "repairable_needs_review"
    if actions:
        return "repairable"
    return "hold"


def _mismatched_claim_ids(semantic: dict[str, Any]) -> set[str]:
    claim_ids: set[str] = set()
    for failure in list(semantic.get("failures", []) or []):
        if str(failure.get("type", "")).strip() != "evidence_mismatch":
            continue
        claim_id = str(failure.get("claim_id", "")).strip()
        if claim_id:
            claim_ids.add(claim_id)
    return claim_ids


def _rewrite_source_hold(
    action: dict[str, Any],
    failure: dict[str, Any],
    rewrite_sources: set[tuple[str, str]],
    invalid_rewrite_claim_ids: set[str],
) -> dict[str, Any] | None:
    claim_id = str(action.get("claim_id", "")).strip()
    if claim_id in invalid_rewrite_claim_ids:
        hold = _hold(
            "invalid_rewrite_source_hold",
            failure,
            "이 claim은 같은 라운드에서 중복 제거 또는 evidence mismatch 대상이라 rewrite 근거로 재사용하지 않습니다.",
        )
        hold["claim_id"] = action.get("claim_id")
        hold["suggested_action"] = action.get("action")
        return hold

    key = _rewrite_source_key(action)
    if key is None:
        return None
    if key in rewrite_sources:
        hold = _hold(
            "duplicate_rewrite_source_hold",
            failure,
            "같은 claim 하나로 같은 슬롯군을 여러 번 채우면 문장이 반복되므로 자동 repair에서 제외합니다.",
        )
        hold["claim_id"] = action.get("claim_id")
        hold["suggested_action"] = action.get("action")
        hold["field_group"] = key[0]
        return hold
    rewrite_sources.add(key)
    return None


def _rewrite_source_key(action: dict[str, Any]) -> tuple[str, str] | None:
    if str(action.get("action", "")) not in {"rewrite_generic_copy", "rewrite_from_best_claim"}:
        return None
    claim_id = str(action.get("claim_id", "")).strip()
    field_group = _field_group(str(action.get("field", "")).strip())
    if not claim_id or field_group not in {"good_for", "not_good_for", "top_strengths", "top_risks"}:
        return None
    return (field_group, claim_id)


def _field_group(field: str) -> str:
    if "[" in field:
        return field.split("[", 1)[0]
    if "." in field:
        return field.split(".", 1)[0]
    return field


def _plan_duplicate_claim_action(
    failure: dict[str, Any],
    claim_map: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    claim_id = str(failure.get("claim_id", "")).strip()
    matched_id = str(failure.get("matched_claim_id", "")).strip()
    claim = claim_map.get(claim_id)
    matched = claim_map.get(matched_id)
    if not claim or not matched:
        return None

    claim_score = float(claim.get("support_score", 0.0) or 0.0)
    matched_score = float(matched.get("support_score", 0.0) or 0.0)
    drop_claim = claim if claim_score <= matched_score else matched
    keep_claim = matched if drop_claim is claim else claim
    return {
        "action": "drop_duplicate_claim",
        "failure_type": "duplicate_claim",
        "claim_id": drop_claim.get("claim_id"),
        "keep_claim_id": keep_claim.get("claim_id"),
        "section": drop_claim.get("section"),
        "reason": "같은 stance에서 같은 claim 제목이 반복되어 support가 낮거나 늦게 나온 block을 제거 후보로 표시합니다.",
        "current_text": drop_claim.get("title"),
        "replacement_text": None,
        "safety_level": "safe",
        "support_scores": {
            str(claim.get("claim_id")): claim_score,
            str(matched.get("claim_id")): matched_score,
        },
    }


def _plan_copy_rewrite_action(
    failure: dict[str, Any],
    claims: list[dict[str, Any]],
    phrase_bank: dict[str, list[str]],
) -> dict[str, Any] | None:
    field = str(failure.get("field", "")).strip()
    current_text = str(failure.get("text", "")).strip()
    stance = _field_stance(field)
    claim = _best_supported_claim(current_text, claims, stance=stance)
    if claim is None:
        claim = _highest_support_claim(claims, stance=stance)
    if claim is None:
        return None
    replacement = _rewrite_from_claim(field=field, claim=claim, phrase_bank=phrase_bank)
    if not replacement:
        return None
    return {
        "action": "rewrite_generic_copy",
        "failure_type": "generic_copy",
        "field": field,
        "claim_id": claim.get("claim_id"),
        "reason": "템플릿성 문구를 claim ledger와 phrase bank 기반 문구로 교체 후보 표시합니다.",
        "current_text": current_text,
        "replacement_text": replacement,
        "phrases_used": _top_phrases(claim, phrase_bank),
        "safety_level": "review_required",
    }


def _plan_theme_drift_action(
    failure: dict[str, Any],
    claim_map: dict[str, dict[str, Any]],
    phrase_bank: dict[str, list[str]],
) -> dict[str, Any] | None:
    best_claim_id = str(failure.get("best_claim_id", "")).strip()
    if not best_claim_id:
        return None
    best_score = float(failure.get("best_score", 0.0) or 0.0)
    if best_score < 0.08:
        return None
    claim = claim_map.get(best_claim_id)
    if claim is None:
        return None
    field = str(failure.get("field", "")).strip()
    replacement = _rewrite_from_claim(field=field, claim=claim, phrase_bank=phrase_bank)
    if not replacement:
        return None
    return {
        "action": "rewrite_from_best_claim",
        "failure_type": "theme_drift",
        "field": field,
        "claim_id": best_claim_id,
        "reason": "display 문장이 약하게 연결된 claim의 theme/phrase 기준으로 교체 후보를 만듭니다.",
        "current_text": str(failure.get("text", "")).strip(),
        "replacement_text": replacement,
        "best_score": round(best_score, 4),
        "phrases_used": _top_phrases(claim, phrase_bank),
        "requires_review": True,
        "safety_level": "review_required",
    }


def _plan_evidence_mismatch_action(
    failure: dict[str, Any],
    claim_map: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    claim_id = str(failure.get("claim_id", "")).strip()
    claim = claim_map.get(claim_id)
    if not claim:
        return None
    claim_families = set(claim.get("claim_families", set()) or set())
    if not claim_families:
        return None

    selected: list[str] = []
    seen: set[str] = set()
    for snippet in list(claim.get("evidence_candidate_snippets", []) or []):
        text = str(snippet).strip()
        if not text or text in seen:
            continue
        if claim_families & families(text):
            seen.add(text)
            selected.append(text)
        if len(selected) >= 3:
            break

    if len(selected) < 2:
        return None
    return {
        "action": "reselect_evidence_snippets",
        "failure_type": "evidence_mismatch",
        "claim_id": claim_id,
        "section": claim.get("section"),
        "reason": "현재 선택된 스니펫은 claim과 어긋나지만, 후보 스니펫 중 claim 주제와 맞는 근거가 있어 재선택 후보로 표시합니다.",
        "current_text": failure.get("text"),
        "replacement_text": selected[:3],
        "safety_level": "review_required",
        "requires_review": True,
    }


def _plan_evidence_theme_title_action(
    failure: dict[str, Any],
    claim_map: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    block_id = str(failure.get("block_id", "")).strip()
    field = str(failure.get("field", "")).strip()
    claim = claim_map.get(block_id)
    if not block_id or not field:
        return None
    return {
        "action": "rewrite_evidence_block_copy",
        "failure_type": "evidence_theme_title_mismatch",
        "field": field,
        "claim_id": block_id,
        "reason": "Rewrite only the evidence block copy so its title and explanation match the block theme.",
        "current_text": str(failure.get("text", "")).strip(),
        "replacement_text": {
            "title": str((claim or {}).get("title", "") or "").strip(),
            "why_it_matters": str((claim or {}).get("why_it_matters", "") or "").strip(),
            "explanation": str((claim or {}).get("why_it_matters", "") or "").strip(),
        },
        "safety_level": "review_required",
        "requires_review": True,
    }


def _rewrite_from_claim(
    *,
    field: str,
    claim: dict[str, Any],
    phrase_bank: dict[str, list[str]],
) -> Any:
    title = str(claim.get("title", "") or "").strip()
    theme = str(claim.get("theme", "") or "").strip()
    why = str(claim.get("why_it_matters", "") or "").strip()
    phrase = _top_phrase(claim, phrase_bank)
    anchor = title or theme or phrase
    anchor = _compact_title(anchor, positive=str(claim.get("stance", "")) == "positive")
    if not anchor:
        return None

    if field.startswith("top_strengths"):
        return {
            "title": _compact_title(title or anchor, positive=True),
            "summary": _claim_summary(why, phrase, positive=True),
        }
    if field.startswith("top_risks"):
        return {
            "title": _compact_title(title or anchor, positive=False),
            "summary": _claim_summary(why, phrase, positive=False),
        }
    if field.startswith("good_for"):
        return _fit_sentence(_fit_anchor(claim, fallback=anchor), positive=True)
    if field.startswith("not_good_for"):
        return _fit_sentence(_fit_anchor(claim, fallback=anchor), positive=False)
    if field == "headline":
        return f"{anchor} 관련 반응이 뚜렷해 이 지점을 중심으로 구매 판단을 보는 편이 좋습니다."
    if field == "recent_state.summary":
        return f"최근 리뷰에서도 {anchor} 관련 반응이 이어지고 있습니다."
    return None


def _compact_title(text: str, *, positive: bool) -> str:
    value = " ".join(str(text or "").split()).strip()
    replacements = (
        ("이 크다는 반응", "이 큰 점"),
        ("가 크다는 반응", "가 큰 점"),
        ("을 끊는다는 반응", "을 끊는 문제"),
        ("를 끊는다는 반응", "를 끊는 문제"),
        ("이 갈린다는 반응", "이 갈리는 지점"),
        ("가 갈린다는 반응", "가 갈리는 지점"),
    )
    for source, target in replacements:
        if value.endswith(source):
            return value[: -len(source)].strip() + target
    for suffix in ("이 있다.", "가 있다.", "있다는 반응이 있다.", "있다는 반응", "이라는 반응", "다는 반응", "반응"):
        if value.endswith(suffix):
            value = value[: -len(suffix)].strip()
            break
    if not value:
        return "근거가 뚜렷한 강점" if positive else "주의가 필요한 리스크"
    return value


def _fit_anchor(claim: dict[str, Any], *, fallback: str) -> str:
    theme = str(claim.get("theme", "") or "").strip()
    title = _compact_title(
        str(claim.get("title", "") or "").strip(),
        positive=str(claim.get("stance", "")) == "positive",
    )
    if theme and "/" not in theme:
        return theme
    return title or fallback


def _fit_sentence(anchor: str, *, positive: bool) -> str:
    value = " ".join(str(anchor or "").split()).strip()
    if not value:
        value = "근거가 확인된 항목"
    suffix_like = ("지점", "포인트", "리스크", "문제", "이슈", "부담", "불편")
    if positive:
        if value.endswith(suffix_like):
            return f"{value}{_object_particle(value)} 중요하게 보는 플레이어"
        return f"{value} 지점을 중요하게 보는 플레이어"
    if value.endswith(suffix_like):
        return f"{value}에 민감한 플레이어"
    return f"{value} 지점에 민감한 플레이어"


def _object_particle(value: str) -> str:
    if not value:
        return "을"
    last = value[-1]
    code = ord(last)
    if not (0xAC00 <= code <= 0xD7A3):
        return "을"
    return "을" if (code - 0xAC00) % 28 else "를"


def _claim_summary(why: str, phrase: str, *, positive: bool) -> str:
    if why:
        return why
    if phrase:
        if positive:
            return f"실제 리뷰에서 '{phrase}' 같은 표현이 보여 이 강점이 반복적으로 확인됩니다."
        return f"실제 리뷰에서 '{phrase}' 같은 표현이 보여 이 리스크를 확인할 필요가 있습니다."
    return "근거 리뷰와 연결된 항목입니다."


def _best_supported_claim(
    text: str,
    claims: list[dict[str, Any]],
    *,
    stance: str,
) -> dict[str, Any] | None:
    item_families = families(text)
    item_tokens = tokens(text)
    pool = claims if stance == "mixed" else [claim for claim in claims if claim.get("stance") == stance]
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for claim in pool:
        claim_families = set(claim.get("support_families", set()))
        claim_tokens = set(claim.get("support_tokens", set()))
        score = jaccard(item_families, claim_families) * 0.75 + jaccard(item_tokens, claim_tokens) * 0.25
        score += float(claim.get("support_score", 0.0) or 0.0) * 0.05
        if score > best[0]:
            best = (score, claim)
    return best[1]


def _highest_support_claim(claims: list[dict[str, Any]], *, stance: str) -> dict[str, Any] | None:
    pool = claims if stance == "mixed" else [claim for claim in claims if claim.get("stance") == stance]
    if not pool:
        return None
    return max(pool, key=lambda claim: float(claim.get("support_score", 0.0) or 0.0))


def _field_stance(field: str) -> str:
    if field.startswith("good_for") or field.startswith("top_strengths"):
        return "positive"
    if field.startswith("not_good_for") or field.startswith("top_risks"):
        return "negative"
    return "mixed"


def _hold(hold_type: str, failure: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "hold_type": hold_type,
        "safety_level": "hold",
        "failure_type": failure.get("type"),
        "field": failure.get("field"),
        "claim_id": failure.get("claim_id"),
        "reason": reason,
        "text": failure.get("text"),
        "failure": failure,
    }


def _hold_reason(failure_type: str) -> str:
    if failure_type == "unsupported_claim":
        return "근거 ledger에 없는 주장이라 자동으로 새 문장을 만들지 않습니다."
    if failure_type == "evidence_mismatch":
        return "evidence 제목/설명과 스니펫이 어긋나 claim 자체를 신뢰하기 어렵습니다."
    if failure_type == "weak_support":
        return "근거 강도가 약해 자동 승격하거나 수정하지 않습니다."
    return "자동 수정 금지 유형입니다."


def _top_phrase(claim: dict[str, Any], phrase_bank: dict[str, list[str]]) -> str:
    phrases = _top_phrases(claim, phrase_bank)
    return phrases[0] if phrases else ""


def _top_phrases(claim: dict[str, Any], phrase_bank: dict[str, list[str]], *, limit: int = 3) -> list[str]:
    claim_id = str(claim.get("claim_id", "")).strip()
    return [str(item) for item in list(phrase_bank.get(claim_id, []) or [])[:limit]]
