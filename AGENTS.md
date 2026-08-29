# Production Worktree Guard

`production-long-items-2026-08-29` is the verified production checkpoint.

- Treat this branch as read-only for all agents and humans by default.
- Do all investigation, experiments, fixes, and Claude/Codex work on a new
  `codex/` branch created from this checkpoint.
- Never merge, cherry-pick, rebase, reset, or commit onto the production
  branch without the owner explicitly authorising that exact production edit.
- The installed Git pre-commit hook prompts for the production edit password
  before it permits a commit on this branch. The password itself is never
  stored in this worktree.
- Before any production deployment, build and run the applicable test suite;
  record the installed APK SHA-256 in the handover/commit message.
