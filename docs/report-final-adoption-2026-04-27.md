# Report Final Adoption - 2026-04-27

## Purpose

This memo tracks which generated reports are safe to expose now, which ones are close but still need another genre-family tuning round, and which ones should stay out of the public list for now.

The decision rule stays simple:

1. Does the copy match the game's genre-family rather than falling back to generic wording?
2. Are `headline`, `good_for / not_good_for`, `top_strengths`, and `top_risks` readable enough for public exposure?
3. Are repeated failures coming from a reusable genre-family gap rather than a one-off game quirk?

## Adopt Now

These games are currently safe to expose in the public demo list.

- `698780` Doki Doki Literature Club!
- `255710` Cities: Skylines
- `427520` Factorio
- `646570` Slay the Spire
- `268500` XCOM 2
- `578080` PUBG: BATTLEGROUNDS
- `3551340` Football Manager 26
- `236850` Europa Universalis IV
- `1222670` The Sims 4
- `2456740` inZOI

Notes:
- `The Sims 4` and `inZOI` were promoted after the life-sim / social-sim tuning round.
- These reports are not perfect, but they are stable enough that genre mismatch is no longer the main concern.

## Partial / Hold

These games are usable as internal candidates, but they still show enough generic drift that they should not be promoted yet.

- `1145360` Hades
- `1091500` Cyberpunk 2077
- `289070` Sid Meier's Civilization VI
- `892970` Valheim
- `582010` Monster Hunter: World
- `1966720` Lethal Company
- `648800` Raft
- `570` Dota 2
- `548430` Deep Rock Galactic
- `413150` Stardew Valley
- `252490` Rust
- `1085660` Destiny 2
- `230410` Warframe
- `553850` HELLDIVERS 2
- `1174180` Red Dead Redemption 2
- `292030` The Witcher 3: Wild Hunt

Notes:
- `Destiny 2`, `Warframe`, and `HELLDIVERS 2` improved after the live-service tuning round, but they still need stronger headline / strength prioritization.
- `Red Dead Redemption 2` and `The Witcher 3` now read closer to narrative open-world games, but they still retain some generic or mismatched risk/headline phrasing.

## Do Not Adopt Yet

These reports still show structural genre-family gaps and should stay out of the public list until another tuning round lands.

- `1158310` Crusader Kings III
- `294100` RimWorld
- `105600` Terraria
- `359550` Rainbow Six Siege
- `730` Counter-Strike 2
- `440` Team Fortress 2
- `814380` Sekiro: Shadows Die Twice
- `1627720` Lies of P
- `1245620` ELDEN RING
- `3240220` Grand Theft Auto V Enhanced
- `271590` Grand Theft Auto V Legacy
- `346110` ARK: Survival Evolved

## Repeated Failure Patterns

The main recurring gaps across non-adopted reports are:

- `grand strategy / colony story management`
  - generic action or exploration wording still leaks into strategy-facing reports
- `looter shooter / live-service progression`
  - progression, farming, and build-loop language is still weaker than it should be
- `co-op live-service shooter`
  - cooperative mission / squad language still loses to generic gameplay copy too often
- `narrative open-world / immersive world`
  - strong story-world games still drift toward generic "play flow" or mismatched risk wording

## Recommended Operating Rule

Use this document as the source of truth for:

1. which games stay visible in the public catalog now
2. which games stay in the next genre-family tuning queue
3. which games are blocked until a larger subtype/fallback gap is addressed

## Revisit Trigger

Update this document when any of the following happens:

- a genre-family tuning round changes fallback / guardrail / priority behavior
- a hold game passes QA and is promoted into `Adopt Now`
- the public demo catalog changes
