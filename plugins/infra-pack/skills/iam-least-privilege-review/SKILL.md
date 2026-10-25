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

Every request starts denied. An `Allow` in an applicable policy grants it, and any explicit `Deny` wins over every `Allow`. Service control policies, resource control policies, permissions boundaries and session policies never grant access; they only narrow what other policies allow. Within one account, either an identity policy or a resource policy can grant access, except that a role's trust policy and a KMS key policy must allow the principal themselves; across accounts, both the caller's identity policy and the resource's policy (for a role, its trust policy) must allow it.

## Read each statement

- `Action`: wildcards expand. `s3:*`, `iam:*` and `*` are everything; `s3:Get*` includes `s3:GetObject`, which reads data. `NotAction` with `Allow` grants every other action.
- `Resource`: a wildcard in an ARN matches any run of characters, `/` included, so `arn:aws:s3:::app*` covers all buckets named `app` plus anything, and all their objects. Pair each action with the resource type it applies to (see the Service Authorization Reference): `s3:ListBucket` on the bucket ARN, `s3:GetObject` and `s3:PutObject` on `bucket/*`. Some actions, many `List*` and `Describe*` calls among them, support no resource-level permission and must be granted on `"Resource": "*"`; that is required, not over-broad. `NotResource` with `Allow` grants everything else.
- `Principal`, in resource and trust policies: `"AWS": "*"` is anyone, including anonymous callers unless a condition limits it. An account principal (`arn:aws:iam::123456789012:root` or the bare account ID) trusts the whole account: any user or role in it can use the grant if its own permissions allow the action, not only the root user. To admit only one workload, name its role ARN as the principal, or limit the account principal with an `aws:PrincipalArn` condition. A role ARN in a trust policy no longer matches once that role is deleted and created again.
- Service principals (such as `lambda.amazonaws.com`) should be limited with `aws:SourceArn` or `aws:SourceAccount` to prevent the confused deputy; a third party that assumes roles in many customers' accounts should be required to present an `sts:ExternalId`.
- Web identity trust (CI OIDC, cluster service accounts) must check the audience and pin the subject to the exact repository and branch or environment, or the exact service account. A subject with a wildcard over an organisation or all branches lets any of them assume the role.
- `Condition`: check the operator and the key. `StringLike` with `*`; a key that may be absent (`...IfExists`, `Null`); multi-valued keys, where `ForAllValues` is true when the request carries no value and `ForAnyValue` matches any one; negated operators (`StringNotEquals`, `NotIpAddress`), which in a `Deny` hit everyone who does not match. `aws:SourceIp` does not match requests that arrive through a VPC endpoint; use `aws:SourceVpce` or `aws:SourceVpc` there.
- Tag-based conditions, such as `aws:ResourceTag/project` equal to `${aws:PrincipalTag/project}`, are a sound way to scope `*` resources, provided the principals have no rights to tag those resources or their own identity.

## Compare with the need

- Write down what the workload must do (which actions on which resources) from the request and from real use: CloudTrail events, IAM last accessed information, Access Analyzer policy generation. Grant that, scoped to the exact resources, and say what the reviewed policy grants beyond it.
- Name what is missing too. A policy that is too narrow fails in production: `kms:Decrypt` for data encrypted with a customer managed key, `s3:ListBucket` so that a missing object returns 404 rather than 403, `iam:PassRole` to hand a role to a service.
- Read "read-only" literally. A managed policy such as `ReadOnlyAccess` allows Get, List, Describe and similar actions across services, and many of those read data, such as object contents and table items. For a review of configuration only, use a configuration-scoped policy (for example `SecurityAudit` or `ViewOnlyAccess`, both AWS managed, or a policy of your own), deny data reads explicitly where data must stay out of reach, and test the result against both the access it must keep and the access it must refuse.
- Approve a policy that already matches the need, and explain why any warning raised against it does not apply.

## Escalation paths

Any of these on broad resources lets a principal become more powerful than its policy suggests. Block them unless the need is explicit and scoped:

- `iam:PassRole` on `*` together with a service that runs code (`ec2:RunInstances`, `lambda:CreateFunction`, `ecs:RunTask`, `cloudformation:CreateStack`, Glue jobs): the principal gains the passed role's rights. Scope `iam:PassRole` to the role ARNs and add `iam:PassedToService`.
- Changing policies or identities: `iam:CreatePolicyVersion`, `iam:SetDefaultPolicyVersion`, `iam:AttachRolePolicy`, `iam:PutRolePolicy` (and the user and group forms), `iam:UpdateAssumeRolePolicy`, `iam:CreateAccessKey`, `iam:CreateLoginProfile`, `iam:UpdateLoginProfile`, `iam:AddUserToGroup`.
- `iam:CreateRole` with rights to attach policies, unless an `iam:PermissionsBoundary` condition forces a boundary on every new role.
- `sts:AssumeRole` on `*`; `lambda:UpdateFunctionCode` on functions with stronger roles; `ssm:SendCommand` or `ssm:StartSession` on instances with stronger roles; `kms:CreateGrant` and `kms:PutKeyPolicy`.
- Tagging actions, when access is decided by tags.

## Resource policies and lockout

- A `Deny` with a negated condition (not through this endpoint, not from this organisation, not from this network) affects every principal that does not match, administrators and automation included; on the policy actions it can leave only the account's root user able to change the policy. Before adding one, find who uses the resource today and keep the access that must stay.
- A KMS key policy is the root of access to its key: a key policy that drops the account's or the administrators' access can leave the key unmanageable.
- Public access: `"Principal": "*"` without a limiting condition, public ACLs, or S3 Block Public Access being switched off.

## Read-only checks

```
aws iam get-role --role-name app --query 'Role.AssumeRolePolicyDocument'
aws iam list-attached-role-policies --role-name app
aws iam get-policy-version --policy-arn <policy-arn> --version-id <version-id>
aws iam simulate-principal-policy --policy-source-arn <role-arn> --action-names s3:GetObject --resource-arns <object-arn>
aws accessanalyzer validate-policy --policy-type IDENTITY_POLICY --policy-document file://policy.json
aws s3api get-bucket-policy --bucket app-data
```

## Proposing the change

Give the corrected statement (exact actions, exact resources, the condition), say what it no longer allows, and propose it through the review and pipeline that manage IAM, applied after the resource owner approves. A change made by hand (`aws iam put-role-policy`, `attach-role-policy`, `update-assume-role-policy`, `aws s3api put-bucket-policy` or `delete-bucket-policy`) needs the same approval. Access is never widened "for now" to be narrowed later.

## Other clouds

The same reading applies. In Google Cloud, Owner, Editor and Viewer are broad, `allUsers` makes a resource public, and `iam.serviceAccounts.actAs` lets a principal act as a service account. In Azure, Owner and User Access Administrator can assign roles; assign at the narrowest scope the need allows.
