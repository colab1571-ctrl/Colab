# 018 — Accessibility + i18n Hardening: Implementation Plan

**Phase**: P17 — Post-feature hardening pass.
**Status**: Ready for implementation.
**Last updated**: 2026-05-11.

---

## 1. Mission Recap

Colab is an AI-powered networking and collaboration platform for Gen Z/Gen Alpha artist-preneurs (18+), shipping to US, Canada, Australia, New Zealand, and India at launch. NFR-5 mandates **WCAG 2.1 AA** on every client surface (React Native/Expo + three Next.js apps). NFR-6 mandates that all strings are externalized from day one so that adding a second language is a translation pass, not a refactor — English is the only locale at launch but the infrastructure must be fully ready.

This spec covers the retroactive quality gate applied in P17. It is cross-cutting: every feature spec (001–017) ships partial deltas here. The outputs are: (1) a running `docs/a11y-checklist.md`; (2) `packages/i18n/locales/en.json` (and the skeleton structure for future locales); (3) CI jobs; (4) lint rule configs; and (5) Storybook a11y addon configuration.

No net-new user-facing features are delivered. All work is measurable via CI gates and smoke-test scripts.

---

## 2. Research — Libraries and Tooling

### 2.1 Web i18n

| Library | Version | Role |
|---|---|---|
| `react-i18next` | v15 | Primary React hook-based i18n library for all three Next.js apps. Wraps `i18next` core. Provides `useTranslation`, `Trans`, `I18nextProvider`. |
| `i18next` | v23+ | Core engine: namespace loading, interpolation, fallback chain, language detection plugin hooks. |
| `i18next-icu` | latest | ICU MessageFormat plugin for `i18next`. Enables `{count, plural, one{# item} other{# items}}`, `{gender, select, male{…} female{…} other{…}}`, and `{value, select, …}` patterns natively. Required for correct pluralization in any future locale beyond English. |
| `i18next-http-backend` | latest | Lazy-loads locale JSON files from `/locales/<lang>/<ns>.json` at runtime (SSR + client). Avoids bundling all locales at build time. |
| `i18next-browser-languagedetector` | latest | Detects locale from: `querystring` → `localStorage` → `navigator.language` → `htmlTag`. Priority overridden by user-settings value (see §4). |
| `FormatJS` (`@formatjs/intl-*`) | latest | Polyfills for `Intl.PluralRules`, `Intl.RelativeTimeFormat`, `Intl.NumberFormat`, `Intl.DateTimeFormat` for environments that lack them (older Android WebViews, Node test runners). |

### 2.2 React Native i18n

| Library | Version | Role |
|---|---|---|
| `i18n-js` | v4 | Lightweight i18n library for React Native. Works without the browser Intl API; uses bundled pluralization rules. Translates keys with ICU-like interpolation. Pairs with `react-native-localize` for device locale. |
| `react-native-localize` | latest | Native module exposing `getLocales()`, `findBestAvailableLanguage()`, `getNumberFormatSettings()`, `uses24HourClock()`, `getTemperatureUnit()`. Used in locale-detection priority chain (§4). Fires `change` event on locale change (user changes device language in Settings). |

### 2.3 Web Accessibility Tooling

| Library | Role |
|---|---|
| `axe-core` | Core a11y rule engine. Runs in browser; detects WCAG 2.1 AA violations programmatically. |
| `@axe-core/playwright` | Playwright integration. Used in CI: every web PR runs `checkA11y(page)` via `@axe-core/playwright` before merge. Results are surfaced as GitHub Checks annotations. |
| `eslint-plugin-jsx-a11y` | Static analysis for JSX: warns on missing `alt`, missing `aria-label`, non-interactive elements with click handlers, etc. Added to `consumer-web`, `admin-web`, and `marketing-web` ESLint configs. |
| `stylelint-a11y` | Stylelint plugin enforcing contrast-safe CSS rules: `no-outline-none`, `media-prefers-reduced-motion`, `font-size-is-readable`, `no-display-none`. Added to all web app Stylelint configs. |
| `@storybook/addon-a11y` | Storybook addon. Runs `axe-core` in the Storybook canvas per story. Every `@colab/ui` component story must pass before the component is consumed by an app. |

### 2.4 React Native Accessibility Tooling

| Library | Role |
|---|---|
| `eslint-plugin-react-native-a11y` | ESLint plugin for RN-specific a11y rules: `has-accessibility-hint`, `has-valid-accessibility-role`, `no-nested-touchables`, `interactive-support-focus`, `touchable-has-accessible-min-size`. Added to RN ESLint config. |
| Detox (existing) | Used for RN e2e. Extended in this phase with Accessibility API hooks (`element.getAccessibilityLabel()`, `element.getAccessibilityValue()`) for screen-reader smoke flows (§10). |

---

## 3. i18n Architecture

### 3.1 Package Layout

```
packages/
  i18n/
    locales/
      en/
        common.json
        auth.json
        profile.json
        discovery.json
        invite.json
        collab.json
        chat.json
        billing.json
        support.json
        notifications.json
        moderation.json
        admin.json
        errors.json
      qps-ploc/          # pseudo-locale for QA (§6)
        common.json
        auth.json
        … (all namespaces)
    src/
      index.ts           # re-exports i18next instance (web) + i18n-js instance (RN)
      web.ts             # web-specific i18next init
      native.ts          # RN-specific i18n-js init
      icu-format.ts      # i18next-icu plugin registration
      locale-detect.ts   # shared priority-chain logic
      types.ts           # generated TypeScript types from en/*.json keys (via i18next-parser or typesafe-i18n codegen)
    package.json
```

**Design rule**: The `packages/i18n` workspace package is the single source of truth for all string catalogs. Apps import from `@colab/i18n` — never define strings inline.

### 3.2 Namespace Strategy

Each namespace maps to a product surface. Namespaces are loaded lazily per route.

| Namespace | Contents |
|---|---|
| `common` | Shared: app name, navigation labels, loading states, generic error messages, modal confirmations, dates/times format patterns, form field labels shared across surfaces |
| `auth` | Signup, login, password reset, email verification, age attestation, ToS acceptance, OAuth prompts |
| `profile` | Profile setup, edit, portfolio upload, badge descriptions, vocation categories, sub-tags |
| `discovery` | Feed, swipe card, filter labels, "Picked for you", profile detail view, save action |
| `invite` | Vibe Check compose, received/sent lists, accept/reject dialogs, expiry notices |
| `collab` | Collaboration workspace headers, status labels (Still Deciding / In Progress / Completed / Didn't Work Out), archive nudge, feedback flow |
| `chat` | Chat input, message types, file picker, voice note, AI command palette (`/mockup-image`, etc.), AI consent dialog, export prompt |
| `billing` | Tier names, feature descriptions, pricing screen, credit wallet, dunning notices, refund flow |
| `support` | FAQ categories, ticket form labels, SLA notices, CSAT labels |
| `notifications` | Push-opt-in card, notification preference labels, each notification type's body template |
| `moderation` | Report dialog, content warning overlays, mod action notices shown to end users |
| `admin` | Admin console UI strings (separate app; loaded only by `admin-web`) |
| `errors` | All error message keys — maps to HTTP status + domain error codes |

### 3.3 ICU MessageFormat

All namespaces use ICU MessageFormat syntax via `i18next-icu`. The raw JSON values are ICU strings; the library handles compilation.

**Web example** (`packages/i18n/src/web.ts`):

```ts
import i18next from 'i18next';
import ICU from 'i18next-icu';
import HttpBackend from 'i18next-http-backend';
import LanguageDetector from 'i18next-browser-languagedetector';

i18next
  .use(ICU)
  .use(HttpBackend)
  .use(LanguageDetector)
  .init({
    fallbackLng: 'en',
    ns: ['common'],          // default; lazy-loaded per route
    defaultNS: 'common',
    backend: { loadPath: '/locales/{{lng}}/{{ns}}.json' },
    detection: {
      order: ['querystring', 'localStorage', 'navigator', 'htmlTag'],
      caches: ['localStorage'],
    },
    interpolation: { escapeValue: false },
  });
```

**RN example** (`packages/i18n/src/native.ts`):

```ts
import { I18n } from 'i18n-js';
import * as RNLocalize from 'react-native-localize';
import en from '../locales/en/common.json';

export const i18n = new I18n({ en });
i18n.enableFallback = true;
i18n.defaultLocale = 'en';
i18n.locale = RNLocalize.findBestAvailableLanguage(['en'])?.languageTag ?? 'en';

RNLocalize.addEventListener('change', () => {
  i18n.locale = RNLocalize.findBestAvailableLanguage(['en'])?.languageTag ?? 'en';
});
```

---

## 4. Locale Detection Priority

The active locale is resolved using the following ordered priority chain, evaluated at app start and on user-settings change:

```
1. User-saved preference  (stored in profile-svc: User.locale_preference; synced to AsyncStorage/localStorage)
2. Device locale          (react-native-localize.getLocales()[0].languageTag  on RN;
                           navigator.language  on Web)
3. Fallback               'en'
```

**Rules**:
- If the device locale is not in the supported locale list, the next step is tried.
- The user-settings screen exposes a "Language" picker (even at launch with only English) so the infra is exercised and the UI exists for future locales.
- Locale change in settings takes effect within 1 second (acceptance criterion from spec §045).
- On RN, `I18nManager.allowRTL(true)` and `I18nManager.forceRTL(false)` are set at app init so that adding an RTL locale later requires zero layout work.

---

## 5. Key Naming Convention

All translation keys follow a three-segment dot-notation:

```
<feature>.<area>.<element>
```

| Segment | Description | Example |
|---|---|---|
| `feature` | The namespace / product surface | `auth`, `discovery`, `collab`, `common` |
| `area` | The screen, section, or component within the surface | `login`, `signup`, `feed`, `profile_card` |
| `element` | The specific UI element or message | `submit_btn`, `placeholder`, `error_required`, `heading` |

**Examples**:

```json
// packages/i18n/locales/en/auth.json
{
  "login": {
    "heading": "Welcome back",
    "email_label": "Email address",
    "email_placeholder": "you@example.com",
    "password_label": "Password",
    "submit_btn": "Sign in",
    "forgot_password_link": "Forgot password?",
    "error_invalid_credentials": "Incorrect email or password.",
    "error_account_locked": "Your account has been temporarily locked. Try again in {minutes, number} {minutes, plural, one{minute} other{minutes}}."
  },
  "signup": {
    "heading": "Create your account",
    "submit_btn": "Create account",
    "tos_agreement": "By signing up, you agree to our <tosLink>Terms of Service</tosLink> and <privacyLink>Privacy Policy</privacyLink>.",
    "age_attestation": "I confirm I am 18 years of age or older."
  }
}
```

**Conventions enforced by lint/codegen**:
- Keys use `snake_case`.
- No key may contain raw English copy as the key name (e.g., `"Submit"` as a key is banned; `submit_btn` is correct).
- All keys present in `en/` must exist in every other locale file (enforced by `i18next-parser` missing-key detection in CI).
- Dynamic values use ICU named placeholders: `{count}`, `{name}`, `{date}` — never positional `{0}`.

---

## 6. Pseudo-Locale `qps-ploc` for QA

`qps-ploc` (Microsoft's standard pseudo-locale tag) is used in CI and QA to catch two classes of defect:

1. **Hardcoded strings** — any UI text that doesn't change when `qps-ploc` is active is a hardcoded string.
2. **Layout truncation** — `qps-ploc` strings are ~40% longer than English, exposing fixed-width containers, single-line clamps with no ellipsis, and overflow-hidden without accessible text alternatives.

### 6.1 Expansion Algorithm

Every `qps-ploc` string is generated from the English source by the `scripts/gen-pseudo-locale.ts` build script:

```
Input:  "Sign in"
Output: "[Ŝĩĝñ ĩñ Ééxxpánndéédd!!]"
```

Steps:
1. Wrap in `[` … `]` — detects truncation at either end.
2. Append ` Ééxxpánndéédd!!` — approximately 40% length increase.
3. Substitute Latin characters with decorated Unicode equivalents (vowels → accented; consonants → dotted) using the standard `qps-ploc` character map.
4. Inject Unicode bidi markers `‪` (LRE) … `‬` (PDF) around each string to verify bidi-neutrality of the layout.

### 6.2 CI Usage

- `packages/i18n/locales/qps-ploc/` is generated at build time; never hand-edited.
- The CI snapshot test job (`pseudo-locale-snapshot.yml`) runs the web app with `?lng=qps-ploc` and takes Playwright screenshots of every route, diffed against a baseline. Any new truncation or overflow triggers a review gate.
- On RN, the Detox pseudo-locale job sets `i18n.locale = 'qps-ploc'` before running the onboarding flow; it asserts that no `Text` component clips below 1 line unless it has `numberOfLines` + `accessibilityLabel` set.

---

## 7. Pluralization, Gender, and Select Examples

All examples use ICU MessageFormat inside `i18next-icu` (web) and equivalent manual patterns in `i18n-js` (RN until `i18n-js` v5 full ICU support).

### 7.1 Pluralization — English

```json
{
  "invite": {
    "quota_remaining": "You have {count, plural, one{# Vibe Check} other{# Vibe Checks}} remaining this week.",
    "requests_received": "{count, plural, =0{No new requests} one{1 new request} other{# new requests}}"
  }
}
```

### 7.2 Pluralization — Future locale (Spanish example, not shipped at launch)

```json
{
  "invite": {
    "quota_remaining": "Te {count, plural, one{queda # Vibe Check} other{quedan # Vibe Checks}} esta semana."
  }
}
```

### 7.3 Gender Select

```json
{
  "collab": {
    "feedback_gave": "{partnerName} {gender, select, male{gave his feedback} female{gave her feedback} other{gave their feedback}}."
  }
}
```

### 7.4 Nested Select + Plural

```json
{
  "billing": {
    "tier_usage_summary": "You are on {tier, select, free{the Free plan} premium{Premium} pro{Premium Pro} other{an unknown plan}} with {credits, plural, =0{no AI credits} one{# AI credit} other{# AI credits}} remaining."
  }
}
```

### 7.5 Date and Number Formatting

Do **not** hardcode date/number formatting in translation strings. Use `Intl.DateTimeFormat` and `Intl.NumberFormat` (with FormatJS polyfills) in component code, passing only the formatted string as an interpolation value:

```ts
// In component:
const formatted = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(-3, 'day');
t('discovery.profile_card.last_active', { relativeTime: formatted });
// en.json: "Active {relativeTime}"  → "Active 3 days ago"
```

---

## 8. Accessibility Checklist

The living checklist lives at `docs/a11y-checklist.md` and is updated as components are audited. Below is the master template every interactive element must satisfy before P17 is considered closed.

### 8.1 Universal Rules (All Platforms)

Every interactive element — button, input, link, card (tappable), icon (tappable), toggle, checkbox, radio, select, slider — must satisfy:

| Requirement | Web (JSX) | RN |
|---|---|---|
| **Accessible label** | `aria-label` or `aria-labelledby` referencing visible text | `accessibilityLabel` prop |
| **Role** | Implicit via semantic HTML (`<button>`, `<a>`, `<input>`) or explicit `role=` | `accessibilityRole` prop |
| **State** | `aria-pressed`, `aria-checked`, `aria-expanded`, `aria-disabled` as appropriate | `accessibilityState={{ pressed, checked, expanded, disabled }}` |
| **Value** (sliders, progress) | `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, `aria-valuetext` | `accessibilityValue={{ now, min, max, text }}` |
| **Hint** (non-obvious actions) | `aria-describedby` pointing to hint text | `accessibilityHint` prop |
| **Touch target** | CSS `min-width: 44px; min-height: 44px` (or padding equivalent) | `minWidth: 44, minHeight: 44` in style; `hitSlop` for icons |
| **Focus order** | DOM order = visual order; no `tabindex > 0` | `accessible={true}`; use `accessibilityViewIsModal` for modals |
| **Focus visible** | `:focus-visible` ring, never `outline: none` without replacement | Native focus ring (Fabric) |

### 8.2 Element-Specific Requirements

**Buttons**

- Must have a label that describes the action (not just "Click here").
- Loading state: `aria-busy="true"` / `accessibilityState={{ busy: true }}` + label changes to "Loading, please wait".
- Disabled state: `aria-disabled="true"` / `accessibilityState={{ disabled: true }}` — do **not** remove from tab order when disabled (preserves discoverability).

**Inputs (text, password, search)**

- Associated `<label>` (web) or `accessibilityLabel` (RN).
- Error messages: `aria-describedby` on the input pointing to the error container / live region.
- Required fields: `aria-required="true"` / `accessibilityHint` includes "required".
- Password fields: `secureTextEntry` on RN; `type="password"` with show/hide toggle labeled "Show password" / "Hide password".

**Links**

- Label must make sense out of context (no "click here", "read more" without context).
- External links: `aria-label` appends "(opens in new tab)" when `target="_blank"`.

**Cards (tappable)**

- The entire card is a single focusable element.
- `accessibilityRole="button"` (RN) or `role="button"` / `<button>` wrapper (web).
- Label synthesizes the key information: e.g., "Alex Rivera, Photographer, Los Angeles. Tap to view profile."

**Icons (tappable)**

- `aria-label` / `accessibilityLabel` must describe the action, not the icon shape.
- Decorative icons: `aria-hidden="true"` / `importantForAccessibility="no"`.

**Toggles / Switches**

- `role="switch"` on web; `accessibilityRole="switch"` on RN.
- `aria-checked` / `accessibilityState={{ checked }}` reflects state.
- Label: "Open to remote work" not "Toggle".

**Image (portfolio, avatar)**

- Non-decorative: `alt` text (web) / `accessibilityLabel` (RN).
- Decorative: `alt=""` / `accessible={false}`.

**Chat messages**

- Live region on the message list: `aria-live="polite"` (web) / `accessibilityLiveRegion="polite"` (RN).
- Each message read as: "{sender name}: {message text}, sent {relative time}".

**Modals / Bottom sheets**

- `aria-modal="true"` (web) / `accessibilityViewIsModal={true}` (RN).
- Focus is trapped inside modal when open; returns to trigger element on close.
- Escape key closes modal on web.

**Form errors**

- Inline error: `role="alert"` or `aria-live="assertive"` so screen readers announce immediately.
- Summary errors (on submit): `role="alert"` container at top of form.

### 8.3 Color Contrast Ratios

- Normal text (< 18pt / < 14pt bold): **4.5:1** minimum against background.
- Large text (≥ 18pt regular, ≥ 14pt bold): **3:1** minimum.
- UI components and graphical objects (borders, icons conveying meaning, focus indicators): **3:1** minimum.
- Design tokens in `packages/ui/tokens/colors.ts` are validated at design-token generation time (see §9).

### 8.4 Dynamic Type / Scalable Text

- Web: all font sizes use `rem` units; no `px` overrides on text. Container widths use `min-height` not `height` so text reflow works.
- RN: `Text` components must use `allowFontScaling={true}` (default). Layouts must be tested at 200% font scale. Use `maxFontSizeMultiplier={2}` only when a fixed-width container genuinely cannot reflow (e.g., tab bar labels); in that case provide a full `accessibilityLabel`.

### 8.5 Reduced Motion

- Web: all CSS transitions and animations gated on `@media (prefers-reduced-motion: no-preference)`.
- RN: `useReducedMotion()` from `react-native-reanimated` (or `AccessibilityInfo.isReduceMotionEnabled()`) gates Reanimated animations.
- The swipe card animation (Discovery feed) must degrade gracefully to a fade transition at reduced motion.

---

## 9. Color-Contrast Tooling

### 9.1 Design Token Contrast Tests

File: `packages/ui/src/__tests__/color-contrast.test.ts`

At build time, the test iterates every `{text-color, background-color}` pair defined in the design token matrix and asserts WCAG contrast ratios using `get-contrast` (a small utility wrapping the WCAG formula):

```ts
import getContrast from 'get-contrast';
import { colors } from '../tokens/colors';

const TEXT_PAIRS = [
  { fg: colors.text.primary,   bg: colors.surface.default },
  { fg: colors.text.secondary, bg: colors.surface.default },
  { fg: colors.text.on_primary, bg: colors.brand.primary },
  // … all pairs enumerated
];

const UI_PAIRS = [
  { fg: colors.border.default,  bg: colors.surface.default },
  { fg: colors.icon.secondary,  bg: colors.surface.default },
  // … all pairs
];

test.each(TEXT_PAIRS)('text contrast $fg on $bg >= 4.5:1', ({ fg, bg }) => {
  expect(getContrast(fg, bg)).toBeGreaterThanOrEqual(4.5);
});

test.each(UI_PAIRS)('UI contrast $fg on $bg >= 3:1', ({ fg, bg }) => {
  expect(getContrast(fg, bg)).toBeGreaterThanOrEqual(3.0);
});
```

This test runs in the `test.yml` CI workflow. Failure blocks merge.

### 9.2 Stylelint a11y Rule Config

File: `apps/consumer-web/.stylelintrc.json` (and equivalents for `marketing-web`, `admin-web`):

```json
{
  "plugins": ["stylelint-a11y"],
  "rules": {
    "a11y/no-outline-none": true,
    "a11y/media-prefers-reduced-motion": true,
    "a11y/font-size-is-readable": [true, { "severity": "warning" }],
    "a11y/no-display-none": [true, { "severity": "warning" }],
    "a11y/content-property-no-static-value": true
  }
}
```

### 9.3 Storybook a11y Addon

File: `packages/ui/.storybook/main.ts` adds `@storybook/addon-a11y`. Every component story that renders an interactive element must include an a11y story test:

```ts
// Button.stories.ts
export const Primary: Story = { ... };
Primary.play = async ({ canvasElement }) => {
  const results = await axe(canvasElement);
  expect(results).toHaveNoViolations();
};
```

The Storybook build is run in CI (`storybook-test.yml`). `axe` violations in stories block merge.

### 9.4 ESLint Configs

**Web** (`apps/*/eslint.config.mjs`):

```js
import jsxA11y from 'eslint-plugin-jsx-a11y';
export default [
  jsxA11y.flatConfigs.recommended,
  // … other configs
];
```

**React Native** (`apps/mobile/eslint.config.mjs`):

```js
import rnA11y from 'eslint-plugin-react-native-a11y';
export default [
  { plugins: { 'react-native-a11y': rnA11y }, rules: rnA11y.configs.all.rules },
  // … other configs
];
```

---

## 10. React Native Screen-Reader Smoke Flows

Ten primary user flows are smoke-tested with screen reader simulation using Detox Accessibility API hooks. Tests live in `apps/mobile/e2e/a11y/`.

For each flow the test:
1. Enables Detox accessibility traversal.
2. Navigates each step using only simulated swipe-right (next element) and double-tap (activate).
3. Asserts that every interactive element encountered returns a non-empty `accessibilityLabel`.
4. Asserts that key status changes are announced via live regions.

| # | Flow | Key Assertions |
|---|---|---|
| 1 | **Signup** | Every form field has label; error messages announced; submit button labeled; ToS link labeled "Terms of Service, opens in browser". |
| 2 | **Complete profile** | Photo upload button labeled; vocation multi-select chips labeled with state (selected/unselected); bio char counter announced as value. |
| 3 | **Send Vibe Check (invite)** | Profile card labeled with synthesized summary; "Send Vibe Check" button labeled; synopsis input labeled; char counter announced; send confirmation announced. |
| 4 | **Accept invite** | Received request card labeled; accept/reject buttons labeled; "Match!" announcement fires as live region. |
| 5 | **Send chat message** | Keyboard input accessible; send button labeled; sent message appears in live region; attachment button labeled. |
| 6 | **Send AI mockup** | `/mockup-image` command labeled; consent dialog modal traps focus; "Generate" and "Cancel" labeled; loading state announced; result image labeled. |
| 7 | **Leave feedback** | Thumbs up/down labeled with role=button + state; tag chips labeled with checked state; submit labeled. |
| 8 | **Archive collaboration** | Status picker labeled; "Archive" confirmation dialog traps focus; confirmation button labeled; success toast announced. |
| 9 | **Submit support ticket** | Category picker labeled with selected value; description input labeled; submit button labeled; confirmation announced. |
| 10 | **Update settings** | Language picker labeled; notification toggles labeled with on/off state; each section header announced as heading. |

---

## 11. CI Integration

### 11.1 Web — axe-core per PR

File: `.github/workflows/a11y-web.yml`

```yaml
name: A11y — Web (axe-core)
on: [pull_request]
jobs:
  axe:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        app: [consumer-web, admin-web, marketing-web]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
      - run: npm run build --workspace=apps/${{ matrix.app }}
      - run: npm run start --workspace=apps/${{ matrix.app }} &
      - name: Run axe-core via Playwright
        run: npx playwright test apps/${{ matrix.app }}/e2e/a11y/
      # Fails on serious/critical violations; uploads report artifact
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: axe-report-${{ matrix.app }}
          path: apps/${{ matrix.app }}/axe-results/
```

Target: zero `serious` or `critical` axe violations. `moderate` and `minor` are surfaced as warnings and tracked in `docs/a11y-checklist.md`.

### 11.2 RN — Detox Accessibility Smoke Tests

File: `.github/workflows/a11y-rn.yml`

```yaml
name: A11y — RN (Detox smoke)
on: [pull_request]
jobs:
  detox-a11y:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
      - run: npx eas build --profile test --platform ios --local
      - run: npx detox test --configuration ios.sim.test --testPathPattern e2e/a11y
```

The 10 smoke flows (§10) must pass. Any `accessibilityLabel` assertion failure fails the job.

### 11.3 Pseudo-Locale Snapshot Tests

File: `.github/workflows/pseudo-locale.yml`

```yaml
name: i18n — Pseudo-locale snapshots
on: [pull_request]
jobs:
  pseudo:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npx ts-node scripts/gen-pseudo-locale.ts   # regenerates qps-ploc JSONs
      - run: npm run build --workspace=apps/consumer-web
      - name: Playwright snapshot with qps-ploc
        run: npx playwright test apps/consumer-web/e2e/pseudo-locale/ --update-snapshots=false
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: pseudo-locale-diffs
          path: apps/consumer-web/test-results/
```

Snapshot baselines committed to repo under `apps/consumer-web/e2e/pseudo-locale/__snapshots__/`. A diff means either a hardcoded string was added or a layout broke under text expansion.

### 11.4 Runtime Budget

- axe-core web job: target < 5 min per app (as per spec NFR).
- Detox a11y smoke: target < 15 min (10 flows on iOS simulator).
- Pseudo-locale snapshot: target < 5 min.
- Lint (eslint-plugin-jsx-a11y + react-native-a11y): runs inside existing `lint.yml`; no additional time cost.

---

## 12. Implementation Tasks

Each task has: ID, title, outcome, estimated hours, blocks (tasks this must ship before), blocked_by (tasks that must complete first).

### Group A — Infrastructure Setup

| ID | Title | Outcome | Est. hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| A-01 | Create `packages/i18n` workspace | Package scaffolded; `en/` namespace JSONs created with 100% of existing hardcoded strings; TypeScript types generated | 8 | all i18n tasks | 002 Shared Platform |
| A-02 | Integrate `react-i18next` + `i18next-icu` in all 3 Next.js apps | `I18nextProvider` wraps each app; `useTranslation` hook available; ICU format plugin registered | 4 | all web i18n tasks | A-01 |
| A-03 | Integrate `i18n-js` + `react-native-localize` in RN app | `i18n.locale` set from device; `change` listener wired; `t()` available throughout | 4 | all RN i18n tasks | A-01 |
| A-04 | Locale detection chain implementation | `locale-detect.ts` module; user-pref → device → `en` chain; settings screen Language picker | 3 | A-05 | A-02, A-03 |
| A-05 | User locale preference API endpoint + persistence | `PATCH /users/me/locale` in `profile-svc`; stored in `User.locale_preference`; synced on app launch | 3 | A-04 | 003 Auth/Profile |
| A-06 | Pseudo-locale generator script | `scripts/gen-pseudo-locale.ts`; generates `qps-ploc/` from `en/` | 3 | A-07 | A-01 |
| A-07 | Pseudo-locale CI workflow | `.github/workflows/pseudo-locale.yml`; snapshot baseline committed | 4 | — | A-06, A-02 |

### Group B — ESLint + Stylelint Tooling

| ID | Title | Outcome | Est. hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| B-01 | Add `eslint-plugin-jsx-a11y` to web ESLint configs | All three web apps linted; zero existing violations OR violations documented in suppression file with TODO | 3 | — | 002 |
| B-02 | Add `eslint-plugin-react-native-a11y` to RN ESLint config | RN app linted; zero existing violations OR documented suppression | 3 | — | 002 |
| B-03 | Add `stylelint-a11y` to web Stylelint configs | `no-outline-none`, `media-prefers-reduced-motion`, etc. enforced | 2 | — | 002 |
| B-04 | Storybook `@storybook/addon-a11y` in `packages/ui` | Addon shows axe panel per story; `axe` assertions added to interactive component stories | 4 | — | 002 |

### Group C — Design Token Contrast Tests

| ID | Title | Outcome | Est. hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| C-01 | Enumerate all color token pairs in contrast test | `color-contrast.test.ts` with all text pairs (≥4.5:1) and UI pairs (≥3:1) | 4 | — | 002 |
| C-02 | Fix any failing token contrast ratios | Updated token values in `packages/ui/tokens/colors.ts`; design sign-off | 4 | — | C-01 |
| C-03 | Wire contrast tests into `test.yml` CI | Contrast test job added; blocks merge on failure | 1 | — | C-01, C-02 |

### Group D — Web axe-core CI

| ID | Title | Outcome | Est. hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| D-01 | Playwright a11y test suite for `consumer-web` | Route-by-route `checkA11y` tests; zero critical/serious findings | 12 | — | A-02, B-01 |
| D-02 | Playwright a11y test suite for `marketing-web` | Same; zero critical/serious | 4 | — | A-02, B-01 |
| D-03 | Playwright a11y test suite for `admin-web` | Same; zero critical/serious | 6 | — | A-02, B-01 |
| D-04 | `a11y-web.yml` CI workflow | Runs D-01–D-03 per PR; < 5 min target | 2 | — | D-01, D-02, D-03 |

### Group E — RN Accessibility Remediation (per surface)

Each sub-task audits one surface against the checklist (§8) and makes the delta changes.

| ID | Title | Outcome | Est. hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| E-01 | Onboarding / Auth screens a11y audit + fix | All form fields labeled; errors in live regions; buttons labeled; 44pt targets | 6 | — | B-02 |
| E-02 | Profile setup screens a11y audit + fix | Photo upload, vocation chips, bio field, portfolio upload all labeled + 44pt | 5 | — | B-02 |
| E-03 | Discovery feed + profile detail a11y audit + fix | Card synthesized label; swipe actions labeled; filter sheet focus-trapped | 5 | — | B-02 |
| E-04 | Vibe Check send/receive a11y audit + fix | Synopsis input labeled; send/accept/reject 44pt + labeled; Match announcement | 4 | — | B-02 |
| E-05 | Chat screen a11y audit + fix | Message list live region; input labeled; send/attachment 44pt + labeled | 5 | — | B-02 |
| E-06 | AI assistant + mockup consent a11y audit + fix | Command palette labeled; consent modal focus-trapped; loading announced | 4 | — | B-02 |
| E-07 | Collaboration lifecycle + feedback a11y audit + fix | Status picker labeled; thumbs labeled + state; tag chips state; archive modal | 4 | — | B-02 |
| E-08 | Billing + payments a11y audit + fix | Tier cards labeled; IAP sheet focus-trapped; credit wallet labeled | 4 | — | B-02 |
| E-09 | Support ticket + FAQ a11y audit + fix | Category picker labeled; textarea labeled; CSAT labeled | 3 | — | B-02 |
| E-10 | Settings + notifications a11y audit + fix | Toggles labeled + state; language picker labeled; section headers as headings | 3 | — | B-02 |
| E-11 | Navigation shell + tab bar a11y audit + fix | Tab bar items labeled with role=tab + state; back buttons labeled | 2 | — | B-02 |

### Group F — Web Accessibility Remediation (per surface)

Mirrors E-01–E-11 for `consumer-web`. `admin-web` and `marketing-web` covered in D-03 and D-02 Playwright audits plus targeted fixes.

| ID | Title | Outcome | Est. hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| F-01 | Auth screens web a11y fix | Focus management after submit; error live regions; `:focus-visible` rings | 4 | — | B-01, B-03 |
| F-02 | Profile + onboarding web a11y fix | Labels, fieldsets, required markers, error associations | 4 | — | B-01, B-03 |
| F-03 | Discovery feed web a11y fix | Card keyboard nav; filter dialog modal; swipe card keyboard alternative (list mode) | 5 | — | B-01, B-03 |
| F-04 | Chat web a11y fix | Live region; keyboard-accessible send; file input labeled | 4 | — | B-01, B-03 |
| F-05 | AI assistant web a11y fix | Command palette keyboard nav; modal trapping; loading announced | 3 | — | B-01, B-03 |
| F-06 | Billing web a11y fix | Stripe Checkout iframe: out-of-scope (Stripe's responsibility); surround container labeled | 2 | — | B-01, B-03 |
| F-07 | Settings + notifications web a11y fix | Toggle `role="switch"`; headings hierarchy; keyboard nav | 3 | — | B-01, B-03 |

### Group G — String Externalization (i18n delta per surface)

Every hardcoded string found during E-* and F-* audits must be moved to `packages/i18n/locales/en/<ns>.json`.

| ID | Title | Outcome | Est. hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| G-01 | Auth surface strings externalized (web + RN) | All strings in `auth.json`; zero hardcoded strings in auth components | 4 | — | A-02, A-03 |
| G-02 | Profile surface strings externalized | All in `profile.json` | 4 | — | A-02, A-03 |
| G-03 | Discovery surface strings externalized | All in `discovery.json` | 3 | — | A-02, A-03 |
| G-04 | Invite surface strings externalized | All in `invite.json`; quota plural examples | 2 | — | A-02, A-03 |
| G-05 | Collab + chat strings externalized | All in `collab.json` + `chat.json`; status labels, feedback chip labels | 4 | — | A-02, A-03 |
| G-06 | Billing strings externalized | All in `billing.json`; tier names, credit labels, dunning messages | 3 | — | A-02, A-03 |
| G-07 | Support + notifications strings externalized | All in `support.json` + `notifications.json` | 3 | — | A-02, A-03 |
| G-08 | Errors + common strings externalized | All in `errors.json` + `common.json` | 3 | — | A-02, A-03 |
| G-09 | `i18next-parser` missing-key detection in CI | CI fails if a key exists in any locale but not in `en/`; and vice versa | 2 | — | A-01, G-01–G-08 |

### Group H — Detox Smoke Flows

| ID | Title | Outcome | Est. hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| H-01 | Write Detox a11y smoke flow: Signup (flow 1) | Test passes with screen-reader assertions | 3 | — | E-01, A-03 |
| H-02 | Complete profile (flow 2) | Test passes | 2 | — | E-02 |
| H-03 | Send Vibe Check (flow 3) | Test passes | 2 | — | E-03, E-04 |
| H-04 | Accept invite (flow 4) | Test passes | 2 | — | E-04 |
| H-05 | Send chat message (flow 5) | Test passes | 2 | — | E-05 |
| H-06 | Send AI mockup (flow 6) | Test passes | 2 | — | E-06 |
| H-07 | Leave feedback (flow 7) | Test passes | 2 | — | E-07 |
| H-08 | Archive collaboration (flow 8) | Test passes | 2 | — | E-07 |
| H-09 | Submit support ticket (flow 9) | Test passes | 2 | — | E-09 |
| H-10 | Update settings (flow 10) | Test passes | 2 | — | E-10 |
| H-11 | `a11y-rn.yml` CI workflow | All 10 flows run per PR; < 15 min | 2 | — | H-01–H-10 |

### Group I — Documentation

| ID | Title | Outcome | Est. hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| I-01 | Create `docs/a11y-checklist.md` | Living checklist covering all element types from §8; columns: component, platform, label, role, state, target, focus, status | 3 | — | — |
| I-02 | i18n contributor guide in `packages/i18n/README.md` | Key naming rules, how to add a new locale, ICU examples, pseudo-locale QA steps | 2 | — | A-01 |

### Effort Summary

| Group | Total Est. Hours |
|---|---|
| A — Infra setup | 29 |
| B — Lint/Storybook tooling | 12 |
| C — Contrast tests | 9 |
| D — Web axe-core CI | 24 |
| E — RN a11y remediation | 45 |
| F — Web a11y remediation | 25 |
| G — String externalization | 28 |
| H — Detox smoke flows | 21 |
| I — Documentation | 5 |
| **Total** | **198** |

---

## 13. Acceptance Criteria

All criteria must pass before P17 is considered done. Each criterion is verified by the method listed.

| # | Criterion | Verification |
|---|---|---|
| AC-01 | `axe-core` CI (`a11y-web.yml`) passes with **zero serious or critical** findings on all three web apps on every PR. | CI green on PR to `main`. |
| AC-02 | Detox a11y smoke tests pass for all 10 primary user flows on iOS simulator (and at least 8/10 on Android emulator, Android API variations noted). | `a11y-rn.yml` CI green. |
| AC-03 | Locale switch in settings updates active language in < 1 second (app does not reload; strings update reactively). | Detox timing assertion in flow 10; Playwright timing assertion for web settings. |
| AC-04 | Pseudo-locale `qps-ploc` test shows zero hardcoded English strings (any unchanged string between `en` and `qps-ploc` renders is a failure). | `pseudo-locale.yml` CI snapshot diff = zero new unresolved diffs. |
| AC-05 | Pseudo-locale test shows zero layout truncation (no `[` or `]` bracket clipped by overflow-hidden or numberOfLines without accessibilityLabel). | Playwright screenshot + Detox assertion in pseudo-locale jobs. |
| AC-06 | All color token contrast ratios pass: text ≥ 4.5:1, UI components ≥ 3:1. | `color-contrast.test.ts` in `test.yml` CI green. |
| AC-07 | `eslint-plugin-jsx-a11y` and `eslint-plugin-react-native-a11y` report zero errors (warnings allowed and tracked). | `lint.yml` CI green. |
| AC-08 | `stylelint-a11y` reports zero `no-outline-none` errors and zero `content-property-no-static-value` errors across all web apps. | `lint.yml` CI green. |
| AC-09 | Every interactive element (button/input/link/card/icon/toggle) in `docs/a11y-checklist.md` is marked "Pass" for all columns on both platforms. | Manual checklist review in PR description for each E-* and F-* task. |
| AC-10 | All user-facing strings (zero hardcoded copy) are loaded from `packages/i18n/locales/en/<ns>.json`. Verified by `i18next-parser` missing-key check. | `G-09` CI job green. |
| AC-11 | `@storybook/addon-a11y` shows zero violations in the Storybook build for all `@colab/ui` interactive components. | Storybook test CI job green. |
| AC-12 | A11y CI runtime < 5 min per web app (axe-core Playwright suite). | CI timing reported in GitHub Actions summary. |

---

## 14. Open Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| OR-01 | **tldraw embed (FR-C-4) is a third-party WebView** — a11y of the whiteboard canvas is not fully controllable. axe-core will not penetrate the iframe for arbitrary tldraw internals. | Medium | Medium | Wrap the tldraw WebView with an `accessibilityLabel` describing the whiteboard; provide a text-based alternative (project-plan view, FR-C-5) as the a11y-equivalent path. File a feature request with tldraw upstream for WCAG AA. Track as a documented exception in `docs/a11y-checklist.md`. |
| OR-02 | **Stripe Checkout iframe** — Stripe-owned UI; not WCAG-tested by Colab. | Low | Medium | Rely on Stripe's published WCAG 2.1 AA commitment. Add a note in `docs/a11y-checklist.md` citing Stripe's statement. Monitor Stripe's changelog. |
| OR-03 | **Persona SDK (selfie/liveness, ARC-18)** — native SDK UI is not authored by Colab. | Low | Medium | Wrap Persona modal with `accessibilityViewIsModal`; confirm with Persona that their SDK passes VoiceOver/TalkBack smoke tests. Document as vendor dependency. |
| OR-04 | **ICU plural data for future locales** — `i18n-js` v4 has limited ICU support; may need upgrade or custom plural rules for Hindi (which has two plural forms but different rules than English). | Medium | Low at launch | At launch, English only; risk is future. Pin `i18n-js` version; track upgrade to v5 or migration to `i18next` on RN as a pre-condition for first non-English locale. |
| OR-05 | **Dynamic Type at 200% breaks complex layouts** (e.g., the swipe card stack, the bottom tab bar). | Medium | Medium | Audit at 200% during E-03 and E-11. Acceptable mitigation for truly fixed-width elements: `maxFontSizeMultiplier={1.5}` with `accessibilityLabel` carrying the full text. Document all exceptions. |
| OR-06 | **198 estimated hours is cross-cutting across 17 feature specs** — actual hours depend on how thoroughly earlier specs externalized strings and labeled elements. Underestimate risk if earlier phases shipped with tech debt. | High | Medium | Conduct a rapid pre-audit at P17 start (one day of grep for hardcoded strings + one axe-core sweep of the current build) to calibrate actual scope before committing to a ship date. |
| OR-07 | **Android Detox a11y API differences** — `getAccessibilityLabel()` behavior differs between Android API levels; some assertions may require per-platform branching in tests. | Medium | Low | Run H-01–H-10 on both iOS simulator and Android API 33 emulator during initial writing; add platform guards where needed. Accept 8/10 flows on Android as launch gate (AC-02). |
| OR-08 | **i18next-parser false negatives** — dynamically constructed keys (e.g., `t(\`error.\${code}\`)`) will not be detected by static analysis. | Low | Low | Require all dynamic key sets to be exhaustively enumerated in a companion object that `i18next-parser` can statically scan (e.g., `const ERROR_KEYS = { ... }` with all possible values). Lint rule enforces no template-literal key construction. |

---

*End of plan — 018 Accessibility + i18n Hardening.*
