# Mobile Demo — Expo Go

Run the Colab mobile app on your phone in ~2 minutes using Expo Go (no TestFlight, no build wait).

## Prerequisites

- Node 20+ and pnpm installed locally.
- [Expo Go](https://expo.dev/client) installed on your phone (iOS App Store or Google Play — free).
- Fly.io gateway deployed and accessible (see `fly.md`).

## 1. Set the API URL

In `apps/mobile/` create (or update) `.env.local`:

```bash
# apps/mobile/.env.local
EXPO_PUBLIC_API_URL=https://colab-gateway-prod.fly.dev
# While gateway isn't deployed yet, use local tunnel:
# EXPO_PUBLIC_API_URL=http://<your-lan-ip>:8000
```

> Expo automatically injects `EXPO_PUBLIC_*` variables at build time.
> Never put secrets in `EXPO_PUBLIC_*` — they are visible in the JS bundle.

## 2. Start the dev server

```bash
cd apps/mobile
pnpm install          # if not already done from monorepo root
pnpm expo start
```

Expo CLI prints a QR code in the terminal.

## 3. Scan QR and test

1. Open **Expo Go** on your phone.
2. Tap **Scan QR code** → scan the terminal QR.
3. The app loads over your local Wi-Fi (phone and laptop must be on the same network).

If on different networks (e.g., phone on LTE), press `t` in the Expo terminal to use a **tunnel** (ngrok-based):
```bash
pnpm expo start --tunnel
```

## 4. End-to-end signup flow on device

Once the app loads:
1. Tap **Sign Up** → enter email + password.
2. Complete phone OTP (Twilio/SNS SMS arrives on real device).
3. App exchanges credentials for a **JWT** (stored in SecureStore).
4. Redirected to **Profile setup** → fill in name, skills, location.
5. Profile is created in Supabase via profile-svc.
6. You're on the home feed — end-to-end flow complete.

## 5. Share the demo with others

```bash
pnpm expo publish          # publishes to Expo's CDN (requires Expo account)
# Outputs: exp://u.expo.dev/<your-project-slug>
```

Share the `exp://` link or QR — anyone with Expo Go can open it immediately.

> **Note:** `expo publish` requires logging into Expo (`npx expo login`).
> For a fully standalone `.ipa`/`.apk`, use EAS Build (requires paid Expo account for iOS).

## Troubleshooting

| Issue | Fix |
|---|---|
| "Network request failed" | Phone and laptop on same Wi-Fi, or use `--tunnel` |
| Metro bundler crash | `pnpm expo start --clear` to reset cache |
| API 401 errors | Check `EXPO_PUBLIC_API_URL` points to deployed gateway |
| Slow cold start | First request wakes Fly machine (~1-2 s); subsequent calls are fast |
