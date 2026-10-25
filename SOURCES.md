# Sources

The public documentation each skill was written from, as the page title and its address. The skills hold no text copied from these pages; they restate general practice in their own words.

## infra-change-safety

- [Managing Incidents](https://sre.google/sre-book/managing-incidents/), Google SRE book
- [Canarying Releases](https://sre.google/workbook/canarying-releases/), Google SRE workbook
- [Operational Excellence Pillar](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html), AWS Well-Architected Framework
- [Security best practices in IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html), AWS Identity and Access Management
- [Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/), Kubernetes
- [State Locking](https://developer.hashicorp.com/terraform/language/state/locking), Terraform
- [About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), GitHub

## terraform-plan-review

- [terraform plan command](https://developer.hashicorp.com/terraform/cli/commands/plan), Terraform
- [terraform apply command](https://developer.hashicorp.com/terraform/cli/commands/apply), Terraform
- [terraform show command reference](https://developer.hashicorp.com/terraform/cli/commands/show), Terraform
- [JSON Output Format Overview](https://developer.hashicorp.com/terraform/internals/json-format), Terraform
- [Refactor modules](https://developer.hashicorp.com/terraform/language/modules/develop/refactoring), Terraform
- [Import resources overview](https://developer.hashicorp.com/terraform/language/import), Terraform
- [removed block reference](https://developer.hashicorp.com/terraform/language/block/removed), Terraform
- [lifecycle reference](https://developer.hashicorp.com/terraform/language/meta-arguments/lifecycle), Terraform
- [Backend block configuration overview](https://developer.hashicorp.com/terraform/language/backend), Terraform
- [terraform init command](https://developer.hashicorp.com/terraform/cli/commands/init), Terraform
- [State Locking](https://developer.hashicorp.com/terraform/language/state/locking), Terraform
- [terraform force-unlock command](https://developer.hashicorp.com/terraform/cli/commands/force-unlock), Terraform
- [Use refresh-only mode to sync Terraform state](https://developer.hashicorp.com/terraform/tutorials/state/refresh), Terraform tutorials
- [aws_s3_bucket_lifecycle_configuration](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_lifecycle_configuration), Terraform AWS provider
- [aws_db_instance](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/db_instance), Terraform AWS provider
- [Lifecycle configuration elements](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-rules.html), Amazon S3
- [Command: plan](https://opentofu.org/docs/cli/commands/plan/), OpenTofu

## kubernetes-incident-triage

- [Debug Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/), Kubernetes
- [Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/), Kubernetes
- [Determine the Reason for Pod Failure](https://kubernetes.io/docs/tasks/debug/debug-application/determine-reason-pod-failure/), Kubernetes
- [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/), Kubernetes
- [Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/), Kubernetes
- [Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/), Kubernetes
- [CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/), Kubernetes
- [Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/), Kubernetes
- [ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/), Kubernetes
- [Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/), Kubernetes
- [Debug Services](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/), Kubernetes
- [Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/), Kubernetes
- [Horizontal Pod Autoscaling](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/), Kubernetes
- [Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/), Kubernetes
- [Safely Drain a Node](https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/), Kubernetes
- [Force Delete StatefulSet Pods](https://kubernetes.io/docs/tasks/run-application/force-delete-stateful-set-pod/), Kubernetes
- [Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/), Kubernetes
- [Server-Side Apply](https://kubernetes.io/docs/reference/using-api/server-side-apply/), Kubernetes
- [kube-apiserver](https://kubernetes.io/docs/reference/command-line-tools-reference/kube-apiserver/), Kubernetes

## iam-least-privilege-review

- [Policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html), AWS Identity and Access Management
- [AWS JSON policy elements: Principal](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_principal.html), AWS Identity and Access Management
- [IAM JSON policy elements: Resource](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_resource.html), AWS Identity and Access Management
- [AWS global condition context keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html), AWS Identity and Access Management
- [The confused deputy problem](https://docs.aws.amazon.com/IAM/latest/UserGuide/confused-deputy.html), AWS Identity and Access Management
- [Grant a user permissions to pass a role to an AWS service](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_passrole.html), AWS Identity and Access Management
- [AWS managed policies for job functions](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_job-functions.html), AWS Identity and Access Management
- [Define permissions based on attributes with ABAC authorization](https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction_attribute-based-access-control.html), AWS Identity and Access Management
- [Validate policies with IAM Access Analyzer](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html), AWS Identity and Access Management
- [Refine permissions in AWS using last accessed information](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_last-accessed.html), AWS Identity and Access Management
- [Security best practices in IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html), AWS Identity and Access Management
- [Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/reference.html), AWS
- [Actions, resources, and condition keys for AWS services](https://docs.aws.amazon.com/service-authorization/latest/reference/reference_policies_actions-resources-contextkeys.html), AWS Service Authorization Reference
- [Key policies in AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html), AWS Key Management Service
- [Controlling access from VPC endpoints with bucket policies](https://docs.aws.amazon.com/AmazonS3/latest/userguide/example-bucket-policies-vpc-endpoint.html), Amazon S3
- [DeleteBucketPolicy](https://docs.aws.amazon.com/AmazonS3/latest/API/API_DeleteBucketPolicy.html), Amazon S3 API Reference
- [Roles overview](https://docs.cloud.google.com/iam/docs/roles-overview), Google Cloud IAM
- [Best practices for Azure RBAC](https://learn.microsoft.com/en-us/azure/role-based-access-control/best-practices), Microsoft Azure

## ci-pipeline-repair

- [Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use), GitHub Actions
- [Use GITHUB_TOKEN for authentication in workflows](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token), GitHub Actions
- [OpenID Connect](https://docs.github.com/en/actions/concepts/security/openid-connect), GitHub Actions
- [Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), GitHub Actions
- [Running variations of jobs in a workflow](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations), GitHub Actions
- [Dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching), GitHub Actions
- [Control the concurrency of workflows and jobs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency), GitHub Actions
- [Managing environments for deployment](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments), GitHub Actions
- [Troubleshooting required status checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks), GitHub
- [Troubleshooting rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/troubleshooting-rules), GitHub
- [Managing a merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue), GitHub
- [Caching in GitLab CI/CD](https://docs.gitlab.com/ci/caching/), GitLab
- [CI/CD variables](https://docs.gitlab.com/ci/variables/), GitLab
- [Protected environments](https://docs.gitlab.com/ci/environments/protected_environments/), GitLab
- [CI/CD YAML syntax reference](https://docs.gitlab.com/ci/yaml/), GitLab
- [npm-ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/), npm
- [Secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/), pip
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html), PostgreSQL
- [The Cumulative Statistics System](https://www.postgresql.org/docs/current/monitoring-stats.html), PostgreSQL
