import PostHog from "posthog-react-native";
import Constants from "expo-constants";

let posthog: PostHog | null = null;

export function initPostHog(): void {
  const apiKey = (Constants.expoConfig?.extra as Record<string, string> | undefined)?.posthogApiKey;
  if (!apiKey) return;

  posthog = new PostHog(apiKey, {
    host: "https://us.i.posthog.com",
    // No cross-app tracking; first-party analytics only
    captureApplicationLifecycleEvents: true,
    captureDeepLinks: true,
  });
}

export function useFeatureFlag(key: string): boolean | null {
  return posthog?.getFeatureFlag(key) as boolean | null ?? null;
}

export { posthog };
