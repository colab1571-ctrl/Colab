# Incident Channels — Slack / Discord / PagerDuty Bridge

**Version**: 1.0  
**Date**: 2026-05-11

---

## 1. Slack Channels

| Channel | Purpose | Who posts | Notes |
|---------|---------|-----------|-------|
| `#incidents` | All active incidents (P1–P3) | On-call, IC, PagerDuty bot | Default incident channel |
| `#incidents-p1` | P1 only | On-call, IC; PagerDuty auto-posts | Pings @oncall + @engineering-lead |
| `#postmortems` | Published postmortem documents | Anyone | Link to doc; no discussion in this channel |
| `#engineering` | P3/P4 issues; general eng discussion | Engineers | Not for active incidents |
| `#deploys` | Deployment announcements (automated) | GitHub Actions bot | Auto-post on every production deploy |
| `#status-alerts` | Pingdom + CloudWatch alerts (automated) | Bots only | High volume; muted by most |

### PagerDuty → Slack integration

PagerDuty automatically posts to `#incidents` when:
- A new incident is created
- An incident is acknowledged
- An incident is resolved
- An escalation fires

Format of PagerDuty Slack post:
```
:pagerduty: [P1] INCIDENT CREATED — Colab API Gateway
Summary: API Gateway returning 5xx
Service: Colab API Gateway
Assigned to: @[oncall_name]
Acknowledge: [link] | View Incident: [link]
```

### Slack app integrations required before launch

- [ ] PagerDuty for Slack (app installed; connected to PagerDuty org)
- [ ] Pingdom (or AWS CloudWatch) alert webhook → `#status-alerts`
- [ ] GitHub Actions deployment notifications → `#deploys`
- [ ] Sentry alert webhook → `#incidents` (P1/P2 alerts only; not every error)

---

## 2. Discord (Community-Facing)

Discord is used for **public-facing status communication only** when outages affect users and last >1 hour. Technical details are never shared in Discord.

| Channel | Purpose | Who posts | Notes |
|---------|---------|-----------|-------|
| `#status-updates` | Outage + resolution announcements | Founders/moderators only | No @everyone unless P1 |
| `#beta-general` (beta period only) | General beta discussion | Beta participants | During beta: higher engagement |

### Discord notification policy

Post to `#status-updates` when:
- P1 incident and outage duration >30 min
- P2 incident affecting majority of users and duration >1h
- Scheduled maintenance >5 min downtime

Do NOT post:
- Technical root cause details before postmortem
- Internal system names (EKS, RDS, etc.)
- Personal names of engineers involved
- Speculation about the cause

---

## 3. PagerDuty Bridge Configuration

### Slack /pd trigger command

Configure Slack PagerDuty integration to allow on-call to trigger incidents from Slack:

```
/pd trigger [service] [severity] [description]
```

Example:
```
/pd trigger "Colab Chat Service" P2 "WebSocket connections failing for 15% of users"
```

### PagerDuty → Status Page bridge

PagerDuty can auto-update Statuspage.io components via the Statuspage.io integration:
- Incident created in PagerDuty → corresponding Statuspage component set to "Investigating"
- Incident resolved in PagerDuty → Statuspage component set to prompt manual review

**Note**: Statuspage component updates should always be manually reviewed before final publish to avoid incorrect user-facing status.

### Incident Zoom/Meet call

For P1 incidents, an IC creates a meeting immediately:

```
# Zoom (if using Zoom)
/zoom start

# Google Meet (if using Workspace)
# Create ad-hoc meeting; paste link in #incidents-p1
```

Link format in Slack:
```
:movie_camera: P1 call: https://meet.google.com/xxx-xxxx-xxx
```

---

## 4. Communication Timeline (P1 Reference)

| Time | Action | Channel |
|------|--------|---------|
| T+0 | PagerDuty fires | PagerDuty app |
| T+0 | PagerDuty auto-posts to Slack | #incidents-p1 |
| T+5 | On-call acknowledges; posts update | #incidents-p1 |
| T+5 | Status page: "Investigating" | Statuspage.io |
| T+5 | Incident call started | Zoom/Meet link in #incidents-p1 |
| T+15 | Update post (even if no new info) | #incidents-p1 |
| T+30 | Status page: update | Statuspage.io |
| T+30 | Discord post (if user-visible) | Discord #status-updates |
| T+30–T+120 | Updates every 15–30 min | #incidents-p1 + Statuspage |
| T+resolution | Resolved post + Statuspage update | All channels |
| T+resolution | Discord resolution post | Discord #status-updates |
| T+24h | Draft postmortem started | #postmortems (link) |
| T+72h | Postmortem published | #postmortems + Notion |

---

## 5. Shared Credentials and Tools

| Resource | Location | Access |
|----------|---------|--------|
| PagerDuty dashboard | pagerduty.com | Engineering team login |
| Statuspage.io dashboard | manage.statuspage.io | Engineering team login |
| Pingdom dashboard | pingdom.com | Engineering team login |
| Sentry dashboard | sentry.io/colab | Engineering team login |
| CloudWatch dashboards | AWS Console | IRSA / engineering IAM role |
| Grafana dashboards | Grafana Cloud | Engineering team login |

All shared credentials stored in 1Password team vault (or equivalent), not in Slack or email.
