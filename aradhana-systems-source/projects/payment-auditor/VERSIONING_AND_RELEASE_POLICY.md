# Versioning and Release Policy

## 1. Branching Strategy

*   **`main` Branch:** Represents the **live stable** production environment. Code in this branch must always be deployable and fully verified.
*   **`develop` Branch:** Represents the **testing** environment. All new features and regular bug fixes are merged here for integration testing before a release.
*   **Release Branches:** Branched from `develop` when preparing for a new production release (e.g., `release/v1.2.0`). Used for final polishing, bug fixing, and stabilization before merging into `main`.
*   **Hotfix Branches:** Branched directly from `main` to address critical production issues (e.g., `hotfix/login-crash`). Once fixed, they are merged back into both `main` and `develop`.

## 2. Versioning Tags

We follow semantic versioning (SemVer) principles: `vMAJOR.MINOR.PATCH` (e.g., `v1.2.0`).
*   Tags are applied to commits on the `main` branch immediately after a merge from a release or hotfix branch.

## 3. Rollback Process

In the event of a critical failure following a deployment to production:
1.  **Identify the last stable tag:** Locate the most recent stable `vMAJOR.MINOR.PATCH` tag on the `main` branch prior to the failure.
2.  **Revert/Checkout:** Revert the changes or checkout the stable tag in the deployment environment to restore functionality.
3.  **Communication:** Notify stakeholders of the rollback and the reasons.
4.  **Investigation:** Investigate the root cause on `develop` or a dedicated bugfix branch, not directly on `main`.

## 4. Deployment Rules

*   **After-Hours Deployment Rule:** Production deployments (to the live environment) must **NOT** occur outside of standard business hours or immediately before weekends/holidays, unless it is an emergency hotfix. This ensures adequate staff is available to monitor and address potential issues post-deployment.

## 5. Stable Build Checklist

Before merging a release branch into `main` and deploying, the following checklist must be satisfied:
- [ ] All automated tests (unit, integration, e2e) pass successfully.
- [ ] No high or critical severity vulnerabilities reported by security scans.
- [ ] Code review completed and approved.
- [ ] QA sign-off obtained in the `develop` / staging environment.
- [ ] Database migrations (if any) have been tested and verified.
- [ ] Release notes have been generated and reviewed.
