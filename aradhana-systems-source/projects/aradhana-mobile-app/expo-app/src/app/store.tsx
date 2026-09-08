import { useCallback } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { MAPS_URL, MASTER, TAGLINE } from '@/config/master';
import { BorderRadius, Shadow } from '@/constants/theme';

const STORE_TIMINGS = [
  { day: 'Monday - Saturday', time: '10:00 AM - 8:30 PM' },
  { day: 'Sunday', time: '11:00 AM - 7:00 PM' },
];

const WHY_VISIT = [
  { icon: '\uD83D\uDC8E', title: 'Try Before You Buy', desc: 'Touch and feel 500+ designs in person' },
  { icon: '\uD83D\uDD27', title: 'Custom Design', desc: 'Get bespoke jewellery made to your vision' },
  { icon: '\u2728', title: 'Lifetime Service', desc: 'Free cleaning, polishing & repair support' },
  { icon: '\uD83D\uDCB0', title: 'Best Exchange Value', desc: 'Transparent gold exchange with live rates' },
];

export default function StoreScreen() {
  const router = useRouter();

  const handleBookVisit = useCallback(() => {
    const text = encodeURIComponent(
      `Namaste ${MASTER.displayName},\n\nI would like to schedule a visit to your showroom.\n\nPlease share available time slots.\n\nThank you!`
    );
    Linking.openURL(`${MASTER.whatsapp}?text=${text}`);
  }, []);

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

        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          {/* Hero Card */}
          <View style={[styles.heroCard, Shadow.md]}>
            <View style={styles.heroTop}>
              <View style={styles.heroBrandRow}>
                <View style={styles.omLogo}>
                  <ThemedText style={styles.omText}>{'\u0950'}</ThemedText>
                </View>
                <View style={{ flex: 1 }}>
                  <ThemedText style={styles.heroName}>{MASTER.displayName}</ThemedText>
                  <ThemedText style={styles.heroTag}>{TAGLINE}</ThemedText>
                </View>
              </View>
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

          {/* Book Visit CTA */}
          <Pressable onPress={handleBookVisit} style={[styles.bookVisitBtn, Shadow.sm]}>
            <View style={styles.bookVisitLeft}>
              <ThemedText style={styles.bookVisitIcon}>{'\uD83D\uDCC5'}</ThemedText>
              <View style={{ flex: 1 }}>
                <ThemedText style={styles.bookVisitTitle}>Book a Visit</ThemedText>
                <ThemedText style={styles.bookVisitSub}>Schedule a private appointment</ThemedText>
              </View>
            </View>
            <ThemedText style={styles.bookVisitArrow}>{'\u2192'}</ThemedText>
          </Pressable>

          {/* WhatsApp CTA */}
          <Pressable
            onPress={() => {
              const text = encodeURIComponent(`Namaste ${MASTER.displayName}, I have a question about your jewellery.`);
              Linking.openURL(`${MASTER.whatsapp}?text=${text}`);
            }}
            style={[styles.whatsappBtn, Shadow.sm]}>
            <ThemedText style={styles.whatsappBtnText}>{'\uD83D\uDCAC'} WhatsApp Us \u2014 {MASTER.phone}</ThemedText>
          </Pressable>

          {/* Store Timings */}
          <View style={[styles.card, Shadow.sm]}>
            <ThemedText style={styles.cardTitle}>{'\u23F0'} Store Timings</ThemedText>
            {STORE_TIMINGS.map((t) => (
              <View key={t.day} style={styles.timingRow}>
                <ThemedText style={styles.timingDay}>{t.day}</ThemedText>
                <ThemedText style={styles.timingTime}>{t.time}</ThemedText>
              </View>
            ))}
            <View style={styles.timingNote}>
              <ThemedText style={styles.timingNoteText}>
                Timings may vary on public holidays. Please call to confirm.
              </ThemedText>
            </View>
          </View>

          {/* Why Visit */}
          <View style={[styles.card, Shadow.sm]}>
            <ThemedText style={styles.cardTitle}>Why Visit Our Showroom</ThemedText>
            <View style={styles.whyGrid}>
              {WHY_VISIT.map((item) => (
                <View key={item.title} style={styles.whyItem}>
                  <ThemedText style={styles.whyIcon}>{item.icon}</ThemedText>
                  <View style={{ flex: 1 }}>
                    <ThemedText style={styles.whyTitle}>{item.title}</ThemedText>
                    <ThemedText style={styles.whyDesc}>{item.desc}</ThemedText>
                  </View>
                </View>
              ))}
            </View>
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
              <ThemedText style={styles.trustSub}>BIS certified gold jewellery \u2014 every piece tested & certified</ThemedText>
            </View>
          </View>
        </ScrollView>
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

  /* Hero */
  heroCard: {
    marginHorizontal: 16, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.xl,
    borderWidth: 1, borderColor: '#E5E1D8', padding: 20, gap: 12,
  },
  heroTop: { gap: 4 },
  heroBrandRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  omLogo: {
    width: 48, height: 48, borderRadius: 24, backgroundColor: '#FDF8ED',
    alignItems: 'center', justifyContent: 'center', borderWidth: 1.5, borderColor: '#C9A84C',
  },
  omText: { fontSize: 24, color: '#C9A84C', fontWeight: '700' },
  heroName: { fontSize: 20, fontWeight: '700', color: '#1A1A2E' },
  heroTag: { fontSize: 11, color: '#C9A84C', letterSpacing: 1, textTransform: 'uppercase' },
  heroDivider: { height: 1, backgroundColor: '#F0ECE4' },
  heroAddress: { gap: 2 },
  addressLine: { fontSize: 14, color: '#1A1A2E', lineHeight: 20 },
  landmark: { fontSize: 12, color: '#6B7280', marginTop: 4 },

  /* Actions */
  actions: { flexDirection: 'row', gap: 10, paddingHorizontal: 16 },
  actionBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 8, paddingVertical: 14, borderRadius: BorderRadius.md,
  },
  directionsBtn: { backgroundColor: '#23519D' },
  directionsBtnText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },
  callBtn: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#23519D' },
  callBtnText: { color: '#23519D', fontSize: 14, fontWeight: '700' },
  actionIcon: { fontSize: 16 },

  /* Book Visit */
  bookVisitBtn: {
    marginHorizontal: 16, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg,
    borderWidth: 1, borderColor: '#C9A84C', padding: 16,
  },
  bookVisitLeft: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  bookVisitIcon: { fontSize: 28 },
  bookVisitTitle: { fontSize: 15, fontWeight: '700', color: '#1A1A2E' },
  bookVisitSub: { fontSize: 12, color: '#6B7280', marginTop: 2 },
  bookVisitArrow: { fontSize: 18, color: '#C9A84C', fontWeight: '700', marginTop: 8 },

  whatsappBtn: {
    marginHorizontal: 16, backgroundColor: '#16A34A',
    borderRadius: BorderRadius.md, paddingVertical: 14, alignItems: 'center',
  },
  whatsappBtnText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },

  /* Cards */
  card: {
    marginHorizontal: 16, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg,
    borderWidth: 1, borderColor: '#E5E1D8', padding: 16, gap: 8,
  },
  cardTitle: { fontSize: 15, fontWeight: '700', color: '#1A1A2E', marginBottom: 4 },

  /* Timings */
  timingRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#F0ECE4',
  },
  timingDay: { fontSize: 13, fontWeight: '600', color: '#1A1A2E' },
  timingTime: { fontSize: 13, fontWeight: '700', color: '#23519D' },
  timingNote: {
    backgroundColor: '#F8F6F3', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, marginTop: 4,
  },
  timingNoteText: { fontSize: 11, color: '#6B7280', fontStyle: 'italic' },

  /* Why Visit */
  whyGrid: { gap: 12 },
  whyItem: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  whyIcon: { fontSize: 24, width: 36, textAlign: 'center' },
  whyTitle: { fontSize: 13, fontWeight: '700', color: '#1A1A2E' },
  whyDesc: { fontSize: 11, color: '#6B7280', marginTop: 1 },

  /* Business Details */
  detailRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 6,
  },
  detailLabel: { fontSize: 12, color: '#6B7280' },
  detailValue: { fontSize: 13, fontWeight: '600', color: '#1A1A2E' },
  detailDivider: { height: 1, backgroundColor: '#F0ECE4' },

  /* Trust */
  trustRow: {
    flexDirection: 'row', alignItems: 'center', marginHorizontal: 16,
    backgroundColor: '#FDF8ED', borderRadius: BorderRadius.lg,
    borderWidth: 1, borderColor: '#E8D9A8', padding: 14, gap: 12,
  },
  trustBadge: {
    width: 48, height: 48, borderRadius: 24, backgroundColor: '#C9A84C',
    alignItems: 'center', justifyContent: 'center',
  },
  trustBadgeText: { fontSize: 16, fontWeight: '800', color: '#FFFFFF' },
  trustTitle: { fontSize: 14, fontWeight: '700', color: '#1A1A2E' },
  trustSub: { fontSize: 12, color: '#6B7280' },
});
