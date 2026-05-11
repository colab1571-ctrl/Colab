# 018 — Accessibility + i18n Hardening

**Phase**: P17.
**Mission**: Stamp WCAG 2.1 AA across every client surface (RN + 3× Next.js). Bake i18n infra so adding Spanish, French, Portuguese, Hindi, etc., is a translation pass — not a refactor.

## In scope

### Accessibility (RN + Web)
- Screen-reader labels on every interactive element (TalkBack, VoiceOver).
- Dynamic Type / Scalable Text up to 200%.
- Color contrast ≥4.5:1 (text) / 3:1 (UI).
- Focus visible + keyboard navigation on Web.
- Reduced-motion preference honored.
- Form errors associated with inputs.
- Live regions for chat + notifications.
- Touch target ≥44×44pt.

### Internationalization
- All strings externalized via `react-i18next` (Web) + `i18n-js` (RN).
- ICU MessageFormat for plurals + gender + select.
- Locale detection: device locale; user override in settings.
- Date / number / currency formatting via Intl.* (web + RN polyfilled).
- RTL-safe layouts (logical CSS properties on web; `I18nManager.allowRTL` on RN — even though no RTL locale ships at launch).
- Locale message catalogs in `packages/i18n/locales/<lang>.json`.

### QA tooling
- axe-core CI checks for Web (Playwright + @axe-core/playwright).
- React Native Accessibility lints (`eslint-plugin-react-native-a11y`).
- Color-contrast lint via `stylelint-a11y`.

## Dependencies

- **Hard**: 002 Shared Platform.
- **Cross-cutting**: applies retroactively to every feature.

## Owned entities (none)

This is a quality-gate phase; outputs are deltas to existing screens.

## Acceptance criteria

- axe-core CI passes with zero serious/critical findings on every web app.
- Mobile screen-reader-driven smoke tests pass for the 10 primary flows.
- Locale switch in settings updates active language in <1s.
- A pseudo-locale test (e.g., `qps-ploc`) shows no hardcoded strings + no truncation in expanded copy.

## NFRs

- A11y CI runtime <5 min on each PR.

## Open

- Launch-day locale list — confirmed English-only; infra still ready.
