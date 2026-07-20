# IT Access Provisioning Policy

## Sensitivity Classification

### Low Sensitivity (Auto-Approve)
- Slack channels (public)
- Wiki/Confluence spaces
- Development tools (IDE licenses, GitHub repos for own team)
- Internal documentation

### Medium Sensitivity (Auto-Approve + Logging)
- Internal dashboards and reporting tools
- Staging/sandbox environments
- Cross-team Slack channels (private)
- CI/CD pipeline access (read-only)

### High Sensitivity (Requires Justification + Manager Approval)
- Production database (read-only)
- Customer data views (anonymized)
- Admin panels (read-only)
- Security scanning tools
- Cost/billing dashboards

### Critical Sensitivity (Requires Justification + Manager + Security Approval)
- Production database (write access)
- Customer PII (non-anonymized)
- Data export capabilities
- Admin panels (write access)
- Infrastructure/cloud console access
- Encryption key management

## Approval Requirements

| Sensitivity | Approver | SLA |
|---|---|---|
| Low | None (auto) | Instant |
| Medium | None (auto + logged) | Instant |
| High | Direct manager | 24 hours |
| Critical | Manager + Security team | 48 hours |

## Duration Policies

- Temporary access (7-90 days): Preferred for project-based work
- Permanent access: Only for job-function-essential systems
- All high/critical access: Auto-expires, renewal required at 75% of duration
- Maximum duration for data export access: 30 days (no exceptions)

## Justification Requirements

A valid justification must include:
1. Specific business need (not just "I might need it")
2. What data/functionality will be accessed
3. Why existing access is insufficient
4. Expected duration of need

## Red Flags (Triggers Additional Review)
- Requesting access outside own team's domain
- Data export + external sharing
- Requesting permanent access to high/critical systems
- New employee (<30 days) requesting critical access
- Requesting access to systems not mentioned in job description
