# Dependency Audit — Colab Platform

**Version**: 1.0  
**Date**: 2026-05-11  
**Tools**: Trivy · Snyk · semgrep · bandit · eslint-plugin-security · Dependabot

---

## 1. Tool Inventory

| Tool | Scope | Trigger | Gate |
|------|-------|---------|------|
| **Trivy** | Container images (OS + pip + npm inside image), Dockerfile misconfig, secrets detection | CI after `docker build`; weekly ECR scan | CRITICAL or HIGH findings block merge |
| **Snyk Open Source** | Python `pyproject.toml` / `requirements.txt`; npm `package.json` | CI on every PR; `snyk monitor` on main | HIGH/CRITICAL block merge; MODERATE email digest |
| **Snyk Container** | Docker base images | CI after `docker build` | HIGH/CRITICAL block merge |
| **semgrep** | Python FastAPI services; TypeScript (Next.js, RN); YAML/K8s manifests | CI on every PR; nightly full scan | Zero HIGH/CRITICAL unresolved |
| **bandit** | Python only (AST-level) | CI on every PR | HIGH findings fail CI; baseline committed |
| **eslint-plugin-security** | TypeScript and TSX files | CI on every PR | HIGH findings fail CI |
| **Dependabot** | pip + npm + Docker base images + GitHub Actions | Weekly PRs; immediate on security advisory | PR auto-merge if CI green and severity ≤ MODERATE |

---

## 2. Trivy Integration

### How it runs

```yaml
# .github/workflows/security-scan.yml (excerpt)
- name: Trivy container scan
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: ${{ env.ECR_REGISTRY }}/${{ env.SERVICE }}:${{ github.sha }}
    format: sarif
    output: trivy-results.sarif
    severity: CRITICAL,HIGH
    exit-code: 1          # Block CI on findings
    ignore-unfixed: false
    vuln-type: os,library
```

### SBOM generation

```bash
trivy image --format cyclonedx --output sbom-${SERVICE}-${SHA}.json \
  ${ECR_REGISTRY}/${SERVICE}:${SHA}
```

SBOM artifacts stored in `s3://colab-audit-artifacts/sboms/` per build.

### Post-push registry scanning

```bash
# Run weekly via CloudWatch Events → Lambda
trivy image --exit-code 0 --format json \
  ${ECR_REGISTRY}/${SERVICE}:latest \
  | aws s3 cp - s3://colab-audit-artifacts/trivy-weekly/$(date +%Y%m%d)/${SERVICE}.json
```

### Exception process

1. Engineer identifies finding as false positive or accepted risk.
2. Engineering lead signs off in GitHub issue with label `trivy:accepted`.
3. `.trivyignore` entry added with: finding ID, acceptance date, expiry date (max 90 days), compensating control.
4. On expiry: re-evaluate finding; extend or remediate.

---

## 3. Snyk Integration

### How it runs

```bash
# Installed in CI per service
snyk test --severity-threshold=high --json > snyk-results.json || exit 1

# Monitor (continuous background tracking)
snyk monitor --project-name=colab-${SERVICE} --org=colab
```

### Fix PR policy

Snyk auto-generates fix PRs. Merge policy:
- **Auto-merge**: CI green + severity ≤ MODERATE + no breaking version change
- **Human review required**: HIGH/CRITICAL within 48h; breaking version change regardless of severity

### Snyk vs. Dependabot overlap

Both tools are run because they use different vulnerability databases (Snyk Intel vs. GitHub Advisory Database / NVD). Findings unique to each database are complementary.

---

## 4. semgrep Integration

### Rulesets activated

```yaml
# .semgrepignore and semgrep.yml
rules:
  - p/python
  - p/fastapi
  - p/typescript
  - p/react
  - p/secrets
  - p/owasp-top-ten
  - p/docker
  - p/kubernetes
```

### Custom rules (in `tools/semgrep/`)

| Rule ID | Pattern | Rationale |
|---------|---------|-----------|
| `colab.missing-auth-decorator` | FastAPI route without `Depends(verify_jwt)` | Unprotected endpoint |
| `colab.raw-sql-query` | `cursor.execute(f"...{var}...")` | SQL injection risk |
| `colab.subprocess-shell-true` | `subprocess.run(..., shell=True)` | Command injection |
| `colab.logging-sensitive` | `log.*(password\|token\|secret\|api_key)` | Credential leak in logs |
| `colab.hardcoded-secret` | Literals matching `/sk-[A-Za-z0-9]{32}/` etc. | Stripe/OpenAI key pattern |
| `colab.dangerously-set-html` | `dangerouslySetInnerHTML` in TSX | XSS in React |
| `colab.eval-usage` | `eval(` in JS/TS | Code injection |

### Running locally

```bash
semgrep --config=p/python --config=p/fastapi services/auth-svc/
semgrep --config=tools/semgrep/ services/  # custom rules only
```

---

## 5. bandit Integration

### How it runs

```bash
# Per Python service in CI
bandit -r services/${SERVICE}/app/ \
  -ll \                        # report HIGH and above
  --format json \
  -o bandit-${SERVICE}.json || exit 1

# Baseline (committed to repo after initial run)
bandit -r services/${SERVICE}/app/ -ll --format json -o .bandit-baseline.json
```

### Common findings to watch

| bandit ID | Description | Action |
|-----------|-------------|--------|
| B105 | Hardcoded password string | Always fix |
| B608 | SQL injection (string concat) | Always fix |
| B602 | `subprocess.Popen` with shell | Fix or document |
| B324 | Use of MD5 / SHA1 | Replace with SHA-256+ |
| B301 | `pickle.loads` | Replace with `json` or `msgpack` |

---

## 6. eslint-plugin-security Integration

### Config (in each TS package's `.eslintrc`)

```json
{
  "plugins": ["security"],
  "extends": ["plugin:security/recommended"],
  "rules": {
    "security/detect-object-injection": "warn",
    "security/detect-non-literal-regexp": "error",
    "security/detect-possible-timing-attacks": "error",
    "security/detect-unsafe-regex": "error",
    "security/detect-eval-with-expression": "error",
    "security/detect-no-csrf-before-method-override": "error"
  }
}
```

---

## 7. Dependabot Configuration

See `/.github/dependabot.yml` for the full config. Summary:

- **Python services**: Weekly PRs grouped by `production-deps` and `dev-deps`; all 19 services covered individually (separate `directory` per service).
- **npm (apps)**: Weekly for `consumer-web`, `marketing-web`, `admin-web`, `apps/mobile`.
- **npm (packages)**: Weekly for `packages/ui`, `packages/design-tokens`, etc.
- **Docker**: Weekly for all `Dockerfile` base images.
- **GitHub Actions**: Weekly for all `uses:` action references.

### Auto-merge policy (via GitHub Actions)

```yaml
# Dependabot PRs: auto-merge if CI green + MODERATE or lower severity
- name: Auto-merge Dependabot PRs
  if: github.actor == 'dependabot[bot]'
  run: gh pr merge --auto --squash "${{ github.event.pull_request.html_url }}"
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

HIGH/CRITICAL Dependabot PRs are NOT auto-merged; they page the on-call engineer.

---

## 8. Audit Schedule Summary

| Cadence | Activity |
|---------|----------|
| Every PR | Trivy, Snyk, semgrep, bandit, eslint-security |
| Every main merge | `snyk monitor` report update |
| Weekly | Dependabot PRs generated; ECR Trivy registry scan |
| Monthly | Review accepted exceptions in `.trivyignore`; extend or remediate |
| Quarterly | Secrets rotation drill (see secrets-rotation-runbook.md); full `snyk test --all-projects` |
| Pre-launch | Security sign-off (T-033): all tools green + pen-test retest passed |
