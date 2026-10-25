---
name: terraform-plan-review
description: Review a Terraform or OpenTofu plan, in text or JSON, against the stated intent of the change before it is approved or applied. Use it when someone asks whether a plan or an infrastructure pull request is safe to apply, when a plan shows replacements, destroys or a surprising number of creates, after a refactor, backend, state, workspace or provider change, or when an apply fails on state or locking. It reads what will be created, changed, replaced or destroyed, finds the changes that lose data or identity, checks that refactors touch no real resources, names what a plan cannot show, and says when the plan is safe to apply.
license: Apache-2.0
metadata:
  version: "0.9.0"
  author: Spellwarden
---

# Terraform and OpenTofu plan review

A plan is Terraform's prediction of the API calls it will make, computed from the configuration and the state it read. Review it line by line against the intent of the change, and then against what it cannot see. Everything here applies to OpenTofu with `tofu` in place of `terraform`.

## Read the plan

- Symbols: `+` create, `-` destroy, `~` update in place, `-/+` destroy then create (replace), `+/-` create then destroy (replace under `create_before_destroy`), `<=` read a data source. `# forces replacement` marks the attribute that causes a replacement.
- The summary `Plan: A to add, C to change, D to destroy` counts each replacement in both add and destroy. Compare it with the intent: a one-line change that adds dozens of resources, or a refactor that destroys anything, is wrong until explained.
- `(known after apply)` is a value computed during the apply. When a resource's own ID or ARN becomes unknown it is being replaced, and resources that refer to it change or are replaced too; follow them.
- "Objects have changed outside of Terraform" lists drift found on refresh. The apply will push the configuration back over it, so find out who changed it and why before reverting their change; to accept it instead, update the configuration, or record it with a reviewed `terraform apply -refresh-only`.
- JSON (`terraform show -json tfplan`): each `resource_changes[].change.actions` is `["create"]`, `["update"]`, `["delete"]`, `["delete","create"]`, `["create","delete"]`, `["read"]` or `["no-op"]`. `replace_paths` lists the attributes forcing replacement and `action_reason` says why. Compare `before` with `after`; `after_unknown` marks computed values.
- `(sensitive value)` hides content; say the plan does not show it rather than guessing.

## Match every change to the intent

- List each resource address with its action and ask whether the intent explains it. An unexplained change blocks approval until it is explained.
- Check the scope of what is added or changed. A rule or policy with an empty or missing filter, prefix, selector or condition applies to everything it can reach: a storage lifecycle or retention rule without a prefix or tag filter, a firewall rule open to `0.0.0.0/0`, a policy on `*`. A code comment, variable name or PR title is not the scope; the configuration is.
- An omitted argument takes the provider's default, which may not be what the author assumes.
- Changing a resource name, a module address, `count` to `for_each`, or the keys of a `for_each` re-keys resources: Terraform destroys the old address and creates a new one unless a `moved` block or a state move maps them. Removing one item from a list used with `count` shifts every later index, so those resources change or are replaced; stable `for_each` keys avoid it.
- A plan can change with no code change when an input moves: a data source that picks the latest image, a module or provider version range, a module source on a branch. Pin them, and treat a replacement they cause as a change to review.

## Changes that lose data or identity

Replacing or destroying these loses something the new resource does not bring back:

- Stored data: database instances and clusters, volumes and snapshots, buckets and their objects, file systems, tables, queues holding messages, log groups.
- Identity: a new ID, ARN, IP, DNS name or certificate for something others refer to, such as a role named in trust or resource policies, a load balancer, an elastic IP, an endpoint, or an encryption key that existing data depends on.
- Protections switched off in the same change: `deletion_protection = false`, `skip_final_snapshot = true`, `force_destroy = true`, a removed `prevent_destroy`, shorter backup, log or object retention, versioning suspended, a deletion or recovery window cut to the minimum.

Such a plan is not safe to apply until the intent explains it, a backup or snapshot exists and is checked, the consumers are known, and an owner explicitly approves the loss. With `create_before_destroy`, a replacement whose name must be unique fails or collides; check the name.

Not every replacement is a loss. Some resources are immutable by design, so a change creates a new version: a container task definition revision, a launch template version, a function version, a configuration object with a hashed name. That is the normal deploy path. Read what happens to the old version from the plan (a destroy removes or deregisters it), not from memory. Assess the rollout that follows (rolling update settings, health checks, automatic rollback, what keeps serving meanwhile), not the word "replaced".

## Refactors, imports and removals

- A pure refactor plans zero adds and zero destroys, each resource shown as `has moved to`. Use `moved` blocks (Terraform 1.1 or later). A destroy and create pair in a refactor means a missing `moved` block, and applying it recreates real resources.
- `import` blocks (1.5 or later) bring existing resources under management; the plan must show the import and no change beyond the intended one.
- To stop managing a resource without destroying it, use a `removed` block with `lifecycle { destroy = false }` (1.7 or later). Deleting the resource block alone plans a destroy.

## State, backend and workspace

- A plan that wants to create what already exists, or destroy everything, usually means Terraform is reading the wrong or an empty state: a changed backend key, bucket or prefix, the wrong workspace, var file, account, region or role. Never apply it: the result is a duplicate beside the real resources (or deleted infrastructure) and a state that tracks the wrong objects.
- `terraform init -migrate-state` copies the state from the backend the directory was last initialised with to the newly configured one. `terraform init -reconfigure` switches without copying, and after it there is nothing left to migrate from: re-initialise on the old location, then change the configuration and migrate, or copy the state object across with the owner's approval. The move is done when a plan on the new location shows no changes; keep the old object until then.
- Check where the plan came from before trusting it:

```
terraform version
terraform workspace show
terraform providers
terraform state list
terraform show -json tfplan | jq -r '.resource_changes[] | "\(.change.actions | join(",")) \(.address)"'
```

## Locks and concurrent runs

- A state lock means another operation may be writing the state right now. Read its `Who`, `Operation` and `Created` fields and match them with running pipelines and people first.
- If the holder is still running, wait for it to finish, then make a fresh plan against the updated state and apply that. Disabling locking with `-lock=false` is never the answer.
- `terraform force-unlock` is only for a lock whose holder is confirmed gone (the run ended or was killed and nothing else is applying); propose it with that evidence, run it only with the stack owner's approval, then re-plan.

## What a plan cannot show

Say so in the review when it matters:

- Data inside resources: objects a lifecycle or retention rule will delete later, rows a schema change drops.
- Who depends on the resource: clients, callers and other stacks outside this configuration. A narrower session length, protocol list, network rule or quota breaks any client that needs more; check access logs, audit trails and the consumers' own configuration.
- Runtime behaviour of an in-place update: some restart, reboot or briefly drop connections; some wait for a maintenance window unless applied immediately.
- Changes made after the plan, other runs on the same state, partial failure mid-apply, and values that are `(known after apply)`.

## When it is safe to apply

Say yes when every change is explained by the intent, nothing stateful is replaced or destroyed without a planned and approved reason, the plan was made against the right state with no unexplained drift, and the dependents the plan cannot see are known to be fine. Then apply the saved plan that was reviewed (`terraform apply tfplan`) through the normal pipeline and its approval. Keep `-target` for recovery, since it applies part of the graph, and use `-replace` only when the replacement is the intent.

## Commands that change things

`terraform apply`, `destroy`, `import`, `state mv`, `state rm`, `force-unlock` and `init -migrate-state` change infrastructure or state: propose each with its reason, run it only after the owner approves, and save a copy of the state (`terraform state pull` to a file) before any state edit.
