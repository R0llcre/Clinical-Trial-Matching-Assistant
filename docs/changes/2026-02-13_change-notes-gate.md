# M8 PR-6: Change Notes Gate

## Why
- 需要把“每次改动都写变更说明”从约定升级为强制门禁，避免遗漏。
- 让 review / 回归 / 发布时可以快速理解“为什么改、改了什么”。

## Changes
- 新增 `docs/changes/` 目录与模板文件。
- 新增 GitHub Actions workflow：PR 必须新增 `docs/changes/YYYY-MM-DD_*.md`，否则 CI 失败。

## Tests
- GitHub Actions: `change-notes` workflow on PR。

## Deploy
- 无需部署（仅 CI 与文档约束）。

## Rollback
- 回滚该 PR 即可移除门禁（不影响业务服务）。

