import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  Pressable,
  RefreshControl,
  ScrollView,
  Share,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing, BorderRadius, Shadow } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { fetchRateSnapshot, find18kt, formatInr, subscribeRates, type RateSnapshot } from '@/services/rates';

export default function GoldRateScreen() {
  const colors = useTheme();
  const [snap, setSnap] = useState<RateSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [connected, setConnected] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = await fetchRateSnapshot();
      setSnap(s);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not reach rate server');
    }
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeRates({
      onData: (s) => {
        setSnap(s);
        setError(null);
      },
      onStatus: setConnected,
    });
    return unsubscribe;
  }, []);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const g = snap?.published;
  const v18 = snap ? find18kt(snap) : undefined;
  const sil = snap?.silver?.published;
  const live = connected && g?.status === 'VERIFIED';

  const shareRates = () => {
    if (!g) return;
    const msg = [
      `Today's Gold & Silver Rates — Aradhana Jewellers, Boisar`,
      ``,
      `Gold 22K: \u20B9${formatInr(g.rate22kt)}/10g`,
      `Gold 24K: \u20B9${formatInr(g.rate24kt)}/10g`,
      v18 ? `Gold 18K: \u20B9${formatInr(v18.rate)}/10g` : null,
      sil ? `Silver Pure: \u20B9${formatInr(sil.pure)}/kg` : null,
      sil ? `Silver Ornament: \u20B9${formatInr(sil.ornament)}/kg` : null,
      ``,
      `Updated: ${g.atIst} IST`,
      `Hallmarked 916 jewellery · Boisar, Palghar`,
    ].filter(Boolean).join('\n');
    void Share.share({ message: msg });
  };

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.gold} />
          }>
          {/* Header */}
          <View style={styles.headerRow}>
            <View>
              <ThemedText style={styles.screenTitle}>Metal Rates</ThemedText>
              <ThemedText style={styles.screenSub}>Aradhana Jewellers, Boisar</ThemedText>
            </View>
            <View style={styles.headerActions}>
              <View style={[styles.liveBadge, { backgroundColor: live ? '#16A34A' : '#D97706' }]}>
                <View style={styles.liveDot} />
                <ThemedText style={styles.liveText}>{live ? 'LIVE' : 'SYNCING'}</ThemedText>
              </View>
              <Pressable onPress={shareRates} style={styles.shareBtn} accessibilityLabel="Share rates">
                <ThemedText style={styles.shareIcon}>{'\u2197'}</ThemedText>
              </Pressable>
            </View>
          </View>

          {!snap && !error && (
            <ActivityIndicator color={colors.gold} style={styles.loader} />
          )}
          {error && (
            <View style={styles.errorCard}>
              <ThemedText style={styles.errorText}>{error}</ThemedText>
              <ThemedText style={styles.errorSub}>Pull down to retry</ThemedText>
            </View>
          )}

          {g && (
            <>
              {/* Hero Card — 22K Gold */}
              <View style={styles.heroCard}>
                <View style={styles.heroTop}>
                  <ThemedText style={styles.heroLabel}>GOLD 22K</ThemedText>
                  <View style={styles.heroBadge}>
                    <ThemedText style={styles.heroBadgeText}>TODAY</ThemedText>
                  </View>
                </View>
                <ThemedText style={styles.heroRate} numberOfLines={1} adjustsFontSizeToFit>
                  {'\u20B9'} {formatInr(g.rate22kt)}
                </ThemedText>
                <ThemedText style={styles.heroUnit}>per 10 grams</ThemedText>
                <View style={styles.heroDivider} />
                <View style={styles.heroBottom}>
                  <View style={styles.heroStat}>
                    <ThemedText style={styles.heroStatLabel}>Session High</ThemedText>
                    <ThemedText style={styles.heroStatValue}>{'\u20B9'}{formatInr(g.high)}</ThemedText>
                  </View>
                  <View style={styles.heroStat}>
                    <ThemedText style={styles.heroStatLabel}>Session Low</ThemedText>
                    <ThemedText style={styles.heroStatValue}>{'\u20B9'}{formatInr(g.low)}</ThemedText>
                  </View>
                </View>
              </View>

              {/* Rate Grid */}
              <View style={styles.rateGrid}>
                <RateTile label="24K GOLD" value={`\u20B9 ${formatInr(g.rate24kt)}`} sub="per 10g" accent={colors.primary} />
                <RateTile
                  label="18K GOLD"
                  value={v18 ? `\u20B9 ${formatInr(v18.rate)}` : '\u2014'}
                  sub="per 10g"
                  accent={colors.goldDeep}
                />
                <RateTile
                  label={sil?.pureLabel?.toUpperCase() ?? 'SILVER PURE'}
                  value={sil ? `\u20B9 ${formatInr(sil.pure)}` : '\u2014'}
                  sub="per kg"
                  accent="#6B7280"
                />
                <RateTile
                  label={sil?.ornamentLabel?.toUpperCase() ?? 'SILVER ORNAMENT'}
                  value={sil ? `\u20B9 ${formatInr(sil.ornament)}` : '\u2014'}
                  sub="per kg"
                  accent="#6B7280"
                />
              </View>

              {/* Last Updated */}
              <View style={styles.metaCard}>
                <View style={styles.metaRow}>
                  <ThemedText style={styles.metaLabel}>Last Updated</ThemedText>
                  <ThemedText style={styles.metaValue}>{g.atIst} IST</ThemedText>
                </View>
                <View style={styles.metaDivider} />
                <View style={styles.metaRow}>
                  <ThemedText style={styles.metaLabel}>Confidence</ThemedText>
                  <ThemedText style={styles.metaValue}>{g.confidence}%</ThemedText>
                </View>
                <View style={styles.metaDivider} />
                <View style={styles.metaRow}>
                  <ThemedText style={styles.metaLabel}>Source</ThemedText>
                  <ThemedText style={styles.metaValue}>Safari Bullions</ThemedText>
                </View>
              </View>

              {/* Rate Alert */}
              <View style={styles.alertCard}>
                <ThemedText style={styles.alertTitle}>{'\uD83D\uDD14'} Rate Alerts</ThemedText>
                <ThemedText style={styles.alertDesc}>
                  Get notified when gold or silver rates change meaningfully. Never miss a good time to buy.
                </ThemedText>
                <Pressable style={styles.alertBtn} onPress={() => {
                  const text = encodeURIComponent('Namaste, I want to receive gold rate alerts from Aradhana Jewellers, Boisar.');
                  Linking.openURL(`https://wa.me/919422682086?text=${text}`);
                }}>
                  <ThemedText style={styles.alertBtnText}>Follow Rate Updates</ThemedText>
                </Pressable>
              </View>
            </>
          )}

          <View style={styles.disclaimer}>
            <ThemedText style={styles.disclaimerText}>
              Rates are indicative and change with the market. Final price is confirmed at the counter
              based on weight and the prevailing rate at that time. Hallmarked 916 jewellery.
            </ThemedText>
          </View>
        </ScrollView>
      </SafeAreaView>
    </ThemedView>
  );
}

function RateTile({ label, value, sub, accent }: { label: string; value: string; sub: string; accent: string }) {
  return (
    <View style={[styles.tile, Shadow.sm]}>
      <View style={[styles.tileAccent, { backgroundColor: accent }]} />
      <ThemedText style={styles.tileLabel}>{label}</ThemedText>
      <ThemedText style={styles.tileValue}>{value}</ThemedText>
      <ThemedText style={styles.tileSub}>{sub}</ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFBF5' },
  safeArea: { flex: 1 },
  content: { padding: 20, gap: 16, paddingBottom: Spacing.six },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  screenTitle: { fontSize: 26, fontWeight: '700', color: '#1A1A2E', letterSpacing: -0.5 },
  screenSub: { fontSize: 13, color: '#6B7280', marginTop: 2 },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  liveBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
  },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#fff' },
  liveText: { color: '#fff', fontSize: 10, fontWeight: '700', letterSpacing: 1 },
  shareBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#F8F6F3',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#E5E1D8',
  },
  shareIcon: { fontSize: 16, color: '#1A1A2E' },
  loader: { marginTop: 40 },
  errorCard: {
    backgroundColor: '#FEF2F2',
    borderRadius: BorderRadius.lg,
    padding: 16,
    borderWidth: 1,
    borderColor: '#FECACA',
  },
  errorText: { color: '#DC2626', fontWeight: '600', fontSize: 14 },
  errorSub: { color: '#DC2626', fontSize: 12, opacity: 0.7, marginTop: 2 },

  /* Hero Card */
  heroCard: {
    backgroundColor: '#23519D',
    borderRadius: BorderRadius.xl,
    padding: 24,
    gap: 4,
  },
  heroTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  heroLabel: { color: '#C9A84C', fontSize: 13, fontWeight: '700', letterSpacing: 2 },
  heroBadge: {
    backgroundColor: 'rgba(201,168,76,0.2)',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  heroBadgeText: { color: '#C9A84C', fontSize: 9, fontWeight: '700', letterSpacing: 1 },
  heroRate: { color: '#FFFFFF', fontSize: 36, fontWeight: '700', letterSpacing: -0.5 },
  heroUnit: { color: 'rgba(255,255,255,0.6)', fontSize: 12, marginBottom: 8 },
  heroDivider: { height: 1, backgroundColor: 'rgba(201,168,76,0.25)', marginBottom: 8 },
  heroBottom: { flexDirection: 'row', gap: 24 },
  heroStat: { gap: 2 },
  heroStatLabel: { color: 'rgba(255,255,255,0.5)', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5 },
  heroStatValue: { color: '#FFFFFF', fontSize: 15, fontWeight: '600' },

  /* Rate Grid */
  rateGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  tile: {
    width: '47%',
    flexGrow: 1,
    backgroundColor: '#FFFFFF',
    borderRadius: BorderRadius.lg,
    padding: 16,
    gap: 4,
    borderWidth: 1,
    borderColor: '#E5E1D8',
    overflow: 'hidden',
  },
  tileAccent: { position: 'absolute', top: 0, left: 0, width: 3, height: '100%', borderRadius: 2 },
  tileLabel: { fontSize: 10, fontWeight: '700', color: '#6B7280', letterSpacing: 1, marginLeft: 6 },
  tileValue: { fontSize: 18, fontWeight: '700', color: '#1A1A2E', marginLeft: 6 },
  tileSub: { fontSize: 11, color: '#9CA3AF', marginLeft: 6 },

  /* Meta Card */
  metaCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: BorderRadius.lg,
    padding: 16,
    borderWidth: 1,
    borderColor: '#E5E1D8',
    gap: 10,
  },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  metaLabel: { fontSize: 12, color: '#6B7280' },
  metaValue: { fontSize: 12, fontWeight: '600', color: '#1A1A2E' },
  metaDivider: { height: 1, backgroundColor: '#F0ECE4' },

  /* Alert Card */
  alertCard: {
    backgroundColor: '#FDF8ED',
    borderRadius: BorderRadius.lg,
    padding: 16,
    borderWidth: 1,
    borderColor: '#E8D9A8',
    gap: 8,
  },
  alertTitle: { fontSize: 15, fontWeight: '700', color: '#1A1A2E' },
  alertDesc: { fontSize: 13, color: '#6B7280', lineHeight: 18 },
  alertBtn: {
    backgroundColor: '#23519D',
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
    marginTop: 4,
  },
  alertBtnText: { color: '#FFFFFF', fontSize: 13, fontWeight: '700' },

  /* Disclaimer */
  disclaimer: {
    backgroundColor: '#F8F6F3',
    borderRadius: BorderRadius.md,
    padding: 14,
    borderWidth: 1,
    borderColor: '#E5E1D8',
  },
  disclaimerText: { fontSize: 11, color: '#6B7280', lineHeight: 16 },
});
