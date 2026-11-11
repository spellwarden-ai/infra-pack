# Spellwarden Infra Pack

Five agent skills for infrastructure operations, packaged as a plugin marketplace for Claude Code and as an extension for VS Code. They are free, open source (Apache-2.0) and published by Spellwarden.

The pack helps an agent, and the engineer working with it, review infrastructure changes and incidents with care: reach the right decision, ask for a person's approval before anything destructive, and point to the evidence.

## Install

Pin the install to the current version, 0.9.0. In Claude Code:

```
/plugin marketplace add spellwarden-ai/infra-pack#v0.9.0
/plugin install infra-pack@spellwarden
```

Or from a shell:

```
claude plugin marketplace add spellwarden-ai/infra-pack#v0.9.0
claude plugin install infra-pack@spellwarden
```

The pin matters. Released skills reach the `main` branch only in a release commit that raises the version, and a version pin keeps you on the text that was checked.

In VS Code 1.109 or later, install [Spellwarden Infra Pack](https://marketplace.visualstudio.com/items?itemName=spellwarden.infra-pack) (`spellwarden.infra-pack`) from the Visual Studio Marketplace, or from a shell, pinned the same way:

```
code --install-extension spellwarden.infra-pack@0.9.0
```

The agent loads a skill when your request matches its description. To ask for one by name, type `/` in chat and pick it.

## What each skill covers

| Skill | What it covers |
|---|---|
| `infra-change-safety` | Reviewing any infrastructure change, plan or incident before acting: reach the right decision, which may be that the change is sound; put a person's approval before any destructive or irreversible action; point to the lines the decision rests on; keep the actions to the few that matter. Use it next to the four below. |
| `terraform-plan-review` | Reading a Terraform or OpenTofu plan against the intent of the change: what is created, changed, replaced or destroyed, which of those lose data or identity, what a plan cannot show, and when it is safe to apply. |
| `kubernetes-incident-triage` | Triage of a Kubernetes workload, node or cluster problem from command output, events, logs and manifests: finding the cause the evidence supports, choosing the least disruptive next step, and recognising actions that lose data or availability. |
| `iam-least-privilege-review` | Review of AWS IAM policies for least privilege: what a policy really allows, what the workload needs, and changes that widen access beyond the need or open a path to escalation. |
| `ci-pipeline-repair` | Diagnosing and repairing failing or unsafe CI pipelines, GitHub Actions and GitLab CI first: finding the real cause, fixing it without disabling tests or protections, and keeping secrets, deploy rules and pins intact. |

Each skill is a single SKILL.md: no scripts, nothing that runs.

## How it is measured

Measured on 40 infrastructure tasks (Infra-Ops 40) with all five skills loaded: +15.0 points, 95% interval 3.6 to 26.4, over five runs, version 0.9.0, the first measurement of the pack on this suite. Details in [MEASUREMENTS.md](MEASUREMENTS.md), which also sets out how the pack is measured and what may be claimed from a measurement.

## Scan it yourself

The free Spellwarden scanner reads the skills the way a reviewer would. From a checkout of this repository:

```
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r tools/requirements.txt
.venv/bin/spellwarden scan plugins/infra-pack --fail-on low --no-telemetry
```

The pack is meant to pass with no finding at any severity.

## Working on the pack

The checks and tests need only the virtual environment above:

```
.venv/bin/python tools/check_pack.py
.venv/bin/python -m unittest discover -s tools/tests
```

`tools/lift.py` recomputes a published measurement from the evaluation runs it came from. It uses only the Python standard library.

A release commit raises the version in `plugin.json`, in every SKILL.md and in `package.json` together. Its tag `v<x.y.z>` also publishes the VS Code extension to the Visual Studio Marketplace (`.github/workflows/publish-vscode.yml`, trusted publishing, no stored token), once `tools/check_vsix.py` has checked that the package holds exactly the released files.

## Licence and security

Apache-2.0, see [LICENSE](LICENSE). To report a security problem, see [SECURITY.md](SECURITY.md).
