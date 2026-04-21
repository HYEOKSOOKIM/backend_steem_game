"""Template-based summary generation for review insights."""

from __future__ import annotations

from report.models.schemas import IssueSignal


def build_summary(
    issue_signals: dict[str, IssueSignal],
    *,
    sample_size_tier: str,
    trend_status: str,
) -> dict[str, str]:
    """Generate a compact, explainable summary without LLM dependency."""
    sorted_by_mentions = sorted(
        issue_signals.items(),
        key=lambda item: item[1].mention_count,
        reverse=True,
    )
    positive_candidates = sorted(
        issue_signals.items(),
        key=lambda item: (item[1].negative_ratio, -item[1].mention_count),
    )

    top_issue = sorted_by_mentions[0] if sorted_by_mentions else None
    top_positive = positive_candidates[0] if positive_candidates else None
    rising_issues = [
        category for category, signal in issue_signals.items() if signal.recent_trend == "up"
    ]

    return {
        "what_players_like": _build_positive_summary(top_positive, sample_size_tier),
        "what_players_dislike": _build_negative_summary(top_issue, sample_size_tier),
        "recent_change": _build_trend_summary(rising_issues, trend_status),
        "fit_for": _build_fit_summary(issue_signals, sample_size_tier),
        "risks": _build_risk_summary(top_issue, trend_status, sample_size_tier),
    }


def _build_positive_summary(
    top_positive: tuple[str, IssueSignal] | None,
    sample_size_tier: str,
) -> str:
    if top_positive is None:
        return "현재 수집된 한국어 리뷰 기준으로 뚜렷한 강점 신호는 아직 부족합니다."

    category, signal = top_positive
    if signal.negative_ratio >= 0.5:
        return "현재 수집된 한국어 리뷰 기준으로 강점보다 문제 신호가 더 두드러집니다."

    themes = ", ".join(signal.themes[:2]) or category
    prefix = _sample_prefix(sample_size_tier)
    return f"{prefix}상대적으로 긍정 신호가 보이는 영역은 {category}이며, 대표 테마는 {themes}입니다."


def _build_negative_summary(
    top_issue: tuple[str, IssueSignal] | None,
    sample_size_tier: str,
) -> str:
    if top_issue is None:
        return "현재 수집된 한국어 리뷰 기준으로 반복되는 불만 신호는 아직 확인되지 않았습니다."

    category, signal = top_issue
    themes = ", ".join(signal.themes[:2]) or category
    prefix = _sample_prefix(sample_size_tier)
    return f"{prefix}가장 자주 언급되는 불만 영역은 {category}이며, 대표 테마는 {themes}입니다."


def _build_trend_summary(rising_issues: list[str], trend_status: str) -> str:
    if trend_status == "limited":
        return "최근 리뷰 수가 적어 추세 해석은 제한적으로만 참고해야 합니다."

    if not rising_issues:
        return "최근 기간에는 특정 카테고리의 급격한 변화보다 전반적인 유지 신호가 보입니다."

    joined = ", ".join(rising_issues[:3])
    return f"최근 기간에는 {joined} 관련 언급이 상대적으로 증가하는 흐름이 보입니다."


def _build_fit_summary(
    issue_signals: dict[str, IssueSignal],
    sample_size_tier: str,
) -> str:
    categories = set(issue_signals)
    prefix = _sample_prefix(sample_size_tier)

    if {"difficulty", "controls"} & categories:
        return f"{prefix}초반 진입 장벽이나 조작 적응 여부를 중요하게 보는 플레이어는 사전 확인이 필요합니다."
    if {"story", "graphics"} & categories and "performance" not in categories:
        return f"{prefix}연출과 분위기 중심 경험을 기대하는 플레이어에게 더 잘 맞을 가능성이 있습니다."

    return f"{prefix}현재 표본만으로 특정 플레이어 유형에 대한 적합성을 단정하기보다는 대표 리뷰를 함께 확인하는 편이 안전합니다."


def _build_risk_summary(
    top_issue: tuple[str, IssueSignal] | None,
    trend_status: str,
    sample_size_tier: str,
) -> str:
    prefix = _sample_prefix(sample_size_tier)
    if top_issue is None:
        return f"{prefix}현재 표본에서는 뚜렷한 운영 리스크가 반복적으로 드러나지 않습니다."

    category, signal = top_issue
    if trend_status == "limited":
        return f"{prefix}{category} 관련 신호가 보이지만 표본이 작아 우선순위를 단정하기는 어렵습니다."

    if signal.recent_trend == "up":
        return f"{prefix}{category} 관련 불만이 최근 구간에서 상대적으로 증가하고 있어 추적이 필요합니다."

    return f"{prefix}{category} 관련 이슈는 반복적으로 언급되지만 최근 급격한 악화 신호는 제한적입니다."


def _sample_prefix(sample_size_tier: str) -> str:
    if sample_size_tier in {"very_small", "small"}:
        return "현재 수집된 한국어 리뷰 표본 기준으로 "
    return ""

