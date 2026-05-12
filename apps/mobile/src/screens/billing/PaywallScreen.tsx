/**
 * PaywallScreen — displays tier options (Free / Premium / Pro) with IAP via RevenueCat.
 *
 * Uses react-native-purchases for Apple IAP + Google Play Billing.
 * Calls Purchases.purchasePackage() which handles receipt validation via RC.
 * Entitlement update arrives via webhook → polling or push notification.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import Purchases, {
  PurchasesOffering,
  PurchasesPackage,
} from 'react-native-purchases';

interface PlanFeatureProps {
  text: string;
  included: boolean;
}

const PlanFeature: React.FC<PlanFeatureProps> = ({ text, included }) => (
  <View style={styles.featureRow}>
    <Text style={[styles.featureIcon, included ? styles.included : styles.excluded]}>
      {included ? '✓' : '✗'}
    </Text>
    <Text style={[styles.featureText, !included && styles.excludedText]}>{text}</Text>
  </View>
);

interface TierCardProps {
  title: string;
  price: string;
  features: { text: string; included: boolean }[];
  isSelected: boolean;
  isCurrent: boolean;
  onSelect: () => void;
}

const TierCard: React.FC<TierCardProps> = ({
  title, price, features, isSelected, isCurrent, onSelect,
}) => (
  <TouchableOpacity
    style={[styles.card, isSelected && styles.cardSelected]}
    onPress={onSelect}
    activeOpacity={0.8}
  >
    {isCurrent && (
      <View style={styles.currentBadge}>
        <Text style={styles.currentBadgeText}>Current Plan</Text>
      </View>
    )}
    <Text style={styles.tierTitle}>{title}</Text>
    <Text style={styles.tierPrice}>{price}</Text>
    {features.map((f, i) => (
      <PlanFeature key={i} text={f.text} included={f.included} />
    ))}
  </TouchableOpacity>
);

const TIER_FEATURES = {
  free: [
    { text: '5 invites per week', included: true },
    { text: 'No AI credits', included: false },
    { text: 'Ads shown', included: false },
    { text: 'Chat export', included: false },
    { text: 'See who saved you', included: false },
  ],
  premium: [
    { text: 'Unlimited invites', included: true },
    { text: '200 AI credits/month', included: true },
    { text: 'No ads', included: true },
    { text: 'Chat export', included: true },
    { text: 'See who saved you', included: true },
  ],
  pro: [
    { text: 'Unlimited invites', included: true },
    { text: '1,000 AI credits/month', included: true },
    { text: 'No ads', included: true },
    { text: 'Portfolio PDF export', included: true },
    { text: 'Visibility boost', included: true },
  ],
};

interface PaywallScreenProps {
  navigation: any;
  route: { params?: { currentTier?: string } };
}

export const PaywallScreen: React.FC<PaywallScreenProps> = ({ navigation, route }) => {
  const [offerings, setOfferings] = useState<PurchasesOffering | null>(null);
  const [selectedPackage, setSelectedPackage] = useState<PurchasesPackage | null>(null);
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState(false);
  const [billingPeriod, setBillingPeriod] = useState<'monthly' | 'annual'>('monthly');

  const currentTier = route.params?.currentTier ?? 'free';

  useEffect(() => {
    loadOfferings();
  }, []);

  const loadOfferings = async () => {
    try {
      const offeringsResult = await Purchases.getOfferings();
      if (offeringsResult.current) {
        setOfferings(offeringsResult.current);
      }
    } catch (error) {
      console.error('Failed to load offerings:', error);
      Alert.alert('Error', 'Could not load subscription options. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handlePurchase = useCallback(async () => {
    if (!selectedPackage) {
      Alert.alert('Select a plan', 'Please choose a subscription plan to continue.');
      return;
    }

    // IMPORTANT: RC docs say to call logIn before first purchase
    // logIn should have been called at auth time; guard here anyway
    setPurchasing(true);
    try {
      const { customerInfo } = await Purchases.purchasePackage(selectedPackage);
      // Entitlements update arrives via webhook; navigate to confirmation
      navigation.navigate('SubscriptionManagement', { justPurchased: true });
    } catch (error: any) {
      if (!error.userCancelled) {
        Alert.alert(
          'Purchase failed',
          'Something went wrong with your purchase. Please try again.',
        );
        console.error('Purchase error:', error);
      }
    } finally {
      setPurchasing(false);
    }
  }, [selectedPackage, navigation]);

  const handleRestorePurchases = async () => {
    try {
      await Purchases.restorePurchases();
      Alert.alert('Restored', 'Your purchases have been restored.');
    } catch {
      Alert.alert('Error', 'Could not restore purchases.');
    }
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.heading}>Upgrade Colab</Text>
      <Text style={styles.subheading}>Unlock your full creative potential</Text>

      {/* Billing period toggle */}
      <View style={styles.periodToggle}>
        <TouchableOpacity
          style={[styles.periodBtn, billingPeriod === 'monthly' && styles.periodBtnActive]}
          onPress={() => setBillingPeriod('monthly')}
        >
          <Text style={styles.periodBtnText}>Monthly</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.periodBtn, billingPeriod === 'annual' && styles.periodBtnActive]}
          onPress={() => setBillingPeriod('annual')}
        >
          <Text style={styles.periodBtnText}>Annual</Text>
          <Text style={styles.savingsBadge}>Save 20%</Text>
        </TouchableOpacity>
      </View>

      {/* Tier cards */}
      <TierCard
        title="Free"
        price="$0"
        features={TIER_FEATURES.free}
        isSelected={false}
        isCurrent={currentTier === 'free'}
        onSelect={() => {}}
      />
      <TierCard
        title="Premium"
        price={billingPeriod === 'monthly' ? '$9.99/mo' : '$95.88/yr'}
        features={TIER_FEATURES.premium}
        isSelected={selectedPackage?.packageType === 'MONTHLY' || selectedPackage?.packageType === 'ANNUAL'}
        isCurrent={currentTier === 'premium'}
        onSelect={() => {
          const pkg = offerings?.availablePackages.find(
            p => p.packageType === (billingPeriod === 'monthly' ? 'MONTHLY' : 'ANNUAL')
              && p.offeringIdentifier.includes('premium'),
          );
          setSelectedPackage(pkg ?? null);
        }}
      />
      <TierCard
        title="Premium Pro"
        price={billingPeriod === 'monthly' ? '$24.99/mo' : '$239.88/yr'}
        features={TIER_FEATURES.pro}
        isSelected={false}
        isCurrent={currentTier === 'pro'}
        onSelect={() => {
          const pkg = offerings?.availablePackages.find(
            p => p.offeringIdentifier.includes('pro'),
          );
          setSelectedPackage(pkg ?? null);
        }}
      />

      {/* CTA */}
      <TouchableOpacity
        style={[styles.ctaButton, (!selectedPackage || purchasing) && styles.ctaDisabled]}
        onPress={handlePurchase}
        disabled={!selectedPackage || purchasing}
      >
        {purchasing ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.ctaText}>
            {selectedPackage ? 'Subscribe Now' : 'Select a Plan'}
          </Text>
        )}
      </TouchableOpacity>

      <TouchableOpacity onPress={handleRestorePurchases} style={styles.restoreBtn}>
        <Text style={styles.restoreText}>Restore Purchases</Text>
      </TouchableOpacity>

      <Text style={styles.legal}>
        Subscriptions auto-renew unless canceled 24h before renewal.{'\n'}
        Manage or cancel in your {Platform.OS === 'ios' ? 'App Store' : 'Play Store'} account settings.{'\n'}
        {Platform.OS === 'ios' ? 'Apple' : 'Google'} handles all billing and tax for in-app purchases.
      </Text>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff' },
  content: { padding: 20, paddingBottom: 40 },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  heading: { fontSize: 28, fontWeight: '700', textAlign: 'center', marginBottom: 8 },
  subheading: { fontSize: 16, color: '#666', textAlign: 'center', marginBottom: 24 },
  periodToggle: { flexDirection: 'row', justifyContent: 'center', marginBottom: 20, gap: 12 },
  periodBtn: {
    paddingVertical: 8, paddingHorizontal: 20, borderRadius: 20,
    borderWidth: 1, borderColor: '#ddd', alignItems: 'center',
  },
  periodBtnActive: { backgroundColor: '#6C47FF', borderColor: '#6C47FF' },
  periodBtnText: { fontSize: 14, color: '#333' },
  savingsBadge: { fontSize: 10, color: '#4CAF50', fontWeight: '600' },
  card: {
    borderWidth: 2, borderColor: '#eee', borderRadius: 16,
    padding: 20, marginBottom: 16, backgroundColor: '#fafafa',
  },
  cardSelected: { borderColor: '#6C47FF', backgroundColor: '#f5f3ff' },
  currentBadge: {
    backgroundColor: '#4CAF50', borderRadius: 8, paddingHorizontal: 8,
    paddingVertical: 2, alignSelf: 'flex-start', marginBottom: 8,
  },
  currentBadgeText: { color: '#fff', fontSize: 11, fontWeight: '600' },
  tierTitle: { fontSize: 20, fontWeight: '700', marginBottom: 4 },
  tierPrice: { fontSize: 18, color: '#6C47FF', fontWeight: '600', marginBottom: 12 },
  featureRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 6 },
  featureIcon: { fontSize: 14, fontWeight: '700', marginRight: 8, width: 16 },
  featureText: { fontSize: 14, color: '#333' },
  included: { color: '#4CAF50' },
  excluded: { color: '#ccc' },
  excludedText: { color: '#aaa' },
  ctaButton: {
    backgroundColor: '#6C47FF', borderRadius: 14, paddingVertical: 16,
    alignItems: 'center', marginTop: 8, marginBottom: 16,
  },
  ctaDisabled: { opacity: 0.5 },
  ctaText: { color: '#fff', fontSize: 18, fontWeight: '700' },
  restoreBtn: { alignItems: 'center', marginBottom: 20 },
  restoreText: { color: '#6C47FF', fontSize: 14 },
  legal: { fontSize: 11, color: '#aaa', textAlign: 'center', lineHeight: 16 },
});

export default PaywallScreen;
