---
name: ci-pipeline-repair
description: Diagnose and repair failing or unsafe CI pipelines, GitHub Actions and GitLab CI first, from job logs, workflow files, branch protection and pipeline settings. Use it when a build, test, scan, migration or deploy job fails, when pull or merge requests are blocked by checks, when a cache, runner, dependency or checksum problem appears, or when a pipeline change touches secrets, tokens, permissions, deploy rules or pinned dependencies. It finds the real cause of a failure, fixes it without disabling tests, checks or protections, and keeps secrets, deploy rules and supply-chain pins intact.
license: Apache-2.0
metadata:
  version: "0.9.0"
  author: Spellwarden
---

# CI pipeline repair

A pipeline is part of the system's controls: its tests, scans, required checks, approvals and pins exist to stop bad changes. Repair the cause of a failure so that those controls still hold. A green pipeline reached by switching a control off is a failure that is now hidden.

## Find the real cause

- Read the log from the first error, not from the last line; the final message is often a consequence. Note the step, the command, the exit code and the exact message.
- Compare with the last green run of the same workflow: what changed in the commit, the workflow file, the runner image (`ubuntu-latest` moves), action and tool versions, the lock file, base images, secrets and variables, and repository settings such as branch protection, rulesets and environments.
- Classify the failure: a real regression in the code; a flaky test (fails and passes on the same commit); the environment (runner image, tool version, an unpinned dependency, network, rate limits); the configuration (YAML, job names, `needs`, `if` and `rules`, path filters); permissions (token scopes, protected variables, fork restrictions); or integrity (checksum, signature or lock file hash).
- Treat a checksum or signature failure as possible tampering, not a value to update. A released version's file never changes, at its publisher or at a copy, so a new checksum for the same version is itself the incident: check what the publisher released and how the copy you download (mirror, proxy, cache) came to differ, and never take a new value from the source that served the changed file. Change a pin only to move deliberately to a new version, checked against its publisher.

## Fix without weakening

Do not make a failure go away by skipping, deleting or marking tests as expected to fail; setting `continue-on-error: true` or `allow_failure: true` on a required job; dropping a job from `needs`; lowering a coverage, severity or quality threshold; removing a checksum, signature or scan step; replacing a pinned SHA or digest with a tag, a branch or `latest`; widening `permissions` to write-all; or merging past branch protection with an admin override or removing a required check. A truly flaky test is fixed, or quarantined with its owner's approval and a tracking issue, never silenced to get a release out.

## Required checks and blocked merges

- Branch protection and rulesets match required checks by exact name. A matrix job reports one check per combination, named like `test (linux)`. Renaming a job (its id or `name:`), or adding a matrix, leaves the old required name unreported, so merges wait for a check that never arrives.
- A workflow skipped by a `paths` or `branches` filter also leaves its required checks pending, while a job skipped by its own `if` reports success.
- Repair the naming rather than the rule: point the required checks at the names now reported (a settings change the repository admin approves), or add one job carrying the required name that `needs` the others, runs with `if: always()`, and fails unless all of them succeeded.
- With a merge queue, required workflows must also run on the `merge_group` event. Events caused by the workflow token (a bot push or a tag it creates) start no new workflow runs, so checks that never start may have that cause.
- An admin override or removing the check from the rule is not a fix: every later merge then goes through without that check.

## Secrets, tokens and permissions

- Set `permissions` per workflow or job to the least needed, read-only contents by default, and grant writes only to the job that needs them. For cloud access prefer OIDC (the permission `id-token` with the value write) and a cloud role whose trust pins the repository and the branch or environment, over long-lived keys stored as secrets.
- Pull requests from forks run on `pull_request` without secrets and with a read-only token. `pull_request_target` and `workflow_run` run with the base repository's secrets and a token that can write, so never check out and run the pull request's code in them.
- Do not place untrusted event fields (pull request titles, branch names, commit messages) directly inside a `run` script, where they become shell code; pass them through `env` and quote them.
- Never print a secret, or move one into the workflow file, a cache or an artifact; a secret that reached a log is rotated by its owner.
- GitLab: protected variables reach only pipelines on protected branches and tags, and masked variables are hidden in logs. A job that lacks a variable on a feature branch is working as designed: do not unprotect the variable.
- Production deploys sit behind protected environments: required reviewers and deployment branch rules in GitHub, protected environments and `rules` limited to the default branch or tags in GitLab. Moving a deploy out of its environment, or loosening its rules, to get past an approval weakens the control. In GitLab a `when: manual` job outside `rules` defaults to `allow_failure: true`, so later stages do not wait for it; a gate needs `allow_failure: false`.
- Self-hosted runners must not run pull request code from forks of a public repository: a job there can reach the runner's network and leave things behind for the next job.
- Pin third-party actions to a full commit SHA (`actions/checkout@<full commit SHA>` with the version in a comment) and images to a digest (`@sha256:<digest>`), because a tag or branch can be moved to other code; a SHA or digest cannot.

## Caches, runners and concurrency

- A cache is an optimisation, never a trusted input. Key it on the lock file, let one job write it and the rest only read it, and install with a lock-file check (`npm ci`, `pip install --require-hashes -r <file>`, a verified `go.sum`) that refuses a package whose hash differs from the recorded one.
- GitHub scopes caches by branch: a pull request can restore the base branch's cache, but what it saves is not restored on the default branch. GitLab keeps separate caches for protected and unprotected branches by default (keys end in `-protected` or `-non_protected`). A cache change that keeps those boundaries and a lock-file install is not a cross-branch poisoning risk on that ground.
- A concurrency group with `cancel-in-progress` (GitHub) or `interruptible` jobs (GitLab) must never cancel a running deploy or apply; give deploys their own group, or a `resource_group` in GitLab.
- When an unpinned runner image or tool changed under you, pin the last good version; do not loosen the check that caught it.

## Deploy and migration jobs

- A failed migration job: read the database error, then compare the schema version the database records with the one the release requires. Never mark a migration as applied that did not run (a "stamp" or "fake" command), and never deploy past a migration that did not run: the application would run against a schema it does not expect, and the recorded history would no longer match the schema.
- Lock or timeout errors usually mean another session holds a lock: identify the blocking session from the database's own lock views before ending it, with its owner's approval, then re-run the job.
- Re-run a failed job once to tell a flaky failure from a real one; re-running until green is not a fix.

## Read-only commands

```
gh run list --workflow <file> --limit 5
gh run view <run-id> --log-failed
gh pr checks <number>
gh api repos/<owner>/<repo>/branches/main/protection/required_status_checks
glab ci get
glab ci trace <job-id>
git log --oneline -5 -- .github/workflows/ .gitlab-ci.yml
sha256sum -c checksums.txt
```

## Proposing the change

Give the edit as a short diff of the workflow or pipeline file, merged through a pull or merge request with its normal review. Changes to branch protection, rulesets, environments, protected variables or secrets need the repository or project admin's approval; re-running a deploy, ending database sessions or rotating secrets needs the owner's approval.
