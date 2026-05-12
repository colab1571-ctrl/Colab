/**
 * SubscriptionManagementScreen — shows active subscriptions, billing info, cancel options.
 *
 * Fetches from GET /billing/subscriptions + GET /billing/entitlements.
 * Cancel: POST /billing/cancel/web (Stripe) or deep-link to store settings (mobile).
 * Shows cross-platform duplicate warning if user has multiple active subs.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Linking,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';

interface Subscription {
  id: string;
  source: string;
  gateway: string;
  tier: string;
  status: string;
  billing_period: string;
  current_period_end: string;
  cancel_at_period_end: boolean;
}

interface Entitlements {
  tier: string;
  subscription_status: string | null;
  current_period_end: string | null;
  axes: Record<string, any>;
}

const TIER_LABELS: Record<string, string> = {
  free: 'Free',
  premium: 'Premium',
  pro: 'Premium Pro',
};

const GATEWAY_LABELS: Record<string, string> = {
  stripe: 'Web',
  apple: 'App Store',
  google: 'Play Store',
  paddle_in: 'Paddle (IN)',
};

const STATUS_COLORS: Record<string, string> = {
  active: '#4CAF50',
  trialing: '#2196F3',
  past_due: '#FF9800',
  grace: '#FF9800',
  canceled: '#f44336',
  expired: '#9E9E9E',
  paused: '#9C27B0',
};

interface SubscriptionManagementScreenProps {
  navigation: any;
}

export const SubscriptionManagementScreen: React.FC<SubscriptionManagementScreenProps> = ({
  navigation,
}) => {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [entitlements, setEntitlements] = useState<Entitlements | null>(null);
  const [loading, setLoading] = useState(true);
  const [canceling, setCanceling] = useState<string | null>(null);

  const getToken = async (): Promise<string> => '';

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const token = await getToken();
      const headers = { Authorization: `Bearer ${token}` };

      const [subsResp, entResp] = await Promise.all([
        fetch('/billing/subscriptions', { headers }),
        fetch('/billing/entitlements', { headers }),
      ]);

      if (subsResp.ok) setSubscriptions(await subsResp.json());
      if (entResp.ok) setEntitlements(await entResp.json());
    } catch (error) {
      console.error('Failed to load subscription data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCancelStripe = useCallback(async (sub: Subscription) => {
    Alert.alert(
      'Cancel Subscription',
      'Your subscription will remain active until the end of the current billing period.',
      [
        { text: 'Keep Subscription', style: 'cancel' },
        {
          text: 'Cancel at Period End',
          style: 'destructive',
          onPress: async () => {
            setCanceling(sub.id);
            try {
              const resp = await fetch('/billing/cancel/web', {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  Authorization: `Bearer ${await getToken()}`,
                },
                body: JSON.stringify({ subscription_id: sub.id, immediate: false }),
              });
              if (resp.ok) {
                Alert.alert('Canceled', 'Your subscription will end at period close.');
                await loadData();
              }
            } finally {
              setCanceling(null);
            }
          },
        },
      ],
    );
  }, []);

  const handleCancelMobile = (sub: Subscription) => {
    const url =
      sub.gateway === 'apple'
        ? 'https://apps.apple.com/account/subscriptions'
        : 'https://play.google.com/store/account/subscriptions';
    Alert.alert(
      'Cancel in Store',
      `To cancel your ${GATEWAY_LABELS[sub.gateway]} subscription, please visit your ${
        sub.gateway === 'apple' ? 'App Store' : 'Play Store'
      } subscription settings.`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Open Settings', onPress: () => Linking.openURL(url) },
      ],
    );
  };

  const activeSubs = subscriptions.filter(
    s => ['active', 'trialing', 'past_due', 'grace'].includes(s.status),
  );
  const hasMultiplePlatforms =
    activeSubs.length > 1 &&
    new Set(activeSubs.map(s => s.gateway)).size > 1;

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.heading}>Subscription</Text>

      {/* Current tier summary */}
      {entitlements && (
        <View style={styles.tierSummary}>
          <Text style={styles.tierLabel}>
            {TIER_LABELS[entitlements.tier] ?? entitlements.tier}
          </Text>
          {entitlements.current_period_end && (
            <Text style={styles.periodEnd}>
              Renews {new Date(entitlements.current_period_end).toLocaleDateString()}
            </Text>
          )}
        </View>
      )}

      {/* Multi-platform warning */}
      {hasMultiplePlatforms && (
        <View style={styles.warningCard}>
          <Text style={styles.warningTitle}>⚠️ Multiple Active Subscriptions</Text>
          <Text style={styles.warningText}>
            You have active subscriptions on multiple platforms. You are being charged on both.
            Consider canceling the lower-tier or earlier-expiring one.
          </Text>
        </View>
      )}

      {/* Subscription cards */}
      {subscriptions.map(sub => (
        <View key={sub.id} style={styles.subCard}>
          <View style={styles.subHeader}>
            <Text style={styles.subGateway}>{GATEWAY_LABELS[sub.gateway] ?? sub.gateway}</Text>
            <View style={[styles.statusBadge, { backgroundColor: STATUS_COLORS[sub.status] ?? '#ccc' }]}>
              <Text style={styles.statusText}>{sub.status}</Text>
            </View>
          </View>

          <Text style={styles.subTier}>{TIER_LABELS[sub.tier] ?? sub.tier}</Text>
          <Text style={styles.subDetail}>
            {sub.billing_period === 'month' ? 'Monthly' : 'Annual'} •{' '}
            {sub.cancel_at_period_end ? 'Cancels' : 'Renews'}{' '}
            {new Date(sub.current_period_end).toLocaleDateString()}
          </Text>

          {/* Action buttons */}
          <View style={styles.actionRow}>
            {sub.status !== 'canceled' && sub.status !== 'expired' && (
              <TouchableOpacity
                style={styles.cancelBtn}
                disabled={canceling === sub.id}
                onPress={() =>
                  sub.gateway === 'stripe' ? handleCancelStripe(sub) : handleCancelMobile(sub)
                }
              >
                {canceling === sub.id ? (
                  <ActivityIndicator size="small" color="#f44336" />
                ) : (
                  <Text style={styles.cancelBtnText}>Cancel</Text>
                )}
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={styles.refundBtn}
              onPress={() => navigation.navigate('RefundRequest', { subscriptionId: sub.id })}
            >
              <Text style={styles.refundBtnText}>Refund Request</Text>
            </TouchableOpacity>
          </View>
        </View>
      ))}

      {subscriptions.length === 0 && (
        <View style={styles.emptyState}>
          <Text style={styles.emptyText}>No active subscriptions.</Text>
          <TouchableOpacity
            style={styles.upgradeBtn}
            onPress={() => navigation.navigate('Paywall')}
          >
            <Text style={styles.upgradeBtnText}>View Plans</Text>
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff' },
  content: { padding: 20, paddingBottom: 40 },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  heading: { fontSize: 26, fontWeight: '700', marginBottom: 20 },
  tierSummary: {
    backgroundColor: '#f5f3ff', borderRadius: 16, padding: 20,
    alignItems: 'center', marginBottom: 16,
  },
  tierLabel: { fontSize: 24, fontWeight: '700', color: '#6C47FF' },
  periodEnd: { fontSize: 13, color: '#888', marginTop: 4 },
  warningCard: {
    backgroundColor: '#FFF8E1', borderRadius: 12, padding: 16,
    marginBottom: 16, borderWidth: 1, borderColor: '#FFE082',
  },
  warningTitle: { fontSize: 14, fontWeight: '700', marginBottom: 6 },
  warningText: { fontSize: 13, color: '#5D4037', lineHeight: 18 },
  subCard: {
    borderWidth: 1.5, borderColor: '#eee', borderRadius: 16,
    padding: 16, marginBottom: 16, backgroundColor: '#fafafa',
  },
  subHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  subGateway: { fontSize: 13, color: '#888', fontWeight: '600' },
  statusBadge: { borderRadius: 8, paddingHorizontal: 8, paddingVertical: 2 },
  statusText: { color: '#fff', fontSize: 11, fontWeight: '600', textTransform: 'uppercase' },
  subTier: { fontSize: 20, fontWeight: '700', marginBottom: 4 },
  subDetail: { fontSize: 13, color: '#666', marginBottom: 12 },
  actionRow: { flexDirection: 'row', gap: 8 },
  cancelBtn: {
    borderWidth: 1.5, borderColor: '#f44336', borderRadius: 10,
    paddingVertical: 8, paddingHorizontal: 16,
  },
  cancelBtnText: { color: '#f44336', fontWeight: '600', fontSize: 14 },
  refundBtn: {
    borderWidth: 1.5, borderColor: '#6C47FF', borderRadius: 10,
    paddingVertical: 8, paddingHorizontal: 16,
  },
  refundBtnText: { color: '#6C47FF', fontWeight: '600', fontSize: 14 },
  emptyState: { alignItems: 'center', paddingTop: 40 },
  emptyText: { fontSize: 16, color: '#888', marginBottom: 20 },
  upgradeBtn: {
    backgroundColor: '#6C47FF', borderRadius: 14,
    paddingVertical: 14, paddingHorizontal: 32,
  },
  upgradeBtnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});

export default SubscriptionManagementScreen;
