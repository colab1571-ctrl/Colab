# Incident Communication — Templates and Protocols

**Version**: 1.0  
**Date**: 2026-05-11

---

## 1. Communication Matrix by Severity

| Severity | Internal | Status Page | User Email | Community Discord |
|----------|---------|-------------|-----------|------------------|
| P1 | Immediate: #incidents-p1 + @oncall + @engineering-lead | Yes — immediate | If data breach or >30 min outage | Yes — if outage >1h |
| P2 | Immediate: #incidents | Yes — within 15 min | If affecting majority of users | If widespread impact |
| P3 | #incidents within 30 min | Maybe — if user-visible | No | No |
| P4 | Ticket created; #engineering if useful | No | No | No |

---

## 2. Statuspage.io Incident Templates

### Investigating (post within 5 min of P1 detection)

```
Title: [SERVICE] — Investigating issue

Body:
We are investigating reports of {service_name} issues. Our engineering team
has been alerted and is actively investigating. We will provide an update
within 15 minutes.

Status: Investigating
Affected components: {component_list}
```

### Identified (post when root cause is known)

```
Title: [SERVICE] — Issue Identified

Body:
We have identified the cause of the {service_name} issue: {brief_technical_description}.
Our team is working on a fix and expects to deploy it within {estimated_time}.

We will provide updates every 30 minutes or sooner as the situation develops.

Status: Identified
Affected components: {component_list}
```

### Monitoring (post when fix is deployed but not yet confirmed)

```
Title: [SERVICE] — Fix Deployed, Monitoring

Body:
A fix has been deployed for the {service_name} issue. We are closely monitoring
the situation to confirm full resolution. Services are expected to be fully
restored shortly.

If you continue to experience issues, please contact us at support.[brandname].com.

Status: Monitoring
Affected components: {component_list}
```

### Resolved (post when fully confirmed stable)

```
Title: [SERVICE] — Resolved ✓

Body:
The {service_name} issue has been resolved. All systems are now operating
normally.

Duration: {start_time} – {end_time} UTC ({duration})
Root cause summary: {brief_summary}

We apologize for any disruption this caused. A full postmortem will be
published within 72 hours.

Status: Resolved
```

---

## 3. Slack Internal Templates

### P1 declaration

Post to #incidents-p1, ping @oncall @engineering-lead:

```
:rotating_light: P1 INCIDENT DECLARED :rotating_light:

Service: {service_name}
Impact: {impact_description}
Detected: {time} UTC
Incident commander: {name}

Statuspage: {link}
Runbook: {link}
Incident channel: #{channel_name}

Call: {Zoom/Google Meet link}
```

### P2 declaration

Post to #incidents:

```
:warning: P2 INCIDENT

Service: {service_name}
Impact: {impact_description}
Detected: {time} UTC
Owner: @{on_call_name}

Investigating... updates in this thread.
```

### Resolution announcement

Post to #incidents:

```
:white_check_mark: RESOLVED — {service_name}

Duration: {duration}
Root cause: {one_line_summary}
Users affected: {estimate}
Postmortem: coming within 72h

Closing incident channel.
```

---

## 4. Community Discord Templates (for #status-updates)

Post only when outage affects most users or lasts >1 hour. Do not post raw technical details.

### Active incident post

```
:warning: We're currently experiencing an issue with {feature_name}.

Our team is actively working on a fix. You can follow real-time updates at:
https://status.[brandname].com

We'll update this channel when the issue is resolved. Thank you for your patience.
```

### Resolution post

```
:white_check_mark: The {feature_name} issue has been resolved. All systems
are back to normal.

If you're still experiencing issues, please shake your device to send feedback
or contact us at support.[brandname].com.

Apologies for the disruption!
```

---

## 5. User Email Template (P1 Data-Related Incidents)

Send via SES only when required by law (data breach) or when outage exceeds 4 hours and affects majority of users.

**From**: noreply@[brandname].com  
**Reply-to**: support@[brandname].com  
**Subject**: [BRAND_NAME] Service Update — {date}

```
Hi {first_name},

We want to let you know about an issue that may have affected your experience
with [BRAND_NAME].

What happened: {plain-English description, no technical jargon}

Were you affected: {Yes — your account was/was not affected / We're still investigating}

What we're doing: {current remediation status}

What you should do: {user action if any, or "No action required"}

We take reliability seriously and apologize for any disruption this caused.
Our full postmortem will be published at {URL} within 72 hours.

Questions? Contact us at support.[brandname].com.

— The [BRAND_NAME] team
```

**Note on data breach notification**: If PII was potentially exposed, legal counsel must review the email before send. Breach notification timelines vary by jurisdiction (US: varies by state; CA: 72h to regulator; AU: 30 days to OAIC; NZ: as soon as practicable; IN: 6h to CERT-In).

---

## 6. Incident Naming Convention

Format: `INC-{YYYYMMDD}-{sequence}` (e.g., `INC-20260511-001`)

- Sequence resets each calendar day
- Name used in: Slack channel name, PagerDuty incident title, Statuspage incident, postmortem document
- Slack channel format: `#inc-20260511-001-{short_description}`

---

## 7. Post-Incident Notification

After resolution, notify:
1. **Status page subscribers**: Auto-notified via Statuspage email
2. **Discord**: Resolution post in #status-updates (if incident was announced there)
3. **Affected enterprise customers**: Direct email if applicable (not at launch — no enterprise tier)
4. **Internal postmortem announcement**: In #postmortems channel when published
