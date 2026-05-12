# Colab i18n Contributor Guide

**Phase**: P17 — Accessibility + i18n Hardening  
**Last updated**: 2026-05-11

All user-facing strings in Colab are loaded from `packages/i18n/locales/<lang>/<namespace>.json`. **Never hardcode English copy in component files.** This guide explains how to add strings, how to add a new locale, and how to run QA tools.

---

## 1. Architecture Overview

```
packages/i18n/
  locales/
    en/                  ← source of truth (English)
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
    qps-ploc/            ← auto-generated pseudo-locale (DO NOT edit)
      common.json … (all namespaces)
  src/
    init.ts              ← web (Next.js) i18next initialisation
    init-rn.ts           ← React Native i18n-js + react-native-localize init
    types.ts             ← shared TypeScript types
    useLocale.ts         ← locale switcher hook (web)
    loader.ts            ← synchronous loader (legacy / SSR)
  scripts/
    generate-pseudo.mjs  ← generates qps-ploc from en/
```

**Web** apps import from `react-i18next` using `useTranslation`:

```tsx
import { useTranslation } from "react-i18next";
// In your app entry point, ensure "@colab/i18n/src/init" is imported once.

function MyComponent() {
  const { t } = useTranslation("auth");          // loads auth namespace
  return <h1>{t("login.heading")}</h1>;          // → "Welcome back"
}
```

**React Native** uses `i18n` from `@colab/i18n/src/init-rn`:

```tsx
import { i18n } from "@colab/i18n/src/init-rn";

function MyScreen() {
  return <Text>{i18n.t("auth.login.heading")}</Text>;
}
```

---

## 2. Key Naming Convention

All keys follow three-segment `snake_case` dot-notation:

```
<namespace>.<area>.<element>
```

| Segment | Description | Example |
|---|---|---|
| namespace | Loaded namespace file | `auth`, `discovery`, `collab` |
| area | Screen or section | `login`, `feed`, `profile_card` |
| element | Specific UI element | `submit_btn`, `error_required`, `heading` |

**Rules**:
- Keys are `snake_case`. No camelCase, no hyphen-case.
- Keys must not be raw English copy (`"Submit"` as a key is banned; `submit_btn` is correct).
- Dynamic values use ICU named placeholders: `{name}`, `{count}` — never positional `{0}`.
- All dynamic key sets (e.g., error codes) must be exhaustively listed in a companion const — no template-literal key construction (`t(\`error.${code}\`)` is banned).

---

## 3. How to Add a New String

1. **Decide the namespace**: choose the namespace that matches the product surface. See the namespace table in the spec.

2. **Add the key to `packages/i18n/locales/en/<namespace>.json`**:

```json
// packages/i18n/locales/en/auth.json
{
  "login": {
    "new_key": "Your new English copy here."
  }
}
```

3. **Use the key in your component**:

```tsx
// Web:
const { t } = useTranslation("auth");
return <p>{t("login.new_key")}</p>;

// RN:
import { i18n } from "@colab/i18n/src/init-rn";
<Text>{i18n.t("auth.login.new_key")}</Text>
```

4. **Regenerate pseudo-locale**:

```bash
node packages/i18n/scripts/generate-pseudo.mjs
git add packages/i18n/locales/qps-ploc/
```

5. **CI will verify** that the key exists in `en/` and has a corresponding entry in `qps-ploc/` (via `i18next-parser` missing-key check in G-09).

---

## 4. ICU MessageFormat

All namespaces use ICU MessageFormat via `i18next-icu` (web) or equivalent patterns in `i18n-js` (RN).

### Plural

```json
{
  "invite": {
    "quota_remaining": "You have {count, plural, =0{no Vibe Checks} one{# Vibe Check} other{# Vibe Checks}} remaining this week."
  }
}
```

Usage:
```tsx
t("invite.quota_remaining", { count: 3 })
// → "You have 3 Vibe Checks remaining this week."
```

### Gender Select

```json
{
  "collab": {
    "feedback_given_a11y": "{name} {gender, select, male{gave his feedback} female{gave her feedback} other{gave their feedback}}."
  }
}
```

### Nested Select + Plural

```json
{
  "billing": {
    "tier_usage_summary": "You are on {tier, select, free{the Free plan} premium{Premium} pro{Premium Pro} other{an unknown plan}} with {credits, plural, =0{no AI credits} one{# AI credit} other{# AI credits}} remaining."
  }
}
```

### Date / Number Formatting

Do NOT hardcode date/number formatting in translation strings. Format in component code and pass as an interpolation value:

```tsx
const formatted = new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(-3, "day");
t("discovery.profile_card.last_active", { relativeTime: formatted });
// en.json: "Active {relativeTime}" → "Active 3 days ago"
```

---

## 5. Lazy-Loading Namespaces (Web)

The i18next HTTP backend loads namespace JSON files from `/locales/<lang>/<ns>.json` at runtime. Only `common` is loaded by default. Load additional namespaces per route:

```tsx
// In a page component or route layout:
const { t } = useTranslation(["collab", "chat"]);

// Or imperatively:
import i18next from "i18next";
await i18next.loadNamespaces(["billing"]);
```

For Next.js App Router, load namespaces in the server layout:

```tsx
// app/billing/layout.tsx
import i18next from "@colab/i18n/src/init";
await i18next.loadNamespaces(["billing"]);
```

---

## 6. Locale Detection Priority Chain

```
1. User-saved preference  (localStorage: "colab_locale" on web;
                           AsyncStorage: "colab_locale" on RN;
                           synced to profile-svc User.locale_preference)
2. Device locale          (navigator.language on web;
                           RNLocalize.findBestAvailableLanguage on RN)
3. Fallback               "en"
```

---

## 7. How to Add a New Locale

> English is the only shipped locale at launch. Adding a second locale is a translation pass — no code refactor needed.

1. **Create the locale directory**: `packages/i18n/locales/<lang>/` (e.g., `es/`).

2. **Copy all 13 namespace files** from `en/` to `<lang>/`:
   ```bash
   cp -r packages/i18n/locales/en packages/i18n/locales/es
   ```

3. **Translate all string values** in the new locale files. Keep all keys identical to `en/`. Do not add or remove keys — the CI missing-key check will fail.

4. **Register the locale** in `packages/i18n/src/init.ts` (web):
   ```ts
   export const SUPPORTED_LOCALES = ["en", "es"] as const;
   ```
   And in `packages/i18n/src/init-rn.ts` (RN) — update `SUPPORTED_LOCALES` and add imports.

5. **Update the Loader** (`src/loader.ts`): add `"es"` to the `Locale` type and add import.

6. **CI**: The `i18next-parser` missing-key check will verify parity between `en/` and `es/` on every PR.

7. **QA**: Run the pseudo-locale generator for the new locale (create a separate `gen-pseudo-<lang>.mjs` following the same pattern, or extend the existing script).

---

## 8. Pseudo-Locale QA

The `qps-ploc` pseudo-locale is generated automatically by `packages/i18n/scripts/generate-pseudo.mjs`.

```bash
# Regenerate (run after changing any en/ file)
node packages/i18n/scripts/generate-pseudo.mjs

# Preview what qps-ploc looks like
cat packages/i18n/locales/qps-ploc/auth.json | head -20
```

The pseudo-locale does four things:
1. Wraps all strings in `[` … `]` — detects truncation at either end.
2. Appends ` Ééxxpáändéd!!` — ~40% longer to expose fixed-width containers.
3. Substitutes Latin characters with decorated Unicode (vowels → accented, consonants → dotted).
4. Injects Unicode bidi markers (LRE/PDF) to verify bidi-neutrality.

**Do not hand-edit** `locales/qps-ploc/` — it is regenerated every CI run and changes are rejected.

---

## 9. Dynamic Key Sets (Error Codes)

Template-literal key construction is banned:
```ts
// ❌ BANNED — i18next-parser cannot detect this key:
t(`errors.${errorCode}`)

// ✅ CORRECT — enumerate all possible values:
const ERROR_KEY_MAP: Record<string, string> = {
  UNAUTHORIZED: "errors.UNAUTHORIZED",
  FORBIDDEN: "errors.FORBIDDEN",
  NOT_FOUND: "errors.NOT_FOUND",
  // … all values from errors.json
};
t(ERROR_KEY_MAP[errorCode] ?? "errors.unknown");
```

---

## 10. Useful Commands

```bash
# Generate pseudo-locale
node packages/i18n/scripts/generate-pseudo.mjs

# Check for missing keys (requires i18next-parser — add to CI via G-09)
npx i18next-parser --config i18next-parser.config.mjs

# Run axe-core tests locally
cd apps/consumer-web && npx playwright test e2e/a11y/

# Run pseudo-locale snapshots locally
cd apps/consumer-web && BASE_URL=http://localhost:3000 npx playwright test e2e/pseudo-locale/

# TypeScript check for i18n package
cd packages/i18n && npx tsc --noEmit
```
