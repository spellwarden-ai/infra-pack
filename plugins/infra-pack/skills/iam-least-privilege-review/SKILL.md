---
name: iam-least-privilege-review
description: Review AWS IAM identity policies, resource policies (bucket, key, queue, topic, function), trust policies, permission sets and managed policy attachments for least privilege. Use it when a pull request adds or changes a policy, role, trust relationship or attachment, when someone asks whether access is safe to grant, or when a workload is denied. It works out what a policy actually allows (actions, resources, conditions, principals), compares that with what the workload needs and lacks, and flags changes that widen access beyond the need, lock out the people and automation that manage a resource, or open a path to privilege escalation. The same reasoning applies to other clouds where the principle holds.
license: Apache-2.0
metadata:
  version: "0.9.0"
  author: Spellwarden
---

# IAM least-privilege review

Assess a policy by what it allows, not by its name, its comment or the ticket that asked for it. Then compare that with what the workload needs, from the request and from evidence of real use.

## How AWS decides

Every request starts denied. An `Allow` in an applicable policy grants it, and any explicit `Deny` wins over every `Allow`. Service control policies, resource control policies, permissions boundaries and session policies can only narrow what identity policies grant. Within one account, either an identity policy or a resource policy can grant access; across accounts, both the caller's identity policy and the resource's policy (for a role, its trust policy) must allow it.

## Read each statement

- `Action`: wildcards expand. `s3:*`, `iam:*` and `*` are everything; `s3:Get*` includes `s3:GetObject`, which reads data. `NotAction` with `Allow` grants every other action.
- `Resource`: a wildcard matches every name that fits. `arn:aws:s3:::app*` matches every bucket whose name starts with `app`, and because the wildcard also spans the `/key` part, every object in them. Pair each action with the resource type it applies to (the Service Authorization Reference lists them): `s3:ListBucket` on the bucket ARN, `s3:GetObject` and `s3:PutObject` on `bucket/*`. Some actions, many `List*` and `Describe*` calls among them, support no resource-level permission and only work with `"Resource": "*"`; that is required, not over-broad. `NotResource` with `Allow` grants everything else.
- `Principal`, in resource and trust policies: `"AWS": "*"` is anyone, including anonymous callers unless a condition limits it. An account principal (`arn:aws:iam::123456789012:root` or the bare account ID) trusts the whole account: any user or role there whose own policies allow the action can use it, not only the root user. When only one workload should get access, name its role ARN, or keep the account and add an `aws:PrincipalArn` condition. A trust policy naming a role ARN stops matching if that role is deleted and recreated.
- Service principals (such as `lambda.amazonaws.com`) should be limited with `aws:SourceArn` or `aws:SourceAccount` to prevent the confused deputy; a third party assuming a role should present an `sts:ExternalId`.
- Web identity trust (CI OIDC, cluster service accounts) must check the audience and pin the subject to the exact repository and branch or environment, or the exact service account. A subject with a wildcard over an organisation or all branches lets any of them assume the role.
- `Condition`: check the operator and the key. `StringLike` with `*`; a key that may be absent (`...IfExists`, `Null`); multi-valued keys, where `ForAllValues` is true when the request carries no value and `ForAnyValue` matches any one; negated operators (`StringNotEquals`, `NotIpAddress`), which in a `Deny` hit everyone who does not match. `aws:SourceIp` does not match requests that arrive through a VPC endpoint; use `aws:SourceVpce` or `aws:SourceVpc` there.
- Tag-based conditions such as `aws:ResourceTag/team` equal to `${aws:PrincipalTag/team}` are a sound way to scope `*` resources, provided the principals cannot change those tags (no `ec2:CreateTags`, `iam:TagRole` and the like for them).

## Compare with the need

- Write down what the workload must do (which actions on which resources) from the request and from real use: CloudTrail events, IAM last accessed information, Access Analyzer policy generation. Grant that, scoped to the exact resources, and say what the reviewed policy grants beyond it.
- Name what is missing too. A policy that is too narrow fails in production: `kms:Decrypt` for data encrypted with a customer managed key, `s3:ListBucket` so that a missing object returns 404 rather than 403, `iam:PassRole` to hand a role to a service.
- Read "read-only" literally. A managed policy such as `ReadOnlyAccess` allows Get, List, Describe and similar actions across services, and many of those read data: object contents, table items, queue messages, logs, parameters. For a review of configuration only, use a configuration-scoped policy (the AWS managed `SecurityAudit` or `ViewOnlyAccess`, or a custom one), add an explicit `Deny` on data reads where data must stay out of reach, and test both what must work and what must be refused.
- Approve a policy that already matches the need. A tag condition that scopes a wildcard, a `*` resource the action requires, or a linter warning that does not apply are not reasons to block; explain why the warning does not apply.

## Escalation paths

Any of these on broad resources lets a principal become more powerful than its policy suggests. Block them unless the need is explicit and scoped:

- `iam:PassRole` on `*` together with a service that runs code (`ec2:RunInstances`, `lambda:CreateFunction`, `ecs:RunTask`, `cloudformation:CreateStack`, Glue jobs): the principal gains the passed role's rights. Scope `iam:PassRole` to the role ARNs and add `iam:PassedToService`.
- Changing policies or identities: `iam:CreatePolicyVersion`, `iam:SetDefaultPolicyVersion`, `iam:AttachRolePolicy`, `iam:PutRolePolicy` (and the user and group forms), `iam:UpdateAssumeRolePolicy`, `iam:CreateAccessKey`, `iam:CreateLoginProfile`, `iam:UpdateLoginProfile`, `iam:AddUserToGroup`.
- `iam:CreateRole` with rights to attach policies, unless an `iam:PermissionsBoundary` condition forces a boundary on every new role.
- `sts:AssumeRole` on `*`; `lambda:UpdateFunctionCode` on functions with stronger roles; `ssm:SendCommand` or `ssm:StartSession` on instances with stronger roles; `kms:CreateGrant` and `kms:PutKeyPolicy`.
- Tagging actions, when access is decided by tags.

## Resource policies and lockout

- A `Deny` with a negated condition (not through this VPC endpoint, not from this organisation, not from this network) blocks every principal that does not match: administrators, the role that deploys the policy, console users, AWS services acting for you. With `s3:*` it also blocks reading, changing and deleting the policy itself, so recovery may take the account's root user. Before such a policy goes on, list who uses the resource today (CloudTrail data events, access logs), exempt those that must keep access (for example an `aws:PrincipalArn` condition for the deploy role and a break-glass role), limit the actions to what the requirement covers, try it on a non-production copy, and apply it through the code that manages the resource.
- A KMS key policy is the root of access to its key: a key policy that drops the account's or the administrators' access can leave the key unmanageable.
- Public access: `"Principal": "*"` without a limiting condition, public ACLs, or S3 Block Public Access being switched off.

## Read-only checks

```
aws iam get-role --role-name app --query 'Role.AssumeRolePolicyDocument'
aws iam list-attached-role-policies --role-name app
aws iam list-role-policies --role-name app
aws iam get-policy-version --policy-arn <policy-arn> --version-id <version-id>
aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::123456789012:role/app --action-names s3:GetObject --resource-arns arn:aws:s3:::app-data/report.csv
aws accessanalyzer validate-policy --policy-type IDENTITY_POLICY --policy-document file://policy.json
aws s3api get-bucket-policy --bucket app-data
```

## Proposing the change

Give the corrected statement (exact actions, exact resources, the condition), say what it no longer allows, and propose it through the review and pipeline that manage IAM, applied after the resource owner approves. A change made by hand (`aws iam put-role-policy`, `attach-role-policy`, `update-assume-role-policy`, `aws s3api put-bucket-policy` or `delete-bucket-policy`) needs the same approval. Access is never widened "for now" to be narrowed later.

## Other clouds

The same reading applies. In Google Cloud the Owner, Editor and Viewer roles are broad, `allUsers` and `allAuthenticatedUsers` make a resource public, and `iam.serviceAccounts.actAs` or token creator rights let a principal act as a service account. In Azure, Owner and User Access Administrator can assign roles (`Microsoft.Authorization/roleAssignments/write`); assign at the resource or resource group, not the subscription, unless the need is subscription-wide.
