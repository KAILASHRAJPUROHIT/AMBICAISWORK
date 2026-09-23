import { Linking, Pressable, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { MAPS_URL, MASTER, PENDING, TAGLINE } from '@/config/master';
import { BorderRadius, Shadow } from '@/constants/theme';

export default function StoreScreen() {
  const router = useRouter();

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        {/* Header */}
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
            <ThemedText style={styles.backText}>{'\u2190'}</ThemedText>
          </Pressable>
          <ThemedText style={styles.title}>Showroom</ThemedText>
          <View style={{ width: 36 }} />
        </View>

        {/* Hero Card */}
        <View style={[styles.heroCard, Shadow.md]}>
          <View style={styles.heroTop}>
            <ThemedText style={styles.heroName}>{MASTER.displayName}</ThemedText>
            <ThemedText style={styles.heroTag}>{TAGLINE}</ThemedText>
          </View>
          <View style={styles.heroDivider} />
          <View style={styles.heroAddress}>
            {MASTER.addressLines.map((line) => (
              <ThemedText key={line} style={styles.addressLine}>{line}</ThemedText>
            ))}
          </View>
          <ThemedText style={styles.landmark}>Landmark: Arihant Market, Tarapur Road</ThemedText>
        </View>

        {/* Action Buttons */}
        <View style={styles.actions}>
          <Pressable onPress={() => Linking.openURL(MAPS_URL)} style={[styles.actionBtn, styles.directionsBtn, Shadow.sm]}>
            <ThemedText style={styles.actionIcon}>{'\uD83D\uDCCD'}</ThemedText>
            <ThemedText style={styles.directionsBtnText}>Get Directions</ThemedText>
          </Pressable>
          <Pressable
            onPress={() => Linking.openURL(`tel:${MASTER.phone}`)}
            style={[styles.actionBtn, styles.callBtn, Shadow.sm]}>
            <ThemedText style={styles.actionIcon}>{'\uD83D\uDCDE'}</ThemedText>
            <ThemedText style={styles.callBtnText}>Call Showroom</ThemedText>
          </Pressable>
        </View>
        <Pressable
          onPress={() => {
            const text = encodeURIComponent(`Namaste ${MASTER.displayName}, I would like to visit the showroom.`);
            Linking.openURL(`${MASTER.whatsapp}?text=${text}`);
          }}
          style={[styles.whatsappBtn, Shadow.sm]}>
          <ThemedText style={styles.whatsappBtnText}>{'\uD83D\uDCAC'} WhatsApp Us \u2014 {MASTER.phone}</ThemedText>
        </Pressable>

        {/* Store Timings */}
        <View style={[styles.card, Shadow.sm]}>
          <ThemedText style={styles.cardTitle}>{'\u23F0'} Store Timings</ThemedText>
          {PENDING.storeTimings ? (
            PENDING.storeTimings.map((t) => (
              <ThemedText key={t} style={styles.cardText}>{t}</ThemedText>
            ))
          ) : (
            <ThemedText style={styles.cardTextPlaceholder}>
              Please call the showroom to confirm today{'\u2019'}s timings.
            </ThemedText>
          )}
        </View>

        {/* Business Details */}
        <View style={[styles.card, Shadow.sm]}>
          <ThemedText style={styles.cardTitle}>{'\u2139\uFE0F'} Business Details</ThemedText>
          <View style={styles.detailRow}>
            <ThemedText style={styles.detailLabel}>Legal Name</ThemedText>
            <ThemedText style={styles.detailValue}>{MASTER.legalName}</ThemedText>
          </View>
          <View style={styles.detailDivider} />
          <View style={styles.detailRow}>
            <ThemedText style={styles.detailLabel}>Constitution</ThemedText>
            <ThemedText style={styles.detailValue}>{MASTER.constitution}</ThemedText>
          </View>
          <View style={styles.detailDivider} />
          <View style={styles.detailRow}>
            <ThemedText style={styles.detailLabel}>GSTIN</ThemedText>
            <ThemedText style={styles.detailValue}>{MASTER.gstin}</ThemedText>
          </View>
          <View style={styles.detailDivider} />
          <View style={styles.detailRow}>
            <ThemedText style={styles.detailLabel}>Email</ThemedText>
            <ThemedText style={styles.detailValue}>{MASTER.email}</ThemedText>
          </View>
          <View style={styles.detailDivider} />
          <View style={styles.detailRow}>
            <ThemedText style={styles.detailLabel}>Instagram</ThemedText>
            <ThemedText style={styles.detailValue}>{MASTER.instagramHandle}</ThemedText>
          </View>
        </View>

        {/* Hallmark Trust */}
        <View style={styles.trustRow}>
          <View style={styles.trustBadge}>
            <ThemedText style={styles.trustBadgeText}>916</ThemedText>
          </View>
          <View style={{ flex: 1 }}>
            <ThemedText style={styles.trustTitle}>Hallmarked 916</ThemedText>
            <ThemedText style={styles.trustSub}>BIS certified gold jewellery</ThemedText>
          </View>
        </View>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFBF5' },
  safeArea: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  backBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#F8F6F3',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#E5E1D8',
  },
  backText: { fontSize: 18, color: '#1A1A2E' },
  title: { fontSize: 18, fontWeight: '700', color: '#1A1A2E' },

  /* Hero */
  heroCard: {
    marginHorizontal: 16,
    backgroundColor: '#FFFFFF',
    borderRadius: BorderRadius.xl,
    borderWidth: 1,
    borderColor: '#E5E1D8',
    padding: 20,
    gap: 12,
  },
  heroTop: { gap: 4 },
  heroName: { fontSize: 20, fontWeight: '700', color: '#1A1A2E' },
  heroTag: { fontSize: 12, color: '#C9A84C', letterSpacing: 1, textTransform: 'uppercase' },
  heroDivider: { height: 1, backgroundColor: '#F0ECE4' },
  heroAddress: { gap: 2 },
  addressLine: { fontSize: 14, color: '#1A1A2E', lineHeight: 20 },
  landmark: { fontSize: 12, color: '#6B7280', marginTop: 4 },

  /* Actions */
  actions: { flexDirection: 'row', gap: 10, paddingHorizontal: 16 },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 14,
    borderRadius: BorderRadius.md,
  },
  directionsBtn: { backgroundColor: '#23519D' },
  directionsBtnText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },
  callBtn: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#23519D' },
  callBtnText: { color: '#23519D', fontSize: 14, fontWeight: '700' },
  actionIcon: { fontSize: 16 },
  whatsappBtn: {
    marginHorizontal: 16,
    backgroundColor: '#16A34A',
    borderRadius: BorderRadius.md,
    paddingVertical: 14,
    alignItems: 'center',
  },
  whatsappBtnText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },

  /* Cards */
  card: {
    marginHorizontal: 16,
    backgroundColor: '#FFFFFF',
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: '#E5E1D8',
    padding: 16,
    gap: 8,
  },
  cardTitle: { fontSize: 15, fontWeight: '700', color: '#1A1A2E', marginBottom: 4 },
  cardText: { fontSize: 13, color: '#1A1A2E', lineHeight: 18 },
  cardTextPlaceholder: { fontSize: 13, color: '#6B7280', fontStyle: 'italic' },
  detailRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 6 },
  detailLabel: { fontSize: 12, color: '#6B7280' },
  detailValue: { fontSize: 13, fontWeight: '600', color: '#1A1A2E' },
  detailDivider: { height: 1, backgroundColor: '#F0ECE4' },

  /* Trust */
  trustRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: 16,
    backgroundColor: '#FDF8ED',
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: '#E8D9A8',
    padding: 14,
    gap: 12,
  },
  trustBadge: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#C9A84C',
    alignItems: 'center',
    justifyContent: 'center',
  },
  trustBadgeText: { fontSize: 16, fontWeight: '800', color: '#FFFFFF' },
  trustTitle: { fontSize: 14, fontWeight: '700', color: '#1A1A2E' },
  trustSub: { fontSize: 12, color: '#6B7280' },
});
