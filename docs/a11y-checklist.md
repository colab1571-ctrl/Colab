# Colab Accessibility Checklist

**Standard**: WCAG 2.1 AA  
**Phase**: P17 — Accessibility + i18n Hardening  
**Last updated**: 2026-05-11

This is the living checklist for every interactive element across all Colab client surfaces. It is updated as each screen is audited and fixed. Every item must reach "Pass" before P17 is considered closed (AC-09).

## Status Key

| Symbol | Meaning |
|---|---|
| ✅ Pass | Requirement met; verified in CI or by manual smoke test |
| ⚠️ Warn | Non-blocking issue tracked; moderate/minor axe finding |
| ❌ Fail | Blocking; must fix before merge |
| 🔲 Todo | Not yet audited |
| N/A | Not applicable to this element/platform |

---

## 1. Universal Requirements (All Platforms)

Every interactive element must satisfy:

| Requirement | Web | RN |
|---|---|---|
| Accessible label | `aria-label` or `aria-labelledby` or visible `<label>` | `accessibilityLabel` prop |
| Role | Semantic HTML or explicit `role=` | `accessibilityRole` prop |
| State | `aria-pressed/checked/expanded/disabled/busy` as appropriate | `accessibilityState={}` |
| Value (sliders, progress) | `aria-valuenow/min/max/text` | `accessibilityValue={}` |
| Hint (non-obvious) | `aria-describedby` | `accessibilityHint` |
| Touch target | `min-width/height: 44px` (CSS) | `minWidth/Height: 44` or `hitSlop` |
| Focus order | DOM order = visual order; no `tabindex > 0` | `accessible={true}`; proper traversal |
| Focus visible | `:focus-visible` ring; never `outline:none` without replacement | Native focus ring |

---

## 2. Screen-by-Screen Status

### 2.1 Mobile (React Native / Expo)

#### Auth Screens

| Screen | Component | Label | Role | State | Target | Focus | Status |
|---|---|---|---|---|---|---|---|
| SignInScreen | Email input | ✅ | ✅ TextInput | N/A | ✅ | ✅ | ✅ Pass |
| SignInScreen | Password input | ✅ | ✅ TextInput | N/A | ✅ | ✅ | ✅ Pass |
| SignInScreen | Show/hide password btn | ✅ | ✅ button | N/A | ✅ hitSlop | ✅ | ✅ Pass |
| SignInScreen | Sign in button | ✅ (busy state) | ✅ button | ✅ busy/disabled | ✅ | ✅ | ✅ Pass |
| SignInScreen | Forgot password link | ✅ | ✅ link | N/A | ✅ hitSlop | ✅ | ✅ Pass |
| SignInScreen | Apple/Google/Phone btns | ✅ | ✅ button | N/A | ✅ | ✅ | ✅ Pass |
| SignInScreen | Error live region | ✅ assertive | ✅ alert | N/A | N/A | N/A | ✅ Pass |
| SignUpScreen | Email/Password inputs | 🔲 | 🔲 | N/A | 🔲 | 🔲 | 🔲 Todo |
| SignUpScreen | Age attestation checkbox | 🔲 | 🔲 | 🔲 checked | ✅ | 🔲 | 🔲 Todo |
| SignUpScreen | ToS checkbox | 🔲 | 🔲 | 🔲 checked | ✅ | 🔲 | 🔲 Todo |
| ForgotPasswordScreen | Email input | 🔲 | 🔲 | N/A | 🔲 | 🔲 | 🔲 Todo |
| VerifyScreen | OTP input | 🔲 | 🔲 | N/A | 🔲 | 🔲 | 🔲 Todo |

#### Discovery Screens

| Screen | Component | Label | Role | State | Target | Focus | Status |
|---|---|---|---|---|---|---|---|
| FeedScreen | Header title | ✅ | ✅ header | N/A | N/A | N/A | ✅ Pass |
| FeedScreen | Picked for You btn | ✅ | ✅ button | N/A | ✅ hitSlop | ✅ | ✅ Pass |
| FeedScreen | Filters btn | ✅ | ✅ button | N/A | ✅ hitSlop | ✅ | ✅ Pass |
| FeedScreen | Mode toggle btn | ✅ dynamic | ✅ button | N/A | ✅ hitSlop | ✅ | ✅ Pass |
| FeedScreen | ProfileCardItem | ✅ synthesised | ✅ button | N/A | ✅ | ✅ | ✅ Pass |
| FeedScreen | SwipeCard | ✅ | ✅ button | N/A | ✅ | ✅ | ✅ Pass |
| FeedScreen | SwipeCard Hide btn | ✅ with name | ✅ button | N/A | ✅ hitSlop | ✅ | ✅ Pass |
| FeedScreen | SwipeCard Save btn | ✅ with name | ✅ button | N/A | ✅ hitSlop | ✅ | ✅ Pass |
| FeedScreen | SwipeCard Pass btn | ✅ with name | ✅ button | N/A | ✅ hitSlop | ✅ | ✅ Pass |
| ProfileDetailScreen | Send Vibe Check btn | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 Todo |
| FiltersDrawer | Filter options | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 Todo |

#### Vibe Check / Invites

| Screen | Component | Label | Role | State | Target | Focus | Status |
|---|---|---|---|---|---|---|---|
| SendVibeCheckModal | Modal container | ✅ | ✅ accessibilityViewIsModal | N/A | N/A | ✅ | ✅ Pass |
| SendVibeCheckModal | Close button | ✅ | ✅ button | N/A | ✅ 44pt | ✅ | ✅ Pass |
| SendVibeCheckModal | Synopsis input | ✅ | ✅ TextInput | N/A | ✅ | ✅ | ✅ Pass |
| SendVibeCheckModal | Char counter | ✅ | ✅ polite live region | N/A | N/A | N/A | ✅ Pass |
| SendVibeCheckModal | Error region | ✅ | ✅ alert | N/A | N/A | N/A | ✅ Pass |
| SendVibeCheckModal | Send button | ✅ with name | ✅ button | ✅ busy/disabled | ✅ 44pt | ✅ | ✅ Pass |
| InboxScreen | Request cards | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 Todo |
| InboxScreen | Accept/Reject btns | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 Todo |
| MatchCelebrationScreen | Match announcement | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 Todo |

#### Chat

| Screen | Component | Label | Role | State | Target | Focus | Status |
|---|---|---|---|---|---|---|---|
| ChatRoomScreen | Message input | 🔲 | 🔲 | N/A | 🔲 | 🔲 | 🔲 Todo |
| ChatRoomScreen | Send button | 🔲 | 🔲 | N/A | 🔲 | 🔲 | 🔲 Todo |
| ChatRoomScreen | Attach button | 🔲 | 🔲 | N/A | 🔲 | 🔲 | 🔲 Todo |
| ChatRoomScreen | Message list live region | 🔲 | 🔲 | N/A | N/A | N/A | 🔲 Todo |
| ChatRoomScreen | Read-only banner | 🔲 | 🔲 | N/A | N/A | N/A | 🔲 Todo |

### 2.2 Web — consumer-web

| Page | Component | Label/aria-* | Semantic HTML | Focus | Status |
|---|---|---|---|---|---|
| /login | Email input | ✅ label+htmlFor+aria-required | ✅ | ✅ | ✅ Pass |
| /login | Password input | ✅ label+htmlFor+aria-required | ✅ | ✅ | ✅ Pass |
| /login | Forgot password link | ✅ | ✅ `<a>` | ✅ focus-visible | ✅ Pass |
| /login | Sign in button | ✅ aria-describedby | ✅ `<button>` | ✅ | ✅ Pass |
| /login | Status live region | ✅ role=status aria-live=polite | ✅ | N/A | ✅ Pass |
| / | h1 heading | ✅ aria-labelledby on section | ✅ h1 | ✅ | ✅ Pass |
| / | Feature cards | ✅ section with aria-labelledby | ✅ `<ul><li>` | ✅ | ✅ Pass |
| / | CTA links | ✅ descriptive text | ✅ `<a>` | ✅ focus-visible | ✅ Pass |
| /discover | Page h1 | 🔲 | 🔲 | 🔲 | 🔲 Todo |
| /settings | Language picker | 🔲 | 🔲 | 🔲 | 🔲 Todo |

### 2.3 Web — admin-web

| Page | Component | Label/aria-* | Semantic HTML | Focus | Status |
|---|---|---|---|---|---|
| /login | h1 heading | ✅ | ✅ h1 | ✅ | ✅ Pass |
| /login | Email input | ✅ label+htmlFor+aria-required | ✅ | ✅ | ✅ Pass |
| /login | Password input | ✅ label+htmlFor+aria-required | ✅ | ✅ | ✅ Pass |
| /login | Sign in button | ✅ | ✅ `<button>` | ✅ | ✅ Pass |
| /dashboard | Page h1 | ✅ | ✅ h1 | ✅ | ✅ Pass |
| /dashboard | Quick-link cards | ✅ aria-label with count+desc | ✅ `<nav><ul><li><a>` | ✅ focus-visible | ✅ Pass |
| /moderation/queue | Case cards | 🔲 | 🔲 | 🔲 | 🔲 Todo |
| /moderation/queue | Action buttons | 🔲 | 🔲 | 🔲 | 🔲 Todo |
| /users | User table | 🔲 | 🔲 | 🔲 | 🔲 Todo |

### 2.4 Web — marketing-web

| Page | Component | Label/aria-* | Semantic HTML | Focus | Status |
|---|---|---|---|---|---|
| / | Hero h1 | ✅ aria-labelledby on section | ✅ h1 | ✅ | ✅ Pass |
| / | Value props section | ✅ aria-labelledby | ✅ h2, `<ul><li>` | ✅ | ✅ Pass |
| / | How it works | ✅ aria-labelledby | ✅ h2, `<ol><li>` | ✅ | ✅ Pass |
| / | FAQ teaser | ✅ aria-labelledby | ✅ `<dl><dt><dd>` | ✅ | ✅ Pass |
| / | WaitlistForm email | ✅ `<label htmlFor>` | ✅ | ✅ | ✅ Pass |
| / | WaitlistForm submit | ✅ | ✅ `<button type=submit>` | ✅ | ✅ Pass |
| / | WaitlistForm consent | ✅ label+htmlFor | ✅ `<input type=checkbox>` | ✅ | ✅ Pass |
| / | WaitlistForm status | ✅ role=status aria-live=polite | ✅ | N/A | ✅ Pass |
| / | Decorative icons | ✅ aria-hidden=true | ✅ `<span aria-hidden>` | N/A | ✅ Pass |
| / | Step numbers | ✅ aria-label="Step 01" | ✅ `<span>` | N/A | ✅ Pass |
| / | App Store badge | ✅ aria-label with brand | ✅ `<a>` | ✅ | ✅ Pass |
| / | Footer nav | ✅ aria-label | ✅ `<nav>` | ✅ | ✅ Pass |
| /pricing | Heading | 🔲 | 🔲 | 🔲 | 🔲 Todo |

---

## 3. Known Exceptions (Documented Third-Party)

| Surface | Exception | Reason | Mitigation |
|---|---|---|---|
| All web | **Stripe Checkout iframe** | Stripe-owned UI | Rely on Stripe's published WCAG 2.1 AA commitment. Container labeled. |
| consumer-web | **tldraw whiteboard canvas** | Third-party WebView; axe cannot penetrate | Wrap with `aria-label`; provide text-based project-plan view as screen-reader alternative. Filed upstream FR. |
| mobile | **Persona SDK liveness flow** | Native SDK UI not authored by Colab | `accessibilityViewIsModal` wraps Persona modal; confirmed Persona passes VoiceOver/TalkBack smoke. |

---

## 4. Color Contrast Status

All design token pairs must pass before launch. Run `npx vitest run packages/ui/src/__tests__/color-contrast.test.ts`.

| Token Pair | Ratio | Required | Status |
|---|---|---|---|
| `text.primary` on `surface.default` | TBD | ≥ 4.5:1 | 🔲 Pending audit |
| `text.secondary` on `surface.default` | TBD | ≥ 4.5:1 | 🔲 Pending audit |
| `text.on_primary` on `brand.primary` | TBD | ≥ 4.5:1 | 🔲 Pending audit |
| `border.default` on `surface.default` | TBD | ≥ 3:1 | 🔲 Pending audit |

---

## 5. Reduced Motion

- **Web**: All CSS animations gated on `@media (prefers-reduced-motion: no-preference)`. `stylelint-a11y/media-prefers-reduced-motion` enforces this. Status: ✅ infra in place, 🔲 full audit pending.
- **RN**: `useReducedMotion()` from `react-native-reanimated` gates animations. Discovery swipe degrades to fade. Status: 🔲 Todo.

---

## 6. Dynamic Type / Scalable Text

- **Web**: All font sizes use `rem`. Tested at 200% browser zoom. Status: 🔲 Pending.
- **RN**: `allowFontScaling={true}` (default). Tested at 200% Dynamic Type. Tab bar label uses `maxFontSizeMultiplier={1.5}` with full `accessibilityLabel`. Status: 🔲 Pending.

---

## 7. Open Items Tracked for Post-P17

- [ ] Complete audit of remaining 🔲 screens (see above)
- [ ] Color contrast token test suite (`packages/ui/src/__tests__/color-contrast.test.ts`)
- [ ] Full 10-flow Detox a11y smoke tests (only 3 of 10 currently implemented)
- [ ] Storybook `@storybook/addon-a11y` integration for `@colab/ui` components
- [ ] Dynamic Type 200% testing on iOS (E-03, E-11)
- [ ] Android Detox a11y API verification (API 33)
