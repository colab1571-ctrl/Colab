/**
 * SendVibeCheckModal — Send a Vibe Check from a profile detail view.
 *
 * Features:
 *   - 250-character synopsis counter with live feedback
 *   - Submits POST /invites (with X-Idempotency-Key)
 *   - 402 → upsell modal (upgrade to Premium)
 *   - 422 → moderation rejection message
 *   - 403 → blocked state (user should not normally reach this)
 *
 * FR-B-8: 250-char synopsis, no attachments.
 */

import React, { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useAuthStore } from "../../state/auth.store";
import { sendVibeCheck } from "../../api/invites";

const SYNOPSIS_MAX = 250;

type Props = {
  visible: boolean;
  onClose: () => void;
  toProfileId: string;
  toDisplayName: string | null;
  navigation?: NativeStackNavigationProp<any>;
};

type SubmitState = "idle" | "loading" | "success" | "error";

export function SendVibeCheckModal({
  visible,
  onClose,
  toProfileId,
  toDisplayName,
  navigation,
}: Props): React.ReactElement {
  const [synopsis, setSynopsis] = useState("");
  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showUpsell, setShowUpsell] = useState(false);
  const idempotencyKey = useRef<string>(crypto.randomUUID());

  const remaining = SYNOPSIS_MAX - synopsis.length;
  const isOverLimit = remaining < 0;
  const canSubmit = synopsis.trim().length > 0 && !isOverLimit && submitState !== "loading";

  const handleClose = useCallback(() => {
    setSynopsis("");
    setSubmitState("idle");
    setErrorMessage(null);
    setShowUpsell(false);
    idempotencyKey.current = crypto.randomUUID();
    onClose();
  }, [onClose]);

  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return;
    setSubmitState("loading");
    setErrorMessage(null);

    try {
      await sendVibeCheck({
        toProfileId,
        synopsis: synopsis.trim(),
        idempotencyKey: idempotencyKey.current,
      });
      setSubmitState("success");
    } catch (err: unknown) {
      const apiErr = err as { status?: number; body?: any };
      const status = apiErr?.status;
      const body = apiErr?.body;

      if (status === 402) {
        // Free quota exceeded — show upsell
        setShowUpsell(true);
        setSubmitState("idle");
      } else if (status === 422) {
        setErrorMessage(
          "Your message was flagged by our content policy. Please revise and try again."
        );
        setSubmitState("error");
      } else if (status === 403) {
        setErrorMessage("You cannot send a Vibe Check to this user.");
        setSubmitState("error");
      } else {
        setErrorMessage("Something went wrong. Please try again.");
        setSubmitState("error");
      }
    }
  }, [canSubmit, synopsis, toProfileId]);

  if (showUpsell) {
    return (
      <Modal visible={visible} animationType="slide" transparent presentationStyle="pageSheet">
        <View className="flex-1 bg-white px-6 pt-12 pb-8 items-center justify-center">
          <Text className="text-2xl font-bold text-neutral-900 mb-4 text-center">
            Upgrade to Premium
          </Text>
          <Text className="text-base text-neutral-500 mb-8 text-center">
            You've sent 5 Vibe Checks this week. Premium members get unlimited Vibe Checks.
          </Text>
          <TouchableOpacity
            className="bg-brand-primary py-4 rounded-2xl w-full items-center mb-3"
            onPress={() => {
              handleClose();
              navigation?.navigate("BillingUpgrade");
            }}
            testID="upsell-upgrade-btn"
          >
            <Text className="text-white font-bold text-base">Upgrade to Premium</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={handleClose} testID="upsell-dismiss-btn">
            <Text className="text-neutral-400 text-sm">Maybe later</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    );
  }

  if (submitState === "success") {
    return (
      <Modal visible={visible} animationType="slide" transparent presentationStyle="pageSheet">
        <View className="flex-1 bg-white px-6 pt-12 pb-8 items-center justify-center">
          <Text className="text-5xl mb-4">✨</Text>
          <Text className="text-2xl font-bold text-neutral-900 mb-2 text-center">
            Vibe Check Sent!
          </Text>
          <Text className="text-base text-neutral-500 mb-8 text-center">
            {toDisplayName ?? "They"} will receive your message. You'll be notified if it's a match!
          </Text>
          <TouchableOpacity
            className="bg-brand-primary py-4 rounded-2xl w-full items-center"
            onPress={handleClose}
            testID="success-done-btn"
          >
            <Text className="text-white font-bold text-base">Done</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    );
  }

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent
      presentationStyle="pageSheet"
      accessibilityViewIsModal
      onRequestClose={handleClose}
    >
      <KeyboardAvoidingView
        className="flex-1 bg-white"
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        accessibilityLabel={`Send Vibe Check to ${toDisplayName ?? "this creator"}`}
      >
        <View className="flex-1 px-6 pt-8 pb-8">
          {/* Header */}
          <View className="flex-row items-center justify-between mb-6">
            <Text
              className="text-xl font-bold text-neutral-900"
              accessibilityRole="header"
            >
              Send Vibe Check
            </Text>
            <TouchableOpacity
              onPress={handleClose}
              testID="modal-close-btn"
              accessibilityLabel="Cancel — close this dialog"
              accessibilityRole="button"
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              style={{ minWidth: 44, minHeight: 44, justifyContent: "center" }}
            >
              <Text className="text-neutral-500 text-base">Cancel</Text>
            </TouchableOpacity>
          </View>

          {toDisplayName && (
            <Text className="text-sm text-neutral-500 mb-4" accessibilityLabel={`To: ${toDisplayName}`}>
              To: <Text className="text-neutral-900 font-medium">{toDisplayName}</Text>
            </Text>
          )}

          {/* Synopsis input */}
          <View className="flex-1 mb-4">
            <Text
              className="text-sm font-medium text-neutral-700 mb-2"
              nativeID="synopsis-label"
            >
              Tell them why you want to collaborate
            </Text>
            <TextInput
              className="border border-neutral-200 rounded-2xl p-4 text-base text-neutral-900 flex-1"
              placeholder="What inspires you about their work? What would you create together?"
              multiline
              maxLength={SYNOPSIS_MAX + 20} // allow slight overage so counter shows red
              value={synopsis}
              onChangeText={setSynopsis}
              autoFocus
              testID="synopsis-input"
              textAlignVertical="top"
              accessibilityLabel="Your message to this creator"
              accessibilityHint={`Tell ${toDisplayName ?? "them"} why you'd like to collaborate. ${SYNOPSIS_MAX} character maximum.`}
              accessibilityRequired
            />
          </View>

          {/* Character counter */}
          <View className="flex-row items-center justify-between mb-4">
            <Text
              className={`text-sm font-medium ${
                isOverLimit ? "text-red-500" : remaining <= 30 ? "text-orange-500" : "text-neutral-400"
              }`}
              testID="char-counter"
              accessibilityLabel={
                isOverLimit
                  ? `Message is ${Math.abs(remaining)} characters over the ${SYNOPSIS_MAX} limit`
                  : `${remaining} characters remaining`
              }
              accessibilityLiveRegion="polite"
            >
              {isOverLimit ? `${Math.abs(remaining)} over limit` : `${remaining} remaining`}
            </Text>
            {isOverLimit && (
              <Text className="text-xs text-red-400" importantForAccessibility="no-hide-descendants">
                Max {SYNOPSIS_MAX} characters
              </Text>
            )}
          </View>

          {/* Error */}
          {errorMessage && (
            <View accessibilityLiveRegion="assertive" accessibilityRole="alert">
              <Text className="text-red-500 text-sm mb-4" testID="error-message">
                {errorMessage}
              </Text>
            </View>
          )}

          {/* Submit */}
          <TouchableOpacity
            className={`py-4 rounded-2xl items-center ${
              canSubmit ? "bg-brand-primary" : "bg-neutral-200"
            }`}
            style={{ minHeight: 44 }}
            onPress={handleSubmit}
            disabled={!canSubmit}
            testID="submit-btn"
            accessibilityLabel={
              submitState === "loading"
                ? "Sending Vibe Check, please wait"
                : `Send Vibe Check to ${toDisplayName ?? "this creator"}`
            }
            accessibilityRole="button"
            accessibilityState={{ busy: submitState === "loading", disabled: !canSubmit }}
          >
            {submitState === "loading" ? (
              <ActivityIndicator color={canSubmit ? "#fff" : "#999"} accessibilityLabel="Sending" />
            ) : (
              <Text
                className={`font-bold text-base ${canSubmit ? "text-white" : "text-neutral-400"}`}
              >
                Send Vibe Check
              </Text>
            )}
          </TouchableOpacity>

          <Text className="text-center text-xs text-neutral-400 mt-3">
            No attachments — text only. Be genuine!
          </Text>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
