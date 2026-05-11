# 015 — Help & Support

**Phase**: P14.
**Services**: `support-svc`.
**Mission**: FAQ surfaces, Community Guidelines + legal pages, support ticket intake with categorized SLAs, AI chatbot (OpenAI, bounded to FAQ + ticket creation), CSAT.

## In scope (master Journey F FR-F-1..F-6)

- Self-service FAQ (Markdown sourced from `docs/faq/` and rendered in both RN + Web).
- Community Guidelines / ToS / Privacy / DMCA notice pages.
- Live outage status page (read from Statuspage.io or PagerDuty Status — Phase 5 picks).
- AI chatbot: bounded prompt + retrieval over FAQ + can create a ticket on hand-off.
- Support ticket categories + SLAs:
  - Harassment / threats: 4h ack / 24h resolve
  - IP / DMCA: 24h ack / 7d resolve (+ statutory)
  - Payment: 24h ack / 72h resolve
  - Technical: 24h ack / 5d resolve
  - Other: 48h ack / 7d resolve
  - Premium Pro: 2× faster ack.
- Post-resolution CSAT (1–5).

## Dependencies

- **Hard**: 002, 003.
- **Soft**: 008 Moderation (Harassment/IP tickets cross-link to moderation cases), 013 Billing (Payment tickets), 016 Admin (support console + queue).

## Owned entities

- `SupportTicket`: id, user_id, category, subject, body, status (open|in_progress|pending_user|resolved|closed), priority, sla_ack_due, sla_resolve_due, assigned_to, created_at, first_response_at, resolved_at.
- `SupportTicketEvent`: ticket_id, kind (created|reply|status_change|resolution|csat), actor (user|agent|system), body, created_at.
- `SupportCSAT`: ticket_id, score (1–5), comment, created_at.
- `KbArticle` (FAQ index): slug, title, body_md, tags[], updated_at.

## API surface

- `GET /faq` — list articles (Markdown payload)
- `POST /support/chatbot` body `{message, ticket_id?}` → streaming reply + optional ticket creation
- `POST /support/tickets` body `{category, subject, body, attachments?}`
- `GET /support/tickets`, `GET /support/tickets/{id}`, `POST /support/tickets/{id}/reply`
- `POST /support/tickets/{id}/csat` body `{score, comment?}`
- `GET /status` — outage feed

## Acceptance criteria

- FAQ renders in RN + Web from a single source.
- Chatbot answers from FAQ retrieval; if confidence below threshold, suggests creating a ticket.
- Ticket creation triggers email confirmation + push.
- SLA timers visible to admins (§016 console); breach triggers escalation event.
- CSAT prompt fires on resolution.

## NFRs

- Ticket create P95 <300ms.
- Chatbot stream first token <1.5s.

## Open

- Statuspage.io vs self-hosted status page — Phase 5 cost vs control trade-off.
