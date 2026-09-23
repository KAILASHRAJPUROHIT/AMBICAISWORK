import { Clipboard, Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing, BorderRadius } from '@/constants/theme';
import { MASTER } from '@/config/master';

const bankDetails = [
  { label: 'Account Name', value: MASTER.legalName },
  { label: 'Bank Name', value: 'To be confirmed by Aradhana' },
  { label: 'Branch', value: 'Boisar, Palghar' },
  { label: 'Account Number', value: '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022', copyable: false },
  { label: 'IFSC Code', value: '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022', copyable: false },
  { label: 'Account Type', value: 'Current' },
];

const upiDetails = [
  { label: 'Primary UPI', id: 'To be configured by Aradhana' },
  { label: 'Alternate UPI', id: 'To be configured by Aradhana' },
];

export default function BankDetailsScreen() {
  const router = useRouter();

  const copyToClipboard = (text: string) => {
    if (text.startsWith('\u2022')) return;
    Clipboard.setString(text);
  };

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <ScrollView contentContainerStyle={styles.content}>
          {/* Header */}
          <View style={styles.header}>
            <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
              <ThemedText style={styles.backText}>{'\u2190'}</ThemedText>
            </Pressable>
            <ThemedText style={styles.title}>Bank Details &amp; Payments</ThemedText>
            <View style={{ width: 36 }} />
          </View>

          {/* Safety Warning */}
          <View style={styles.warningCard}>
            <ThemedText style={styles.warningIcon}>{'\u26A0\uFE0F'}</ThemedText>
            <View style={{ flex: 1 }}>
              <ThemedText style={styles.warningTitle}>Payment Safety</ThemedText>
              <ThemedText style={styles.warningText}>
                Only make payments to bank accounts and UPI IDs shown inside the official {MASTER.displayName} app.
                For large payments, please confirm payment details with the showroom before transferring funds.
              </ThemedText>
            </View>
          </View>

          {/* Bank Account Details */}
          <ThemedText style={styles.sectionTitle}>BANK ACCOUNT DETAILS</ThemedText>
          <View style={styles.card}>
            {bankDetails.map((item, idx) => (
              <View key={item.label}>
                <View style={styles.detailRow}>
                  <View style={{ flex: 1 }}>
                    <ThemedText style={styles.detailLabel}>{item.label}</ThemedText>
                    <ThemedText style={styles.detailValue}>{item.value}</ThemedText>
                  </View>
                  {item.copyable !== false && !item.value.startsWith('\u2022') && (
                    <Pressable onPress={() => copyToClipboard(item.value)} style={styles.copyBtn}>
                      <ThemedText style={styles.copyBtnText}>Copy</ThemedText>
                    </Pressable>
                  )}
                </View>
                {idx < bankDetails.length - 1 && <View style={styles.divider} />}
              </View>
            ))}
          </View>

          {/* UPI Details */}
          <ThemedText style={styles.sectionTitle}>UPI DETAILS</ThemedText>
          {upiDetails.map((item) => (
            <View key={item.label} style={styles.card}>
              <ThemedText style={styles.upiLabel}>{item.label}</ThemedText>
              <View style={styles.upiRow}>
                <View style={styles.qrPlaceholder}>
                  <ThemedText style={styles.qrText}>QR Code</ThemedText>
                  <ThemedText style={styles.qrSub}>To be configured</ThemedText>
                </View>
                <View style={{ flex: 1, gap: 8 }}>
                  <View>
                    <ThemedText style={styles.upiIdLabel}>UPI ID</ThemedText>
                    <ThemedText style={styles.upiIdValue}>{item.id}</ThemedText>
                  </View>
                  <Pressable style={styles.copyUpiBtn} onPress={() => copyToClipboard(item.id)}>
                    <ThemedText style={styles.copyUpiBtnText}>Copy UPI ID</ThemedText>
                  </Pressable>
                </View>
              </View>
            </View>
          ))}

          {/* I've Made a Payment */}
          <ThemedText style={styles.sectionTitle}>PAYMENT CONFIRMATION</ThemedText>
          <Pressable
            onPress={() => {
              const text = encodeURIComponent(
                `Namaste ${MASTER.displayName}, I have made a payment. Please share the amount and UTR reference.`,
              );
              Linking.openURL(`${MASTER.whatsapp}?text=${text}`);
            }}
            style={styles.cta}>
            <ThemedText style={styles.ctaText}>{'\u2714'} I have Made a Payment</ThemedText>
          </Pressable>
          <ThemedText style={styles.ctaSub}>
            Share your payment details via WhatsApp. Our team will verify and confirm.
          </ThemedText>

          {/* Disclaimer */}
          <View style={styles.disclaimer}>
            <ThemedText style={styles.disclaimerText}>
              All payment details are controlled by {MASTER.displayName}. Changes to payment details require
              authorised admin access and are logged for security. Never share payment details from external sources.
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
  content: { padding: 16, gap: 16, paddingBottom: Spacing.six },

  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
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

  /* Warning */
  warningCard: {
    flexDirection: 'row',
    backgroundColor: '#FEF3C7',
    borderRadius: BorderRadius.lg,
    padding: 16,
    borderWidth: 1,
    borderColor: '#FDE68A',
    gap: 10,
  },
  warningIcon: { fontSize: 20 },
  warningTitle: { fontSize: 14, fontWeight: '700', color: '#92400E', marginBottom: 4 },
  warningText: { fontSize: 12, color: '#92400E', lineHeight: 17 },

  /* Sections */
  sectionTitle: { fontSize: 11, fontWeight: '700', color: '#9CA3AF', letterSpacing: 1.5 },

  /* Card */
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: '#E5E1D8',
    padding: 16,
    gap: 0,
  },
  detailRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10 },
  detailLabel: { fontSize: 12, color: '#6B7280', marginBottom: 2 },
  detailValue: { fontSize: 14, fontWeight: '600', color: '#1A1A2E' },
  copyBtn: {
    borderWidth: 1,
    borderColor: '#23519D',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 5,
  },
  copyBtnText: { fontSize: 12, fontWeight: '600', color: '#23519D' },
  divider: { height: 1, backgroundColor: '#F0ECE4' },

  /* UPI */
  upiLabel: { fontSize: 14, fontWeight: '700', color: '#1A1A2E', marginBottom: 12 },
  upiRow: { flexDirection: 'row', gap: 14 },
  qrPlaceholder: {
    width: 100,
    height: 100,
    borderRadius: 12,
    backgroundColor: '#F8F6F3',
    borderWidth: 1,
    borderColor: '#E5E1D8',
    alignItems: 'center',
    justifyContent: 'center',
  },
  qrText: { fontSize: 12, fontWeight: '600', color: '#6B7280' },
  qrSub: { fontSize: 10, color: '#9CA3AF' },
  upiIdLabel: { fontSize: 11, color: '#6B7280' },
  upiIdValue: { fontSize: 13, fontWeight: '600', color: '#1A1A2E', marginTop: 2 },
  copyUpiBtn: {
    backgroundColor: '#F8F6F3',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#E5E1D8',
    paddingVertical: 8,
    alignItems: 'center',
  },
  copyUpiBtnText: { fontSize: 12, fontWeight: '600', color: '#23519D' },

  /* CTA */
  cta: {
    backgroundColor: '#16A34A',
    borderRadius: BorderRadius.md,
    paddingVertical: 14,
    alignItems: 'center',
  },
  ctaText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },
  ctaSub: { fontSize: 12, color: '#6B7280', textAlign: 'center', marginTop: -8 },

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
