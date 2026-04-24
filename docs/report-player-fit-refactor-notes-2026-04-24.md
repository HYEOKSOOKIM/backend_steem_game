# Report Player-Fit Refactor Notes (2026-04-24)

## Why we changed this

The old report pipeline mapped a broad `aspect` directly to buyer-facing copy.

That worked for rough summaries, but it failed badly for recommendation-style text:

- `gameplay` could mean boss fights, shooter gunplay, open-world exploration, survival loops, or tactical management
- the old mapping collapsed those into one fixed sentence
- as a result, games like PUBG could inherit soulslike-flavored copy such as "pattern learning" or "boss fight" language

## Judgment we made

We chose to add a **genre-aware subtype layer** instead of only patching a few hardcoded phrases.

Why:

1. The same coarse `aspect` value was feeding multiple outputs:
   - `good_for`
   - `not_good_for`
   - headline and timing seed copy
   - strengths and risks summaries
   - evidence titles and explanations
2. Fixing a single phrase table would leave the same genre mismatch in other cards.
3. The pipeline already had enough context at report-build time:
   - `genres`
   - `themes`
   - aspect evidence

## What changed

We introduced `player_fit_mapper.py` to infer a buyer-facing subtype from:

- `aspect`
- `theme`
- `genres`
- positive / negative stance

Examples:

- shooter / battle royale + gameplay -> `shooter_gunplay` or `survival_loot_loop`
- action RPG / soulslike + gameplay -> `boss_pattern_mastery`
- management / sports / simulation -> `tactical_management`

Those subtypes now influence:

- player-fit personas (`good_for`, `not_good_for`)
- strength / risk titles and summaries
- headline theme wording
- evidence titles
- evidence `why_it_matters` copy

## Additional judgment we made

### 1. Keep deterministic seeds, but make them safer

We did **not** hand all player-fit copy to the LLM.

Reason:

- the original problem started in deterministic seed generation
- if the seed is wrong, the LLM often inherits the wrong frame
- a safer deterministic layer keeps fallback behavior sane even when LLM generation is disabled or partially fails

### 2. Add genre-safe fallback when signals are weak

In some games, selected strengths or risks can be empty after thresholds are applied.

We chose to add **genre-aware default fallback sources** instead of a generic phrase like:

- "one more long-session player"
- "stress-sensitive player"

Reason:

- without this fallback, weak-signal games still fall back to generic or awkward copy
- genre-safe fallback is much better than a broad placeholder when no aspect survives selection

### 3. Stabilize player-fit phrases after LLM generation

We found that `good_for` / `not_good_for` could still become awkward after generation or proofread:

- `플레이어이다`
- `플레이어는`
- overly generic phrases like `...상황의 플레이어`

We chose to:

- tighten the core writer prompt
- disable LLM proofread for persona items
- normalize persona endings
- fall back to seed persona text if the generated phrase is too generic or malformed

Reason:

- persona items are short noun phrases, not prose
- LLM proofreading is useful for paragraph copy, but can harm compact persona labels

### 4. Be conservative with title normalization

We briefly tried removing more trailing particles from generated titles.

That removed some awkward endings, but it also damaged valid nouns like `플레이`.

We rolled that back and kept title normalization conservative:

- remove sentence endings like `입니다`, `이다`
- only trim obviously unfinished `는/은` endings
- do not trim `이/가` blindly

Reason:

- preserving valid nouns is more important than aggressive cleanup

## Tradeoffs we accepted

- We kept the taxonomy lightweight instead of introducing a brand-new stored schema.
- We infer subtypes at report-build time rather than redesigning the analysis artifacts first.
- This is less "pure" than a full schema redesign, but much safer to ship incrementally.

## Follow-up ideas

If we want to go further later:

1. Persist subtype candidates in the analysis layer
2. Add Steam tags alongside genres
3. Add evidence-consistency scoring so subtype confidence can be reduced when snippets do not support it
4. Move from fixed persona strings to signal-first structured data that the LLM realizes into final UI copy
