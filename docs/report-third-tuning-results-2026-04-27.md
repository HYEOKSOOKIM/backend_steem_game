# Report Third Tuning Results (2026-04-27)

This note captures the practical outcome of the third tuning pass after
re-running representative games and checking real generated report copy.

## Scope

Validation covered these genre clusters:

- visual novel / narrative-only
- city builder / urban management
- automation / factory optimization
- card deckbuilding / run planning
- turn-based tactical pressure

Representative games used during QA:

- `Doki Doki Literature Club!`
- `Cities: Skylines`
- `Factorio`
- `Slay the Spire`
- `XCOM 2`

## What Improved

### 1. Genre-mismatch copy dropped sharply

Examples that were reduced or removed:

- visual novels no longer drifting into combat / matchmaking wording
- city builders no longer drifting into combat / movement-flow wording
- automation games no longer drifting into server / matchmaking wording
- deckbuilders no longer drifting into open-world / exploration wording
- turn-based tactics no longer drifting into generic exploration wording as often

### 2. Player-fit copy became more genre-aware

Representative examples after tuning:

- `서사와 감정선에 깊게 몰입하는 플레이어`
- `도시를 키우며 흐름을 다듬는 운영형 플레이어`
- `자동화 라인을 다듬으며 효율을 올리는 플레이어`
- `한 판마다 덱 조합과 경로 선택을 즐기는 플레이어`
- `한 턴의 판단 무게를 즐기는 전술형 플레이어`

### 3. Final polish now blocks more generic drift

The final language polish stage now:

- rewrites genre-incompatible player-fit phrases
- blocks genre-incompatible titles and summaries
- removes duplicated strength titles
- rewrites a few repeated generic fallback phrases into better
  genre-specific alternatives for:
  - automation
  - deckbuilder
  - turn-based tactics

## Remaining Gaps

The main remaining issue is no longer major genre mismatch. The remaining issue
is **generic fallback language**.

Most common residue:

- `계속 손에 붙는 핵심 플레이 감각`

This phrase is now rewritten in more places, but the broader fallback system
still leans on general gameplay wording too often when the deterministic signal
is weak.

## Practical QA Verdict

### Pass

- DDLC
- Cities: Skylines

### Pass, with light generic residue

- Factorio
- Slay the Spire
- XCOM 2

Interpretation:

- the subtype structure is working
- the fallback and guardrail layers are meaningfully better
- future work should focus more on fallback copy quality than on large subtype expansion

## Recommended Next Step

Do **not** jump straight into another large subtype pass.

Prefer this order:

1. keep the current subtype set stable
2. polish shared fallback copy tables
3. add spot QA when a new genre cluster actually fails

## Files Most Responsible For The Improvement

- `backend/report/services/player_fit_mapper.py`
- `backend/report/services/report_view.py`
- `backend/report/services/report_writer_llm.py`
- `backend/tests/test_player_fit_mapper.py`
- `backend/tests/test_report_view.py`

## Summary

The third tuning pass is good enough to treat as a successful structural pass.
The system is now much better at saying the **right kind of thing** for a genre.

The next layer of improvement is mostly about saying it in a **less generic**
way, not about rebuilding the genre model again.
