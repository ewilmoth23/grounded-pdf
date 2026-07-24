# GroundedPDF release checklist

Use this checklist for `v0.1.0` and adapt it for later releases. Do not mark an item complete unless
the command or GitHub setting was actually verified for the release commit.

## 1. Repository state

- [ ] Initialize Git and review the complete first commit; this workspace currently has no `.git`
      metadata.
- [ ] Confirm `git status --short` contains only intentional release changes.
- [ ] Confirm `git ls-files` contains no `.env`, database, upload, model, cache, dependency, coverage,
      build, Playwright-result, or operating-system metadata files.
- [ ] Inspect staged content before committing: `git diff --cached --stat` and `git diff --cached`.
- [ ] Confirm the version is `0.1.0` in the API, web package, UI, and changelog.
- [ ] Confirm `CHANGELOG.md` has an accurate `v0.1.0` entry and `Unreleased` contains only later work.
- [ ] Confirm the MIT license, contribution guide, security policy, code of conduct, issue forms, and
      pull-request template are included.

Suggested hygiene checks:

```bash
git ls-files | rg '(^|/)(data|uploads?|models?|node_modules|dist|test-results|playwright-report)(/|$)|(^|/)\.env($|\.)|\.(db|sqlite|sqlite3|gguf|safetensors)$'
git grep -n -E '(/Users/|/Volumes/|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{16,})'
```

Both commands should return no sensitive or generated tracked content. Review every match; a regex is
not a substitute for human inspection.

## 2. Product evidence

- [ ] Generate the documented synthetic PDF with `make sample`.
- [ ] Confirm every README screenshot is a real capture from the release build and contains only the
      synthetic PDF. Do not use a design mockup as product evidence.
- [ ] Complete the README demo: upload, ready state, selected-document question, supported answer,
      page-2 navigation, insufficient-evidence answer, and deletion.
- [ ] Confirm README commands, defaults, ports, architecture, limitations, and roadmap still match the
      implementation.

## 3. Automated validation

- [ ] `make doctor`
- [ ] `make lint`
- [ ] `make test`
- [ ] `make build`
- [ ] `cd apps/web && npm run e2e`
- [ ] Clean Alembic upgrade, downgrade-to-base, re-upgrade, and `alembic check`
- [ ] `docker build --check ./apps/api`
- [ ] `docker build --check ./apps/web`
- [ ] `docker compose config --quiet`
- [ ] `make docker-verify`
- [ ] `npm --prefix apps/web audit --audit-level=high`
- [ ] `.venv/bin/python -m pip check`
- [ ] TODO: generate and commit a pinned Python lockfile (e.g. `uv lock` or
      `pip-compile pyproject.toml -o apps/api/requirements.lock`) and switch the API Dockerfile to
      install from it; `apps/api/requirements.runtime.txt` currently carries ranges, not pins.
- [ ] Run a Python dependency vulnerability scan and a container-image scan under the repository
      owner's approved disclosure policy.

Record exact results and warnings in the release notes. A skipped check is not a passing check.

## 4. Data and security review

- [ ] Start from a clean application volume or inspect existing records without deleting owner data.
- [ ] Confirm upload validation, selected-document retrieval, citation ownership, failure responses,
      loopback bindings, security headers, non-root containers, and complete deletion.
- [ ] Confirm logs, screenshots, fixtures, issue examples, and test reports contain no private document
      text, credentials, personal paths, or local endpoint secrets.
- [ ] Confirm `.env.example` contains placeholders/defaults only and `.env*` remains ignored except
      `.env.example`.
- [ ] Confirm the standard Docker image does not claim to include optional OCR.

## 5. GitHub repository settings

Recommended description:

> Local-first PDF research assistant with document-scoped retrieval, streamed answers, and
> application-verified page citations.

Recommended topics:

`pdf`, `rag`, `local-ai`, `ollama`, `fastapi`, `react`, `typescript`, `chromadb`, `docker`,
`ai-engineering`

- [ ] Set the description and topics above after confirming they match the published repository.
- [ ] Set the default branch to `main`.
- [ ] Enable private vulnerability reporting, Dependabot alerts, and dependency/security updates.
- [ ] Add branch protection requiring the backend, frontend, end-to-end, and Docker CI jobs.
- [ ] Require pull-request review and dismiss stale approvals after changes.
- [ ] Confirm issue forms and the pull-request template render correctly on GitHub.
- [ ] Add a CI badge only after the real repository URL and workflow run exist. Do not publish a badge
      for an unexecuted or renamed workflow. License/version badges must reflect actual project metadata.

## 6. Publish

- [ ] Push to a private repository first and inspect GitHub's rendered README, Mermaid diagram,
      screenshot, links, templates, language breakdown, and security tab.
- [ ] Wait for all required GitHub Actions jobs to pass on the exact release commit.
- [ ] Resolve or explicitly document vulnerability-scan findings.
- [ ] Create an annotated `v0.1.0` tag from the verified commit.
- [ ] Create the GitHub release from the `v0.1.0` changelog entry.
- [ ] Make the repository public only after the private review and hosted checks are complete.
- [ ] Re-run a clean clone setup following only the public README.

## Release sign-off

- Release commit:
- CI run:
- Reviewer:
- Release date:
- Known limitations reviewed: yes / no
- Public release approved: yes / no
