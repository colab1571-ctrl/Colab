/**
 * CreditPurchaseScreen — buy AI credit bundles via one-time in-app purchase.
 *
 * Uses RevenueCat NON_RENEWING products for mobile.
 * Balance shown from GET /billing/credits/balance.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import Purchases, { PurchasesPackage } from 'react-native-purchases';

interface CreditBundle {
  id: string;
  credits: number;
  price: string;
  popular?: boolean;
}

const CREDIT_BUNDLES: CreditBundle[] = [
  { id: 'credits_100', credits: 100, price: '$0.99' },
  { id: 'credits_500', credits: 500, price: '$3.99', popular: true },
  { id: 'credits_1000', credits: 1000, price: '$6.99' },
  { id: 'credits_5000', credits: 5000, price: '$29.99' },
];

interface CreditPurchaseScreenProps {
  navigation: any;
}

export const CreditPurchaseScreen: React.FC<CreditPurchaseScreenProps> = ({ navigation }) => {
  const [balance, setBalance] = useState<number | null>(null);
  const [packages, setPackages] = useState<PurchasesPackage[]>([]);
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      // Load credit balance from API
      const resp = await fetch('/billing/credits/balance', {
        headers: { Authorization: `Bearer ${await getToken()}` },
      });
      if (resp.ok) {
        const data = await resp.json();
        setBalance(data.balance);
      }

      // Load RC non-renewing packages
      const offeringsResult = await Purchases.getOfferings();
      const creditOffering = offeringsResult.all['credits'];
      if (creditOffering) {
        setPackages(creditOffering.availablePackages);
      }
    } catch (error) {
      console.error('Failed to load credit data:', error);
    } finally {
      setLoading(false);
    }
  };

  const getToken = async (): Promise<string> => {
    // Placeholder — use your auth store
    return '';
  };

  const handlePurchase = useCallback(async (bundle: CreditBundle) => {
    const pkg = packages.find(p => p.offeringIdentifier === bundle.id);
    if (!pkg) {
      Alert.alert('Unavailable', 'This bundle is not available right now.');
      return;
    }

    setPurchasing(bundle.id);
    try {
      const { customerInfo } = await Purchases.purchasePackage(pkg);
      Alert.alert('Purchase successful!', `${bundle.credits} credits added to your wallet.`);
      // Reload balance
      await loadData();
    } catch (error: any) {
      if (!error.userCancelled) {
        Alert.alert('Purchase failed', 'Could not complete purchase. Please try again.');
      }
    } finally {
      setPurchasing(null);
    }
  }, [packages]);

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.heading}>Buy AI Credits</Text>

      {balance !== null && (
        <View style={styles.balanceCard}>
          <Text style={styles.balanceLabel}>Current Balance</Text>
          <Text style={styles.balanceAmount}>{balance} credits</Text>
        </View>
      )}

      <Text style={styles.sectionTitle}>Choose a Bundle</Text>

      {CREDIT_BUNDLES.map(bundle => (
        <TouchableOpacity
          key={bundle.id}
          style={[styles.bundleCard, bundle.popular && styles.popularCard]}
          onPress={() => handlePurchase(bundle)}
          disabled={purchasing !== null}
          activeOpacity={0.8}
        >
          {bundle.popular && (
            <View style={styles.popularBadge}>
              <Text style={styles.popularText}>Most Popular</Text>
            </View>
          )}
          <View style={styles.bundleInfo}>
            <Text style={styles.creditsText}>{bundle.credits.toLocaleString()} Credits</Text>
            <Text style={styles.perCreditText}>
              {(parseFloat(bundle.price.slice(1)) / bundle.credits * 100).toFixed(2)}¢ each
            </Text>
          </View>
          <View style={styles.priceContainer}>
            {purchasing === bundle.id ? (
              <ActivityIndicator color="#6C47FF" />
            ) : (
              <Text style={styles.priceText}>{bundle.price}</Text>
            )}
          </View>
        </TouchableOpacity>
      ))}

      <Text style={styles.info}>
        Credits are used for AI-powered features like portfolio mockups.
        {'\n'}1 credit ≈ 1 mockup generation. Credits never expire.
        {'\n\n'}All purchases handled by {' '}
        {/* Platform-appropriate disclosure */}
        Apple or Google — tax calculated by the store.
      </Text>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff' },
  content: { padding: 20, paddingBottom: 40 },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  heading: { fontSize: 26, fontWeight: '700', marginBottom: 20 },
  balanceCard: {
    backgroundColor: '#f5f3ff', borderRadius: 16, padding: 20,
    alignItems: 'center', marginBottom: 24,
  },
  balanceLabel: { fontSize: 14, color: '#666', marginBottom: 4 },
  balanceAmount: { fontSize: 32, fontWeight: '700', color: '#6C47FF' },
  sectionTitle: { fontSize: 16, fontWeight: '600', color: '#333', marginBottom: 12 },
  bundleCard: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    borderWidth: 1.5, borderColor: '#eee', borderRadius: 14,
    padding: 16, marginBottom: 12, backgroundColor: '#fafafa',
  },
  popularCard: { borderColor: '#6C47FF', backgroundColor: '#f5f3ff' },
  popularBadge: {
    position: 'absolute', top: -10, left: 16,
    backgroundColor: '#6C47FF', borderRadius: 8,
    paddingHorizontal: 8, paddingVertical: 2,
  },
  popularText: { color: '#fff', fontSize: 10, fontWeight: '700' },
  bundleInfo: { flex: 1 },
  creditsText: { fontSize: 18, fontWeight: '600', color: '#1a1a1a' },
  perCreditText: { fontSize: 12, color: '#888', marginTop: 2 },
  priceContainer: { minWidth: 70, alignItems: 'flex-end' },
  priceText: { fontSize: 20, fontWeight: '700', color: '#6C47FF' },
  info: {
    fontSize: 12, color: '#aaa', lineHeight: 18,
    textAlign: 'center', marginTop: 24,
  },
});

export default CreditPurchaseScreen;
