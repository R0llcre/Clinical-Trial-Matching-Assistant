# Why
- Match results cards sometimes wrap the `Score` / `Certainty` labels on smaller viewports, which makes the header feel inconsistent and less professional.
- The demo experience lacks a few “perfect match” examples that reliably showcase a **Strong match** end-to-end.

# Changes
- Web: prevent wrapping for result metrics labels/values.
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/styles/globals.css`
- Web: add 3 “Perfect match example” demo profiles (synthetic) that reliably produce at least one **Strong match** in preview.
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/match/MatchPage.tsx`
- Web: hide synthetic “hidden” profile entries from Patients UI by filtering a reserved prefix (`__hidden__:`).
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/lib/profile/hidden.ts`
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/patients/PatientDetailPage.tsx`
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/patients/PatientEditPage.tsx`

# Tests
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run build`
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run test:e2e`

# Deploy
- Web only (`ca-web-2baacc`): build and deploy the updated web image.

# Rollback
- Re-activate the previous Azure Container Apps revision for `ca-web-2baacc`.

