# Subtype Tuning Checklist

This note is a guardrail against drifting into game-by-game tuning.

The goal is **not** to memorize individual games. The goal is to use each game
as a sample that reveals whether a reusable genre or play-pattern layer is
missing.

## Core Rule

Treat each game as a **signal**, not as a custom exception.

If a report sounds wrong, ask:

- is this a one-off game quirk?
- or is this exposing a missing reusable play-pattern subtype?

Only the second case should lead to subtype design changes.

## Checklist

### 1. Is this a game-cluster problem rather than a single-game problem?

Ask:

- Would this wording failure likely show up in similar games?
- Is the failure tied to a broad play pattern or genre family?

If yes:
- candidate for subtype or fallback tuning

If no:
- do **not** add a game-specific rule

Examples:

- `CK3` failing to express dynasty / relationship / ruler-play
  - likely a reusable strategy-roleplay cluster
- one specific DLC price complaint in one game
  - not a subtype problem

### 2. Can the current subtype structure already explain it?

Ask:

- Is the subtype correct, but the wording is too generic?
- Or is the system choosing the wrong subtype entirely?

If wording is generic:
- prefer prompt tuning or fallback copy tuning

If the subtype is wrong:
- consider subtype priority changes or subtype expansion

### 3. Would buyer-facing copy actually change in a meaningful way?

New subtype work is justified only when user-facing language should genuinely
be different.

Good candidates:

- `city_builder_management`
- `turn_based_tactical_pressure`
- `automation_factory_optimization`

Weak candidates:

- internal distinctions that produce almost the same external copy

### 4. Is this really just a forbidden-phrase problem?

Before adding a subtype, check whether the issue is simply that obviously wrong
phrases are leaking through.

Examples:

- city builder mentioning `전투/이동 흐름`
- visual novel mentioning `매칭`

These should be handled by guardrails first.

### 5. Is this actually a fallback-copy problem?

Sometimes the subtype is fine and the problem is just a weak generic phrase.

Examples:

- `핵심 플레이 감각`
- `손에 익을수록 재미가 커진다`

In these cases:
- tune shared fallback copy first
- avoid adding a new subtype too early

### 6. Could this change damage nearby genres?

Every subtype or mapping change should be checked for spillover.

Questions:

- Will this pull unrelated games into the new subtype?
- Will this weaken existing successful mappings?

Examples:

- broadening `전술` too much can blur:
  - Football Manager
  - XCOM
  - Civilization

If spillover risk is high:
- prefer narrower signals
- prefer fallback tuning before subtype expansion

### 7. Is the subtype named after a play pattern, not a game?

Good:

- `visual_narrative_immersion`
- `automation_factory_optimization`
- `turn_based_tactical_pressure`

Bad:

- `ck3_dynasty_mode`
- `destiny_loot_mode`
- `witcher_story_mode`

Subtype names should describe reusable player-facing play patterns, not titles.

## Recommended Decision Order

When a report looks wrong, check in this order:

1. Is it a forbidden-phrase leak?
2. Is it a generic fallback-copy problem?
3. Is it a subtype priority / mapping problem?
4. Only then ask whether a new subtype is needed.
5. If a new subtype is needed, confirm it applies to a reusable game family.

## Practical Interpretation

Games are QA samples.

The code should evolve at the level of:

- genre families
- play-pattern clusters
- deterministic guardrails
- reusable fallback copy

It should **not** evolve into a growing pile of title-specific exceptions.

## One-Sentence Summary

Use games to discover missing reusable play-pattern abstractions, not to justify
game-specific tuning rules.
