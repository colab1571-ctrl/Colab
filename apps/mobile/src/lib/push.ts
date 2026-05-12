/**
 * Push notification token registration scaffold.
 * Per spec 014 (notifications-svc): don't prompt at signup — prompt at first needed moment.
 * Full implementation in spec 013.
 */

export interface PushTokenRegistration {
  token: string | null;
  permissionStatus: "granted" | "denied" | "undetermined";
}

/**
 * Register for push notifications and return the device token.
 * Does NOT prompt unless called explicitly (user opt-in trigger from spec 014).
 */
export async function registerForPushNotifications(): Promise<PushTokenRegistration> {
  // TODO spec 013: implement with expo-notifications + SNS registration
  return { token: null, permissionStatus: "undetermined" };
}
