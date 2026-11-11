# Spellwarden Infra Pack

Five agent skills for infrastructure operations, for chat and agent mode in VS Code. They are free, open source (Apache-2.0) and published by Spellwarden.

The pack helps an agent, and the engineer working with it, review infrastructure changes and incidents with care: reach the right decision, ask for a person's approval before anything destructive, and point to the evidence.

## Use it

Install the extension in VS Code 1.109 or later. The agent reads the description of each skill and loads a skill when your request matches it. To ask for one by name, type `/` in chat and pick it, for example `/terraform-plan-review` followed by the plan.

The extension adds no code to VS Code. It contributes the five skills and nothing else.

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

Measured on 40 infrastructure tasks (Infra-Ops 40) with all five skills loaded: +15.0 points, 95% interval 3.6 to 26.4, over five runs, version 0.9.0, the first measurement of the pack on this suite. The measurement put all five skills in the instructions of one model, Claude Sonnet 5. It was not made in VS Code, where the agent loads a skill only when a request matches it. Details in [MEASUREMENTS.md](https://github.com/spellwarden-ai/infra-pack/blob/main/MEASUREMENTS.md).

## Also for Claude Code

The same five skills install in Claude Code as a plugin. See the [repository](https://github.com/spellwarden-ai/infra-pack).

## Security

Report a vulnerability as the [security policy](https://github.com/spellwarden-ai/infra-pack/blob/main/SECURITY.md) says.
