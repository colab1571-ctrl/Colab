/**
 * RefundRequestScreen — submit a refund request for a subscription or credit purchase.
 *
 * Platform-specific routing:
 *   - Stripe (web): POST /billing/refund-request → auto-approve within 14d
 *   - Apple: deep-link to reportaproblem.apple.com
 *   - Google: deep-link to Play Help
 *
 * Shows refund eligibility before user submits.
 */

import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Linking,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';

interface RefundRequestScreenProps {
  navigation: any;
  route: {
    params: {
      subscriptionId?: string;
      transactionId?: string;
    };
  };
}

export const RefundRequestScreen: React.FC<RefundRequestScreenProps> = ({
  navigation,
  route,
}) => {
  const { subscriptionId, transactionId } = route.params;
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [eligibility, setEligibility] = useState<{
    within14d: boolean;
    gateway: string;
    daysRemaining: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  const getToken = async (): Promise<string> => '';

  useEffect(() => {
    checkEligibility();
  }, []);

  const checkEligibility = async () => {
    try {
      const token = await getToken();
      const resp = await fetch('/billing/subscriptions', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.ok) {
        const subs = await resp.json();
        const sub = subs.find((s: any) => s.id === subscriptionId);
        if (sub) {
          const startedAt = new Date(sub.started_at ?? sub.current_period_start);
          const daysSince = Math.floor((Date.now() - startedAt.getTime()) / (1000 * 60 * 60 * 24));
          setEligibility({
            within14d: daysSince < 14,
            gateway: sub.gateway,
            daysRemaining: Math.max(0, 14 - daysSince),
          });
        }
      }
    } catch {
      // Non-blocking; user can still submit
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    // Platform-specific routing for mobile gateways
    if (eligibility?.gateway === 'apple') {
      Alert.alert(
        'Apple Refund',
        "For App Store purchases, Apple handles refunds directly. We'll open the Apple refund page for you.",
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Open Apple Refunds',
            onPress: () => {
              // First record in our system, then deep-link
              recordMobileRefund('apple');
              Linking.openURL('https://reportaproblem.apple.com/');
            },
          },
        ],
      );
      return;
    }

    if (eligibility?.gateway === 'google') {
      Alert.alert(
        'Google Play Refund',
        'For Google Play purchases, refunds are handled by Google. We\'ll open Play Help.',
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Open Play Help',
            onPress: () => {
              recordMobileRefund('google');
              Linking.openURL('https://support.google.com/googleplay/answer/2479637');
            },
          },
        ],
      );
      return;
    }

    // Stripe web path — submit via API
    if (!reason.trim()) {
      Alert.alert('Reason required', 'Please provide a brief reason for the refund request.');
      return;
    }

    setSubmitting(true);
    try {
      const token = await getToken();
      const resp = await fetch('/billing/refund-request', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          subscription_id: subscriptionId,
          transaction_id: transactionId,
          reason,
        }),
      });

      const data = await resp.json();

      if (resp.ok) {
        if (data.status === 'auto_approved') {
          Alert.alert(
            'Refund Approved',
            `Your refund of $${((data.refund_amount_minor ?? 0) / 100).toFixed(2)} has been processed. You'll see it in 5–10 business days.`,
            [{ text: 'OK', onPress: () => navigation.goBack() }],
          );
        } else if (data.status === 'pending') {
          Alert.alert(
            'Request Submitted',
            'Your refund request is under review. Our team will respond within 3 business days.',
            [{ text: 'OK', onPress: () => navigation.goBack() }],
          );
        } else {
          Alert.alert(
            'Request Received',
            `Status: ${data.status}. We'll follow up by email.`,
            [{ text: 'OK', onPress: () => navigation.goBack() }],
          );
        }
      } else {
        Alert.alert('Error', data.detail ?? 'Could not submit refund request.');
      }
    } catch {
      Alert.alert('Error', 'Network error. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const recordMobileRefund = async (gateway: 'apple' | 'google') => {
    try {
      const token = await getToken();
      await fetch('/billing/refund-request', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          subscription_id: subscriptionId,
          reason: reason || `Routed to ${gateway}`,
        }),
      });
    } catch {
      // Non-blocking; we record for admin visibility
    }
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  const isMobileGateway = eligibility?.gateway === 'apple' || eligibility?.gateway === 'google';

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.heading}>Request a Refund</Text>

      {/* Eligibility banner */}
      {eligibility && (
        <View style={[
          styles.eligibilityCard,
          eligibility.within14d ? styles.eligibleCard : styles.ineligibleCard,
        ]}>
          {eligibility.within14d ? (
            <>
              <Text style={styles.eligibleTitle}>✓ Within 14-Day Window</Text>
              <Text style={styles.eligibilityText}>
                {isMobileGateway
                  ? 'Your purchase qualifies for a refund via the app store.'
                  : `You have ${eligibility.daysRemaining} days remaining for an auto-approved full refund.`}
              </Text>
            </>
          ) : (
            <>
              <Text style={styles.ineligibleTitle}>Outside Refund Window</Text>
              <Text style={styles.eligibilityText}>
                The 14-day no-questions refund period has passed.
                {'\n'}We'll review your request manually.
              </Text>
            </>
          )}
        </View>
      )}

      {/* Mobile gateway note */}
      {isMobileGateway && (
        <View style={styles.infoCard}>
          <Text style={styles.infoText}>
            {eligibility?.gateway === 'apple'
              ? '🍎 App Store purchases are refunded by Apple. Tapping Submit will open Apple\'s refund page.'
              : '▶️ Google Play purchases are refunded by Google. Tapping Submit will open Play Help.'}
          </Text>
        </View>
      )}

      {/* Reason input (required for Stripe) */}
      {!isMobileGateway && (
        <>
          <Text style={styles.label}>Reason for refund</Text>
          <TextInput
            style={styles.textInput}
            placeholder="Please describe why you're requesting a refund..."
            multiline
            numberOfLines={4}
            value={reason}
            onChangeText={setReason}
            maxLength={500}
          />
          <Text style={styles.charCount}>{reason.length}/500</Text>
        </>
      )}

      <TouchableOpacity
        style={[styles.submitBtn, submitting && styles.submitDisabled]}
        onPress={handleSubmit}
        disabled={submitting}
      >
        {submitting ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.submitText}>
            {isMobileGateway ? 'Open Store Refund' : 'Submit Request'}
          </Text>
        )}
      </TouchableOpacity>

      <Text style={styles.disclaimer}>
        Refund decisions for subscriptions purchased through the App Store or Google Play
        are made by Apple or Google respectively. Colab cannot override store decisions.
      </Text>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff' },
  content: { padding: 20, paddingBottom: 40 },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  heading: { fontSize: 26, fontWeight: '700', marginBottom: 20 },
  eligibilityCard: { borderRadius: 14, padding: 16, marginBottom: 16 },
  eligibleCard: { backgroundColor: '#E8F5E9' },
  ineligibleCard: { backgroundColor: '#FFF8E1' },
  eligibleTitle: { fontSize: 15, fontWeight: '700', color: '#2E7D32', marginBottom: 6 },
  ineligibleTitle: { fontSize: 15, fontWeight: '700', color: '#E65100', marginBottom: 6 },
  eligibilityText: { fontSize: 13, color: '#555', lineHeight: 18 },
  infoCard: {
    backgroundColor: '#E3F2FD', borderRadius: 12, padding: 14, marginBottom: 16,
  },
  infoText: { fontSize: 13, color: '#1565C0', lineHeight: 18 },
  label: { fontSize: 14, fontWeight: '600', color: '#333', marginBottom: 8 },
  textInput: {
    borderWidth: 1.5, borderColor: '#ddd', borderRadius: 12,
    padding: 14, fontSize: 14, color: '#333',
    textAlignVertical: 'top', minHeight: 100, marginBottom: 4,
  },
  charCount: { fontSize: 11, color: '#aaa', textAlign: 'right', marginBottom: 20 },
  submitBtn: {
    backgroundColor: '#6C47FF', borderRadius: 14,
    paddingVertical: 16, alignItems: 'center', marginBottom: 16,
  },
  submitDisabled: { opacity: 0.5 },
  submitText: { color: '#fff', fontSize: 17, fontWeight: '700' },
  disclaimer: {
    fontSize: 11, color: '#aaa', textAlign: 'center', lineHeight: 15,
  },
});

export default RefundRequestScreen;
