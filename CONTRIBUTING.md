# Contributing

## Branch Strategy

- `main` keeps the latest releasable state.
- New work starts from `main` and uses one of these prefixes:
  - `feat/<topic>`
  - `fix/<topic>`
  - `chore/<topic>`
  - `release/<version>`
- Do not push feature work straight to `main`.

## Pull Request Rules

- Open a pull request into `main`.
- Keep the pull request scoped to one change set.
- Release pull requests must update all three files together:
  - `VERSION`
  - `config/version.py`
  - `CHANGELOG.md`

## Required Checks Before Merge

- GitHub Actions job `django-test-and-build` must pass.
- At least one approval is required.
- All review conversations must be resolved.
- Code owner review is required for `main`.

## Release Flow

1. Create a release branch such as `release/1.3.6`.
2. Update `VERSION`, `config/version.py`, and `CHANGELOG.md`.
3. Open a pull request into `main`.
4. Merge after CI and review pass.
5. GitHub Actions will create the annotated tag `v<version>` automatically.
6. The tag push triggers the deployment workflow.

## Branch Protection Settings For `main`

Configure these options in GitHub repository settings:

- Require a pull request before merging.
- Require 1 approval.
- Dismiss stale pull request approvals when new commits are pushed.
- Require review from Code Owners.
- Require conversation resolution before merging.
- Require status checks to pass before merging.
- Required status check name: `django-test-and-build`
- Include administrators.
- Block direct pushes to `main`.

## Deployment Secrets

Configure these GitHub Actions secrets before enabling automatic deployment:

- `DEPLOY_HOST`
- `DEPLOY_PORT`
- `DEPLOY_USER`
- `DEPLOY_PROJECT_PATH`
- `DEPLOY_SSH_PRIVATE_KEY`
- `DEPLOY_KNOWN_HOSTS`
