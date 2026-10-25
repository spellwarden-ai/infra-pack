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
- Treat an integrity failure as possible tampering until shown otherwise. A released version's file should never change. Compare it with the checksum or signature its original publisher released, find out who changed the copy you download (mirror, proxy, cache), and never take the new pin value from the same source that served the changed file. Changing a pin is right only for a deliberate upgrade checked against the publisher.

## Fix without weakening

Do not make a failure go away by skipping, deleting or marking tests as expected to fail; setting `continue-on-error: true` or `allow_failure: true` on a required job; dropping a job from `needs`; lowering a coverage, severity or quality threshold; committing with `--no-verify`; removing a checksum, signature or scan step; replacing a pinned SHA or digest with a tag, a branch or `latest`; widening `permissions` to write-all; or merging past branch protection with an admin override or removing a required check. A truly flaky test is fixed, or quarantined with its owner's approval and a tracking issue, never silenced to get a release out.

## Required checks and blocked merges

- Branch protection and rulesets match required checks by exact name. A matrix job reports one check per combination, named like `test (ubuntu-24.04)`. Renaming a job or workflow, or adding a matrix, leaves the old required name unreported, so every pull request waits for it.
- A workflow skipped by a `paths` or `branches` filter also leaves its required checks pending, while a job skipped by its own `if` reports success.
- Fix the names, not the protection: update the required checks to the new names (a settings change the repository admin approves), or add a final job with the required name that `needs` the others, runs with `if: always()`, and fails unless every needed job succeeded.
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
- Pin third-party actions to a full commit SHA (`actions/checkout@<full commit SHA>` with the version in a comment) and images to a digest (`@sha256:<digest>`).

## Caches, runners and concurrency

- A cache is an optimisation, never a trusted input. Key it on the lock file, let only the install job write it (`pull-push`) and other jobs read it (`pull`), and install with lock-file checks (`npm ci`, `pip install --require-hashes`, a verified `go.sum`), which reject a package that does not match its recorded hash.
- GitHub scopes caches by branch: a pull request can restore the base branch's cache, but what it saves is not restored on the default branch. GitLab keeps separate caches for protected and unprotected branches by default (keys end in `-protected` or `-non_protected`). A cache change that keeps those boundaries and a lock-file install is sound.
- A concurrency group with `cancel-in-progress` (GitHub) or `interruptible` jobs (GitLab) must never cancel a running deploy or apply; give deploys their own group, or a `resource_group` in GitLab.
- When an unpinned runner image or tool changed under you, pin the last good version; do not loosen the check that caught it.

## Deploy and migration jobs

- A failed migration job: read the database error, then compare the schema version the database records with the one the release requires. Never mark a migration as applied that did not run (a "stamp" or "fake" command), and never deploy with the migration step skipped: the application would run against a schema it does not expect, and later migrations would build on a false history.
- Lock or timeout errors usually mean another session holds a lock. Find it with read-only queries (`pg_stat_activity` on PostgreSQL) and confirm it holds the lock (`pg_locks`, or `pg_blocking_pids()` during a retry); end that session only with its owner's approval, then re-run the job.
- Re-run a failed job once to tell a flaky failure from a real one; re-running until green is not a fix.

## Read-only commands

```
gh run list --workflow <file> --limit 5
gh run view <run-id> --log-failed
gh pr checks <number>
gh api repos/<owner>/<repo>/branches/main/protection/required_status_checks
glab ci view
glab ci trace <job-id>
git log --oneline -5 -- .github/workflows/ .gitlab-ci.yml
sha256sum -c checksums.txt
```

## Proposing the change

Give the edit as a short diff of the workflow or pipeline file, merged through a pull or merge request with its normal review. Changes to branch protection, rulesets, environments, protected variables or secrets need the repository or project admin's approval; re-running a deploy, ending database sessions or rotating secrets needs the owner's approval.
