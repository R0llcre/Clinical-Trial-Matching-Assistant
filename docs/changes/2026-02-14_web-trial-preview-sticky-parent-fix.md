# Why
On desktop (two-column) match results, the right-side **Trial preview** could scroll away instead of staying visible while the results list grows. This breaks side-by-side comparison.

# Changes
- Fixed the sticky container bounds for the right column so the preview can remain sticky for the full page scroll.
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/match-results/MatchResultsPage.module.css`
- Strengthened E2E coverage to assert the preview stays at a stable Y position after scrolling.
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/e2e/match-results-midwidth.spec.ts`

# Tests
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run build`
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run test:e2e`

# Deploy
- Web-only: build/push a new web image tag and update `ca-web-2baacc`.

# Rollback
- Web-only: activate the previous Container Apps revision for `ca-web-2baacc`.
