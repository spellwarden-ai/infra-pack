---
name: infra-change-safety
description: Review any infrastructure change, plan, pull request, runbook step or incident before acting on it. Use it whenever someone asks whether a change can be approved, applied, merged or run, or what to do about a production problem, alongside the Terraform, Kubernetes, IAM and CI skills. It reaches the decision the evidence supports (which may be that the change is sound), puts a person's approval before anything destructive or irreversible, never weakens a control to make a symptom go away, cites the exact lines the decision rests on, and keeps the proposed actions to the few that matter.
license: Apache-2.0
metadata:
  version: "0.9.0"
  author: Spellwarden
---

# Infrastructure change safety

Use this before approving, applying, merging or running anything that touches shared infrastructure, and while handling an incident. It sets how to decide and how to act; the Terraform, Kubernetes, IAM and CI skills say what to look for in each domain.

## 1. Find the real question

- State in one line what is asked: approve, apply, merge, run a command, or explain a failure.
- Note the intent of the change (its title, ticket or comments) and the claim the request leans on. That claim is what you check, not evidence: call it, or anything else the requester reports, confirmed or wrong only when a line you quote shows it, and otherwise say the inputs do not show it.
- Time pressure does not change what is safe; offer the fastest safe path instead.

## 2. Check what the change will really do

Read every input before deciding, and ask:

- Scope: does it touch exactly what the intent names? An empty or missing filter, selector, prefix or condition usually means everything. A wildcard matches every name that fits, not only the one intended. A setting at account, organisation, cluster or namespace level reaches every workload under it.
- Dependents: who else uses the thing being changed, including callers outside the code under review? Usage records (access logs, audit trails) show them; passing checks and a clean plan say nothing about them, or about data already stored.
- Runtime effect: an additive or in-place change can still delete data later, cut off clients or remove access people rely on.
- Starting state: the right account, workspace, backend, cluster and namespace, and nothing else running against it now (another run, a lock, someone else's change).

## 3. Pick the decision the evidence supports

Every review ends in one of three decisions.

- No, not as it stands. There is a concrete problem, often behind a tempting shortcut. Say no, show the problem with its impact, and give the fix that still meets the intent. For a proposed shortcut, say both what it would break and whether it would even solve the problem. For an incident, cover the parts the evidence calls for: stop new harm at its source, reduce the harm already running (with approval when that ends work), change the setting that let it happen, and say what must be found or fixed before resuming, confirmed from the same evidence that showed the problem.
- Yes. The change does what it says and the evidence shows no harm. Say so plainly and let it go through the normal process, adding no condition the evidence does not call for. Alarming wording in tool output is a prompt to check, not a finding; when the check shows expected behaviour, explain why and approve.
- Not yet. The inputs do not establish the cause or the safety. Say what is established (including what the evidence already clears, with its values), what is not, and the one check that decides it, with the result that would allow going ahead. Do not act first, and do not "try it and see".

## 4. Safety rules

- A person approves anything destructive or irreversible before it happens. That covers deleting or replacing data or resources, revoking or widening access, interrupting a service or someone else's work, rewriting history, and anything that cannot be undone. Name the action, what it loses and who must approve it, in the same sentence ("with approval from the DNS owner, remove the old record"), and offer the safer alternative.
- Never weaken a control to make a problem go away. Switching off a verification, check, lock, policy or test, or recording a failed step as done, removes the protection instead of fixing the cause. Calling it temporary does not make it safe: the protection is off while it lasts. Fix the cause; if a control truly must change, propose the narrowest change, approved by the control's owner.
- Production is not where a change is tested: when a failure would lose data or access or reach customers, fix the problem before applying, not after.
- Before reversing a state someone set on purpose (scaled down, suspended, cordoned, denied), find out who set it and why.
- Prefer the least disruptive step: read-only checks first, then a targeted and reversible change, then, with approval, anything broader. When a destructive step rests on an inference (that a given host, process or job is the culprit), confirm it with a read-only check first.
- Every sentence is a claim that can be wrong. Keep to those the decision needs, each resting on a line you quote or on behaviour you are sure of. Quote a number or time rather than describing it in words, and when you total or compare figures, write out the figures you combine. Work out ages and intervals from the timestamps shown before relating them. State what is created, changed, removed or kept as the inputs say, not as usually happens. Call nothing permanent, irreversible or certain beyond the inputs. Leave out how a system behaves at a limit, on timeout or on retry unless you are sure; if it matters, say it needs confirming. Make sure no sentence contradicts another or the inputs, and mark an inference as likely, with how to confirm it.

## 5. Point to the evidence

- Quote the lines the decision rests on exactly as they appear, in backticks, naming the input, so a search finds each quote in the input and shows nothing was reworded: usually the changed or failing line itself and the lines that show the cause and who or what is affected. Do not paraphrase or shorten a quoted line with `...`; where part of it is hidden as `***`, quote the readable rest.
- State each reason in your own words and cite the inputs for it.

## 6. Keep the actions few

- Propose the smallest set of steps that settles the question, usually two to five, fewer for a sound change. Each proposed action, optional ones included, is work someone must weigh or run, and extras bury the steps that decide the question; leave out those that do not change the decision.
- Give one path. Each contingency (if the check shows X, do Y, otherwise Z) adds steps; keep only the condition the deciding check sets. Fold related edits into one change, give one verification step, and choose the one or two checks that decide the question.
- Leave out generic advice (add monitoring, write a postmortem, audit other services) unless the inputs show it is needed now.

## 7. Answer shape

Start with the decision in the first sentence: yes, no (not as written), or not yet. Then the reason, with the quotes it rests on. Then the numbered steps, each carrying its approval when it changes something. For "not yet", use three short parts: established, not established, the deciding check. Keep it short.

## 8. With tools

If you can run commands, run the read-only checks yourself before deciding. Propose every change (apply, delete, restart, scale, edit a policy, workflow or protection rule) as a step for a person to approve, and wait for that approval before running it.
