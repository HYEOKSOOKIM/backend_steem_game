# Review Required Decisions - 2026-04-29

Source files:

- `backend/data/report/reports/report_repair_plan.json`
- `backend/data/report/reports/report_review_required_queue.md`

This note records the operator decision for review-required QA items. It is intentionally separate from the generated queue so the queue can keep being regenerated without losing the human judgment trail.

## Summary

| Appid | Game | Decision | Result |
| --- | --- | --- | --- |
| `1174180` | Red Dead Redemption 2 | Accept evidence reselection cleanup | Semantic gate pass; keep exposed |
| `578080` | PUBG: BATTLEGROUNDS | Hold | Needs evidence reselection before promotion |
| `3551340` | Football Manager 26 | Hold | Needs stronger positive evidence before promotion |

## Red Dead Redemption 2

Decision: accept evidence reselection cleanup and keep it in the public exposure set.

Why:

- The display copy now has two evidence-backed strengths: story/character resonance and open-world/visual atmosphere.
- The display copy now has two evidence-backed risks: bugs/loading/online friction and slow controls/pacing.
- Unsupported extra strength/risk blocks were removed instead of being patched with game-specific hardcoded claims.
- The semantic gate now reports `pass` with `0` failures.
- `backend/docs/report-final-adoption-2026-04-27.md` already lists it under `Adopt Now`.
- `backend/data/report/catalog/demo_games.json` already has `1174180` enabled.

Operational outcome:

- No additional exposure-list edit is needed.
- Red Dead Redemption 2 should not remain in the review-required queue.

## PUBG: BATTLEGROUNDS

Decision: hold.

Why:

- The positive evidence block `str_1` is marked as `evidence_mismatch`.
- Visible strength copy includes unsupported topics such as equipment/build progression and ongoing content updates.
- The suggested repair would rely on a claim that is already invalid as a rewrite source, so applying it would only hide the problem.

Next action:

- Rebuild or reselect positive evidence first.
- Do not promote until the strength ledger has at least one clean, display-ready positive claim.

## Football Manager 26

Decision: hold.

Why:

- The current positive side depends too heavily on one weak `str_1` claim.
- Multiple visible strengths are trying to reuse that same claim, which would create repetitive and generic copy.
- The remaining issue is not a wording polish problem; it is a missing-evidence/material problem.

Next action:

- Rebuild or reselect positive evidence before attempting another display repair.
- After reselection, rerun semantic gate and only apply safe repairs if the claim ledger has distinct support for each visible strength.
