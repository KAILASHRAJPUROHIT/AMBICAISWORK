import { Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BorderRadius, Shadow } from '@/constants/theme';
import { MASTER } from '@/config/master';
import { useEnquiries, type Enquiry } from '@/store/enquiries';
import { getById } from '@/services/products';

const STATUS_CONFIG = {
  sent: { label: 'Enquiry Sent', color: '#23519D', bg: '#EEF2FF' },
  replied: { label: 'Replied', color: '#16A34A', bg: '#F0FDF4' },
  pending: { label: 'Pending', color: '#D97706', bg: '#FFFBEB' },
} as const;

function EnquiryCard({ enquiry }: { enquiry: Enquiry }) {
  const product = getById(enquiry.productId);
  const status = STATUS_CONFIG[enquiry.status];

  return (
    <View style={[styles.enquiryCard, Shadow.sm]}>
      <View style={styles.enquiryHeader}>
        <View style={styles.enquiryInfo}>
          <ThemedText style={styles.enquiryProduct} numberOfLines={1}>
            {enquiry.productName}
          </ThemedText>
          <ThemedText style={styles.enquiryCategory}>{enquiry.category}</ThemedText>
        </View>
        <View style={[styles.statusBadge, { backgroundColor: status.bg }]}>
          <View style={[styles.statusDot, { backgroundColor: status.color }]} />
          <ThemedText style={[styles.statusText, { color: status.color }]}>{status.label}</ThemedText>
        </View>
      </View>

      <ThemedText style={styles.enquiryMessage} numberOfLines={2}>
        {enquiry.message}
      </ThemedText>

      <View style={styles.enquiryFooter}>
        <ThemedText style={styles.enquiryDate}>
          {new Date(enquiry.createdAt).toLocaleDateString('en-IN', {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
          })}
        </ThemedText>
        <View style={styles.enquiryActions}>
          {product && (
            <Pressable
              onPress={() => Linking.openURL(`tel:${MASTER.phone}`)}
              style={styles.enquiryActionBtn}>
              <ThemedText style={styles.enquiryActionText}>Call</ThemedText>
            </Pressable>
          )}
          <Pressable
            onPress={() => {
              const text = encodeURIComponent(
                `Follow-up on my enquiry for ${enquiry.productName}.\n\nOriginal message: ${enquiry.message}`
              );
              Linking.openURL(`${MASTER.whatsapp}?text=${text}`);
            }}
            style={[styles.enquiryActionBtn, styles.enquiryActionBtnPrimary]}>
            <ThemedText style={[styles.enquiryActionText, { color: '#FFFFFF' }]}>WhatsApp</ThemedText>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

export default function EnquiriesScreen() {
  const router = useRouter();
  const { enquiries } = useEnquiries();

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
            <ThemedText style={styles.backText}>{'\u2190'}</ThemedText>
          </Pressable>
          <ThemedText style={styles.title}>My Enquiries</ThemedText>
          <View style={{ width: 36 }} />
        </View>

        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          {enquiries.length === 0 ? (
            <View style={styles.emptyState}>
              <ThemedText style={styles.emptyIcon}>{'\uD83D\uDCAC'}</ThemedText>
              <ThemedText style={styles.emptyTitle}>No Enquiries Yet</ThemedText>
              <ThemedText style={styles.emptyDesc}>
                When you enquire about a product, it will appear here for easy tracking.
              </ThemedText>
              <Pressable onPress={() => router.push('/')} style={styles.emptyBtn}>
                <ThemedText style={styles.emptyBtnText}>Browse Collections</ThemedText>
              </Pressable>
            </View>
          ) : (
            <>
              <View style={styles.summaryRow}>
                <View style={styles.summaryItem}>
                  <ThemedText style={styles.summaryValue}>{enquiries.length}</ThemedText>
                  <ThemedText style={styles.summaryLabel}>Total</ThemedText>
                </View>
                <View style={styles.summaryItem}>
                  <ThemedText style={[styles.summaryValue, { color: '#D97706' }]}>
                    {enquiries.filter((e) => e.status === 'pending').length}
                  </ThemedText>
                  <ThemedText style={styles.summaryLabel}>Pending</ThemedText>
                </View>
                <View style={styles.summaryItem}>
                  <ThemedText style={[styles.summaryValue, { color: '#16A34A' }]}>
                    {enquiries.filter((e) => e.status === 'replied').length}
                  </ThemedText>
                  <ThemedText style={styles.summaryLabel}>Replied</ThemedText>
                </View>
              </View>

              {enquiries.map((enquiry) => (
                <EnquiryCard key={enquiry.id} enquiry={enquiry} />
              ))}
            </>
          )}

          <View style={styles.tipCard}>
            <ThemedText style={styles.tipTitle}>Tip</ThemedText>
            <ThemedText style={styles.tipText}>
              Enquiries are stored on your device. Visit the showroom for instant responses and
              personalized recommendations.
            </ThemedText>
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

  scroll: { padding: 16, gap: 12, paddingBottom: 100 },

  /* Empty State */
  emptyState: {
    alignItems: 'center', paddingVertical: 60, gap: 12,
  },
  emptyIcon: { fontSize: 48 },
  emptyTitle: { fontSize: 20, fontWeight: '700', color: '#1A1A2E' },
  emptyDesc: { fontSize: 14, color: '#6B7280', textAlign: 'center', lineHeight: 20, maxWidth: 280 },
  emptyBtn: {
    backgroundColor: '#23519D', borderRadius: BorderRadius.md, paddingHorizontal: 24, paddingVertical: 12, marginTop: 8,
  },
  emptyBtnText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },

  /* Summary */
  summaryRow: {
    flexDirection: 'row', backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg,
    borderWidth: 1, borderColor: '#E5E1D8', padding: 16, gap: 16,
  },
  summaryItem: { flex: 1, alignItems: 'center', gap: 4 },
  summaryValue: { fontSize: 24, fontWeight: '700', color: '#1A1A2E' },
  summaryLabel: { fontSize: 11, color: '#6B7280', fontWeight: '500' },

  /* Enquiry Card */
  enquiryCard: {
    backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg, borderWidth: 1, borderColor: '#E5E1D8', padding: 16, gap: 10,
  },
  enquiryHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  enquiryInfo: { flex: 1, gap: 2 },
  enquiryProduct: { fontSize: 15, fontWeight: '700', color: '#1A1A2E' },
  enquiryCategory: { fontSize: 12, color: '#6B7280' },
  statusBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 12,
  },
  statusDot: { width: 5, height: 5, borderRadius: 3 },
  statusText: { fontSize: 10, fontWeight: '700' },
  enquiryMessage: { fontSize: 13, color: '#6B7280', lineHeight: 18 },
  enquiryFooter: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    borderTopWidth: 1, borderTopColor: '#F0ECE4', paddingTop: 10,
  },
  enquiryDate: { fontSize: 11, color: '#9CA3AF' },
  enquiryActions: { flexDirection: 'row', gap: 8 },
  enquiryActionBtn: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8,
    backgroundColor: '#F8F6F3', borderWidth: 1, borderColor: '#E5E1D8',
  },
  enquiryActionBtnPrimary: { backgroundColor: '#23519D', borderColor: '#23519D' },
  enquiryActionText: { fontSize: 11, fontWeight: '600', color: '#1A1A2E' },

  /* Tip */
  tipCard: {
    backgroundColor: '#FDF8ED', borderRadius: BorderRadius.md, padding: 14,
    borderWidth: 1, borderColor: '#E8D9A8', gap: 4,
  },
  tipTitle: { fontSize: 13, fontWeight: '700', color: '#A68523' },
  tipText: { fontSize: 12, color: '#6B7280', lineHeight: 16 },
});
