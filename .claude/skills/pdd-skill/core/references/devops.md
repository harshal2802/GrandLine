# PDD Reference: DevOps / Infrastructure Projects

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for infrastructure, platform engineering, and DevOps projects (IaC, CI/CD, containers, cloud, and related tooling).

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- Cloud provider(s)? (AWS, GCP, Azure, multi-cloud, on-prem)
- IaC tool? (Terraform, Pulumi, CDK, Bicep, Ansible, CloudFormation)
- Container orchestration? (Kubernetes, ECS, Cloud Run, none)
- CI/CD platform? (GitHub Actions, GitLab CI, Jenkins, CircleCI, ArgoCD)
- How are secrets managed? (Vault, AWS Secrets Manager, SOPS, env vars)
- What environments exist? (dev, staging, prod — or more)
- Are there compliance or security requirements? (SOC2, HIPAA, PCI, etc.)
- What's the on-call / incident response setup?

### Extended `pdd/context/project.md` sections for DevOps/infra

```markdown
## Cloud & platform
- Provider:
- Regions:
- Account / project structure:

## IaC
- Tool:
- State backend: (S3 + DynamoDB, GCS, Terraform Cloud, etc.)
- Module / workspace structure:

## Environments
- Environments: dev / staging / prod (or list)
- Promotion process: (PR merge / manual approval / automated)

## Secrets
- Tool:
- Rotation policy:

## Compliance
- Standards required:
- Audit logging required: yes / no
```

---

## Conventions Starter (Workflow 2)

```markdown
# DevOps / Infra Conventions

## IaC structure
- Modules: reusable, single-responsibility, versioned
- Environments: separate state per environment
- No hardcoded values — all via variables with defaults
- Outputs documented for every module

## Naming
- Resources: <org>-<env>-<service>-<resource-type> (e.g. acme-prod-api-sg)
- Consistent across cloud provider and IaC tool
- Tags: environment, team, cost-center, managed-by=terraform required on all resources

## Change management
- All changes via IaC — no manual console changes
- Plan reviewed before apply — no blind applies
- Destructive changes (delete, replace) flagged explicitly and require separate approval
- Blast radius documented in PR description for significant changes

## Secrets
- Never commit secrets to git — not even encrypted
- Reference secrets by path/ARN from secrets manager — never inline values
- Rotate secrets on a defined schedule

## CI/CD
- Pipeline runs on every PR — plan / lint / test
- Apply only on merge to main (not on PR)
- Failed pipeline blocks merge — no exceptions
- Rollback procedure documented for every deployment

## Security
- Least-privilege IAM — no wildcard permissions in production
- Security groups / firewall rules: deny by default, allow explicitly
- Public exposure documented and justified in decisions.md
- MFA required for console access to production
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New infrastructure module

```markdown
# Prompt: <ModuleName> Terraform Module

## Task
Create a reusable Terraform module for <resource or service>.

## Resources to create
- <resource type and purpose>
- <resource type and purpose>

## Input variables
- `<var_name>`: <type> — <description> (default: <value if optional>)

## Outputs
- `<output_name>`: <what it exposes and why>

## Constraints
- No hardcoded region, account ID, or environment — all via variables
- All resources tagged with: environment, team, managed-by=terraform
- Least-privilege IAM — no wildcard actions or resources in production policies
- Include a README.md with usage example
```

### CI/CD pipeline

```markdown
# Prompt: <Service> CI/CD Pipeline

## Task
Create a <GitHub Actions / GitLab CI> pipeline for <service>.

## Stages
1. Lint and test — on every push and PR
2. Build and push image — on merge to main
3. Deploy to staging — automatic after build
4. Deploy to production — manual approval gate

## Environment variables / secrets needed
- <SECRET_NAME>: <what it's for>

## Constraints
- No secrets in pipeline definition files
- Cache dependencies for faster runs
- Fail fast — don't continue stages after failure
- Notify <Slack channel / email> on production deployment success or failure
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**Security**
- [ ] No hardcoded secrets, credentials, or tokens?
- [ ] IAM / RBAC follows least-privilege?
- [ ] No wildcard permissions (`*`) in production?
- [ ] Public exposure justified and documented?
- [ ] Security groups / firewall rules: deny by default?

**Change safety**
- [ ] Blast radius of this change assessed?
- [ ] Destructive operations (delete, replace) identified and flagged?
- [ ] Rollback procedure clear?
- [ ] Change can be applied incrementally if large?

**IaC quality**
- [ ] No hardcoded values — all via variables?
- [ ] All resources tagged correctly?
- [ ] Outputs documented and useful?
- [ ] Module is reusable — no environment-specific logic inside?
- [ ] State backend configured and remote?

**Reliability**
- [ ] Health checks configured for services?
- [ ] Auto-scaling or redundancy in place for production?
- [ ] Alerts defined for failure conditions?
- [ ] Backup / restore tested for stateful resources?

**Compliance**
- [ ] Audit logging enabled where required?
- [ ] Encryption at rest and in transit?
- [ ] Data residency requirements met?
- [ ] Resource lifecycle / retention policies set?
