import { useCallback, useEffect, useState } from 'react';
import { Image, KeyboardAvoidingView, Linking, Platform, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BorderRadius, Shadow } from '@/constants/theme';
import { MASTER } from '@/config/master';
import { fetchRateSnapshot, formatInr, type RateSnapshot } from '@/services/rates';

const PRESET_AMOUNTS = [5000, 10000, 15000, 20000, 25000, 50000];
const DURATION_OPTIONS = [
  { months: 11, label: '11 Months', bonus: '1 month free' },
  { months: 22, label: '22 Months', bonus: '2 months free' },
  { months: 33, label: '33 Months', bonus: '3 months free' },
];

type Projection = {
  totalInvested: number;
  goldAccumulated: number; // grams
  bonusGold: number;
  totalGold: number;
  estimatedValue: number;
  avgRatePer10g: number;
};

function computeProjection(monthlyAmount: number, months: number, rate22kt: number): Projection {
  // SIP accumulates gold at each month's rate; we approximate with current rate
  // Gold purchased per month = monthlyAmount / (rate22kt / 10)
  const gramsPerMonth = monthlyAmount / (rate22kt / 10);
  const totalInvested = monthlyAmount * months;
  const goldAccumulated = gramsPerMonth * months;

  // Bonus: 1 month free per 11-month block
  const bonusMonths = Math.floor(months / 11);
  const bonusGold = gramsPerMonth * bonusMonths;
  const totalGold = goldAccumulated + bonusGold;

  const estimatedValue = totalGold * (rate22kt / 10);

  return {
    totalInvested,
    goldAccumulated,
    bonusGold,
    totalGold,
    estimatedValue,
    avgRatePer10g: rate22kt,
  };
}

export default function SipScreen() {
  const router = useRouter();
  const [snap, setSnap] = useState<RateSnapshot | null>(null);
  const [monthlyAmount, setMonthlyAmount] = useState(10000);
  const [selectedMonths, setSelectedMonths] = useState(22);
  const [inputText, setInputText] = useState('10000');

  useEffect(() => {
    fetchRateSnapshot().then(setSnap).catch(() => {});
  }, []);

  const rate22kt = snap?.published?.rate22kt ?? 0;
  const projection = rate22kt > 0 ? computeProjection(monthlyAmount, selectedMonths, rate22kt) : null;

  const handleAmountChange = useCallback((text: string) => {
    const cleaned = text.replace(/[^0-9]/g, '');
    setInputText(cleaned);
    const num = parseInt(cleaned, 10);
    if (!isNaN(num) && num >= 500) {
      setMonthlyAmount(num);
    }
  }, []);

  const handlePreset = useCallback((amount: number) => {
    setMonthlyAmount(amount);
    setInputText(String(amount));
  }, []);

  const handleEnquire = useCallback(() => {
    const text = encodeURIComponent(
      `Namaste ${MASTER.displayName},\n\nI am interested in the Gold Savings Plan.\n\nMonthly: ₹${formatInr(monthlyAmount)}\nDuration: ${selectedMonths} months\n\nPlease share the complete scheme details.`
    );
    Linking.openURL(`${MASTER.whatsapp}?text=${text}`);
  }, [monthlyAmount, selectedMonths]);

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
            <ThemedText style={styles.backText}>{'\u2190'}</ThemedText>
          </Pressable>
          <ThemedText style={styles.title}>Gold Savings Plan</ThemedText>
          <View style={{ width: 36 }} />
        </View>

        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={{ flex: 1 }}>
          <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
            {/* Hero Image */}
            <View style={[styles.heroWrap, Shadow.md]}>
              <Image source={require('@/assets/aradhana/sip_main.jpg')} style={styles.heroImg} />
            </View>

            {/* How It Works */}
            <View style={[styles.infoCard, Shadow.sm]}>
              <ThemedText style={styles.sectionTitle}>How It Works</ThemedText>
              <View style={styles.stepRow}>
                <View style={styles.stepBadge}><ThemedText style={styles.stepBadgeText}>1</ThemedText></View>
                <View style={{ flex: 1 }}>
                  <ThemedText style={styles.stepTitle}>Start Your Plan</ThemedText>
                  <ThemedText style={styles.stepDesc}>Choose your monthly instalment amount and duration.</ThemedText>
                </View>
              </View>
              <View style={styles.stepRow}>
                <View style={styles.stepBadge}><ThemedText style={styles.stepBadgeText}>2</ThemedText></View>
                <View style={{ flex: 1 }}>
                  <ThemedText style={styles.stepTitle}>Monthly Payments</ThemedText>
                  <ThemedText style={styles.stepDesc}>Pay monthly and accumulate gold at the current rate.</ThemedText>
                </View>
              </View>
              <View style={styles.stepRow}>
                <View style={styles.stepBadge}><ThemedText style={styles.stepBadgeText}>3</ThemedText></View>
                <View style={{ flex: 1 }}>
                  <ThemedText style={styles.stepTitle}>Redeem Jewellery</ThemedText>
                  <ThemedText style={styles.stepDesc}>Use your accumulated gold value to purchase jewellery.</ThemedText>
                </View>
              </View>
            </View>

            {/* Calculator */}
            <View style={[styles.calcCard, Shadow.sm]}>
              <ThemedText style={styles.sectionTitle}>Calculate Your Savings</ThemedText>

              {/* Live Rate */}
              {rate22kt > 0 && (
                <View style={styles.rateBar}>
                  <View style={styles.rateDot} />
                  <ThemedText style={styles.rateText}>Live Gold 22K: ₹{formatInr(rate22kt)}/10g</ThemedText>
                </View>
              )}

              {/* Monthly Amount Input */}
              <ThemedText style={styles.calcLabel}>Monthly Instalment</ThemedText>
              <View style={styles.amountInputWrap}>
                <ThemedText style={styles.rupeeSymbol}>{'₹'}</ThemedText>
                <TextInput
                  style={styles.amountInput}
                  value={inputText}
                  onChangeText={handleAmountChange}
                  keyboardType="numeric"
                  placeholder="10000"
                  placeholderTextColor="#9CA3AF"
                  maxLength={7}
                />
              </View>

              {/* Preset Amounts */}
              <View style={styles.presetRow}>
                {PRESET_AMOUNTS.map((amt) => (
                  <Pressable
                    key={amt}
                    onPress={() => handlePreset(amt)}
                    style={[styles.presetChip, monthlyAmount === amt && styles.presetChipActive]}>
                    <ThemedText style={[styles.presetText, monthlyAmount === amt && styles.presetTextActive]}>
                      {amt >= 1000 ? `${amt / 1000}K` : amt}
                    </ThemedText>
                  </Pressable>
                ))}
              </View>

              {/* Duration Selector */}
              <ThemedText style={[styles.calcLabel, { marginTop: 16 }]}>Duration</ThemedText>
              <View style={styles.durationRow}>
                {DURATION_OPTIONS.map((opt) => (
                  <Pressable
                    key={opt.months}
                    onPress={() => setSelectedMonths(opt.months)}
                    style={[styles.durationChip, selectedMonths === opt.months && styles.durationChipActive]}>
                    <ThemedText style={[styles.durationLabel, selectedMonths === opt.months && styles.durationLabelActive]}>
                      {opt.label}
                    </ThemedText>
                    <ThemedText style={[styles.durationBonus, selectedMonths === opt.months && styles.durationBonusActive]}>
                      {opt.bonus}
                    </ThemedText>
                  </Pressable>
                ))}
              </View>
            </View>

            {/* Projection Results */}
            {projection && (
              <View style={[styles.resultCard, Shadow.md]}>
                <ThemedText style={styles.resultTitle}>Your Projected Savings</ThemedText>

                <View style={styles.resultGrid}>
                  <View style={styles.resultItem}>
                    <ThemedText style={styles.resultValue}>{formatInr(projection.totalInvested)}</ThemedText>
                    <ThemedText style={styles.resultLabel}>Total Invested</ThemedText>
                  </View>
                  <View style={styles.resultDivider} />
                  <View style={styles.resultItem}>
                    <ThemedText style={[styles.resultValue, { color: '#C9A84C' }]}>
                      {projection.totalGold.toFixed(2)}g
                    </ThemedText>
                    <ThemedText style={styles.resultLabel}>Gold Accumulated</ThemedText>
                  </View>
                </View>

                {projection.bonusGold > 0 && (
                  <View style={styles.bonusRow}>
                    <ThemedText style={styles.bonusText}>
                      +{projection.bonusGold.toFixed(2)}g bonus gold ({Math.floor(selectedMonths / 11)} month{Math.floor(selectedMonths / 11) > 1 ? 's' : ''} free)
                    </ThemedText>
                  </View>
                )}

                <View style={styles.resultDividerFull} />

                <View style={styles.resultSummary}>
                  <View style={styles.resultSummaryRow}>
                    <ThemedText style={styles.resultSummaryLabel}>Estimated Gold Value</ThemedText>
                    <ThemedText style={styles.resultSummaryValue}>{formatInr(projection.estimatedValue)}</ThemedText>
                  </View>
                  <View style={styles.resultSummaryRow}>
                    <ThemedText style={styles.resultSummaryLabel}>Your Gain</ThemedText>
                    <ThemedText style={[styles.resultSummaryValue, { color: '#16A34A' }]}>
                      +{formatInr(projection.estimatedValue - projection.totalInvested)}
                    </ThemedText>
                  </View>
                </View>

                <View style={styles.resultFooter}>
                  <ThemedText style={styles.resultFooterText}>
                    Based on current gold rate. Actual accumulation may vary with rate fluctuations.
                  </ThemedText>
                </View>
              </View>
            )}

            {/* Details Image */}
            <View style={[styles.detailsWrap, Shadow.sm]}>
              <Image source={require('@/assets/aradhana/sip_details.jpg')} style={styles.detailsImg} />
            </View>

            {/* CTA */}
            <Pressable onPress={handleEnquire} style={[styles.cta, Shadow.sm]}>
              <ThemedText style={styles.ctaText}>{'\uD83D\uDCAC'} Start Plan on WhatsApp</ThemedText>
            </Pressable>

            <View style={styles.disclaimer}>
              <ThemedText style={styles.disclaimerText}>
                This is an indicative estimate. Actual scheme terms, instalment amounts, bonus structure and
                benefits will be confirmed by {MASTER.displayName} upon enrolment.
              </ThemedText>
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFBF5' },
  safeArea: { flex: 1 },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 10,
  },
  backBtn: {
    width: 36, height: 36, borderRadius: 18, backgroundColor: '#F8F6F3',
    alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#E5E1D8',
  },
  backText: { fontSize: 18, color: '#1A1A2E' },
  title: { fontSize: 18, fontWeight: '700', color: '#1A1A2E' },

  scroll: { paddingBottom: 100, gap: 12 },

  heroWrap: {
    marginHorizontal: 16, borderRadius: BorderRadius.xl, overflow: 'hidden',
    borderWidth: 1, borderColor: '#E5E1D8',
  },
  heroImg: { width: '100%', aspectRatio: 800 / 650 },

  sectionTitle: { fontSize: 17, fontWeight: '700', color: '#1A1A2E' },

  /* How It Works */
  infoCard: {
    marginHorizontal: 16, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg,
    borderWidth: 1, borderColor: '#E5E1D8', padding: 16, gap: 14,
  },
  stepRow: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  stepBadge: {
    width: 28, height: 28, borderRadius: 14, backgroundColor: '#23519D',
    alignItems: 'center', justifyContent: 'center',
  },
  stepBadgeText: { fontSize: 13, fontWeight: '700', color: '#FFFFFF' },
  stepTitle: { fontSize: 14, fontWeight: '600', color: '#1A1A2E', marginBottom: 2 },
  stepDesc: { fontSize: 12, color: '#6B7280', lineHeight: 16 },

  /* Calculator */
  calcCard: {
    marginHorizontal: 16, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg,
    borderWidth: 1, borderColor: '#E5E1D8', padding: 16, gap: 8,
  },
  rateBar: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#FDF8ED', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6,
    borderWidth: 1, borderColor: '#E8D9A8',
  },
  rateDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#16A34A' },
  rateText: { fontSize: 12, fontWeight: '600', color: '#A68523' },

  calcLabel: { fontSize: 12, fontWeight: '700', color: '#6B7280', letterSpacing: 0.5, textTransform: 'uppercase', marginTop: 4 },

  amountInputWrap: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#F8F6F3',
    borderRadius: BorderRadius.md, borderWidth: 1.5, borderColor: '#E5E1D8',
    paddingHorizontal: 14, height: 52, marginTop: 6,
  },
  rupeeSymbol: { fontSize: 20, fontWeight: '700', color: '#C9A84C', marginRight: 8 },
  amountInput: { flex: 1, fontSize: 22, fontWeight: '700', color: '#1A1A2E', padding: 0 },

  presetRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  presetChip: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20,
    backgroundColor: '#F8F6F3', borderWidth: 1, borderColor: '#E5E1D8',
  },
  presetChipActive: { backgroundColor: '#23519D', borderColor: '#23519D' },
  presetText: { fontSize: 13, fontWeight: '600', color: '#6B7280' },
  presetTextActive: { color: '#FFFFFF' },

  durationRow: { flexDirection: 'row', gap: 8, marginTop: 6 },
  durationChip: {
    flex: 1, alignItems: 'center', paddingVertical: 12, borderRadius: BorderRadius.md,
    backgroundColor: '#F8F6F3', borderWidth: 1.5, borderColor: '#E5E1D8',
  },
  durationChipActive: { backgroundColor: '#EEF2FF', borderColor: '#23519D' },
  durationLabel: { fontSize: 13, fontWeight: '700', color: '#6B7280' },
  durationLabelActive: { color: '#23519D' },
  durationBonus: { fontSize: 10, color: '#16A34A', fontWeight: '600', marginTop: 2 },
  durationBonusActive: { color: '#16A34A' },

  /* Results */
  resultCard: {
    marginHorizontal: 16, backgroundColor: '#23519D', borderRadius: BorderRadius.xl,
    padding: 20, gap: 12,
  },
  resultTitle: { fontSize: 16, fontWeight: '700', color: '#FFFFFF' },

  resultGrid: { flexDirection: 'row', alignItems: 'center' },
  resultItem: { flex: 1, alignItems: 'center', gap: 4 },
  resultValue: { fontSize: 24, fontWeight: '700', color: '#FFFFFF' },
  resultLabel: { fontSize: 11, color: 'rgba(255,255,255,0.6)', fontWeight: '500' },
  resultDivider: { width: 1, height: 40, backgroundColor: 'rgba(255,255,255,0.15)' },

  bonusRow: {
    backgroundColor: 'rgba(22,163,74,0.2)', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8,
  },
  bonusText: { fontSize: 13, fontWeight: '700', color: '#86EFAC', textAlign: 'center' },

  resultDividerFull: { height: 1, backgroundColor: 'rgba(255,255,255,0.15)' },

  resultSummary: { gap: 8 },
  resultSummaryRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  resultSummaryLabel: { fontSize: 13, color: 'rgba(255,255,255,0.7)' },
  resultSummaryValue: { fontSize: 15, fontWeight: '700', color: '#FFFFFF' },

  resultFooter: {
    backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8,
  },
  resultFooterText: { fontSize: 10, color: 'rgba(255,255,255,0.5)', lineHeight: 14, textAlign: 'center' },

  detailsWrap: {
    marginHorizontal: 16, borderRadius: BorderRadius.lg, overflow: 'hidden',
    borderWidth: 1, borderColor: '#E5E1D8',
  },
  detailsImg: { width: '100%', aspectRatio: 800 / 340 },

  cta: {
    marginHorizontal: 16, marginTop: 4, backgroundColor: '#16A34A',
    borderRadius: BorderRadius.md, paddingVertical: 14, alignItems: 'center',
  },
  ctaText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },

  disclaimer: {
    marginHorizontal: 16, marginTop: 8, backgroundColor: '#F8F6F3',
    borderRadius: BorderRadius.md, padding: 12, borderWidth: 1, borderColor: '#E5E1D8',
  },
  disclaimerText: { fontSize: 11, color: '#6B7280', lineHeight: 16 },
});
