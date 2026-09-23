import { FlatList, Image, Linking, Pressable, Share, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BorderRadius, Shadow } from '@/constants/theme';
import { MASTER } from '@/config/master';
import { useCart } from '@/store/cart';
import { getById, imageFor } from '@/services/products';

export default function CartScreen() {
  const router = useRouter();
  const { items, remove } = useCart();

  const cartProducts = items
    .map((item) => ({ ...item, product: getById(item.productId) }))
    .filter((item) => item.product);

  const enquireAll = () => {
    if (cartProducts.length === 0) return;
    const list = cartProducts
      .map((item) => `\u2022 ${item.product!.categoryName} (${item.product!.label})`)
      .join('\n');
    const text = encodeURIComponent(
      `Namaste ${MASTER.displayName}, I am interested in the following items:\n\n${list}\n\nPlease share details and pricing.`,
    );
    Linking.openURL(`${MASTER.whatsapp}?text=${text}`);
  };

  const shareAll = () => {
    if (cartProducts.length === 0) return;
    const list = cartProducts
      .map((item) => `\u2022 ${item.product!.categoryName} \u2014 ${item.product!.label}`)
      .join('\n');
    void Share.share({
      message: `My favourites from ${MASTER.displayName}, Boisar:\n\n${list}\n\nView in the Aradhana Jewellers app.`,
    });
  };

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
            <ThemedText style={styles.backText}>{'\u2190'}</ThemedText>
          </Pressable>
          <ThemedText style={styles.title}>My Cart</ThemedText>
          <View style={{ width: 36 }} />
        </View>

        {cartProducts.length === 0 ? (
          <View style={styles.emptyState}>
            <ThemedText style={styles.emptyIcon}>{'\uD83D\uDED2'}</ThemedText>
            <ThemedText style={styles.emptyTitle}>Your cart is empty</ThemedText>
            <ThemedText style={styles.emptySub}>Browse our collections and add items you love.</ThemedText>
            <Pressable onPress={() => router.push('/collections')} style={styles.emptyBtn}>
              <ThemedText style={styles.emptyBtnText}>Browse Collections</ThemedText>
            </Pressable>
          </View>
        ) : (
          <>
            <FlatList
              data={cartProducts}
              keyExtractor={(item) => item.productId}
              contentContainerStyle={styles.list}
              renderItem={({ item }) => {
                const img = imageFor(item.product!);
                return (
                  <View style={[styles.card, Shadow.sm]}>
                    {img ? (
                      <Image source={img} style={styles.cardImg} resizeMode="contain" />
                    ) : (
                      <View style={[styles.cardImg, styles.cardImgPlaceholder]} />
                    )}
                    <View style={styles.cardInfo}>
                      <ThemedText style={styles.cardName} numberOfLines={1}>{item.product!.categoryName}</ThemedText>
                      <ThemedText style={styles.cardLabel} numberOfLines={1}>Item {item.product!.label}</ThemedText>
                      <ThemedText style={styles.cardMeta}>
                        {item.product!.karat ? `${item.product!.karat}K` : ''}
                        {item.product!.karat && item.product!.weight ? ' \u00B7 ' : ''}
                        {item.product!.weight ? `${item.product!.weight.toFixed(2)}g` : ''}
                      </ThemedText>
                    </View>
                    <Pressable onPress={() => remove(item.productId)} style={styles.removeBtn}>
                      <ThemedText style={styles.removeBtnText}>{'\u2715'}</ThemedText>
                    </Pressable>
                  </View>
                );
              }}
            />

            <View style={styles.bottomBar}>
              <View style={styles.bottomInfo}>
                <ThemedText style={styles.bottomCount}>{cartProducts.length} items</ThemedText>
                <ThemedText style={styles.bottomNote}>Final price confirmed at counter</ThemedText>
              </View>
              <View style={styles.bottomActions}>
                <Pressable onPress={shareAll} style={styles.shareBtn}>
                  <ThemedText style={styles.shareBtnText}>{'\u2197'} Share</ThemedText>
                </Pressable>
                <Pressable onPress={enquireAll} style={styles.enquireBtn}>
                  <ThemedText style={styles.enquireBtnText}>Enquire on WhatsApp</ThemedText>
                </Pressable>
              </View>
            </View>
          </>
        )}
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
    borderBottomWidth: 1,
    borderBottomColor: '#F0ECE4',
  },
  backBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#F8F6F3',
    alignItems: 'center',
    justifyContent: 'center',
  },
  backText: { fontSize: 18, color: '#1A1A2E' },
  title: { fontSize: 18, fontWeight: '700', color: '#1A1A2E' },

  emptyState: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 8, padding: 32 },
  emptyIcon: { fontSize: 48, marginBottom: 8 },
  emptyTitle: { fontSize: 18, fontWeight: '700', color: '#1A1A2E' },
  emptySub: { fontSize: 13, color: '#6B7280', textAlign: 'center' },
  emptyBtn: {
    backgroundColor: '#23519D',
    borderRadius: BorderRadius.md,
    paddingHorizontal: 24,
    paddingVertical: 12,
    marginTop: 8,
  },
  emptyBtnText: { color: '#FFFFFF', fontWeight: '700', fontSize: 14 },

  list: { padding: 16, gap: 12, paddingBottom: 120 },
  card: {
    flexDirection: 'row',
    backgroundColor: '#FFFFFF',
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: '#E5E1D8',
    padding: 12,
    gap: 12,
    alignItems: 'center',
  },
  cardImg: { width: 72, height: 72, borderRadius: BorderRadius.md },
  cardImgPlaceholder: { backgroundColor: '#F8F6F3' },
  cardInfo: { flex: 1, gap: 2 },
  cardName: { fontSize: 14, fontWeight: '600', color: '#1A1A2E' },
  cardLabel: { fontSize: 12, color: '#6B7280' },
  cardMeta: { fontSize: 11, color: '#9CA3AF', marginTop: 2 },
  removeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#FEF2F2',
    alignItems: 'center',
    justifyContent: 'center',
  },
  removeBtnText: { fontSize: 14, color: '#DC2626' },

  bottomBar: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: '#E5E1D8',
    paddingHorizontal: 16,
    paddingVertical: 14,
    paddingBottom: 32,
  },
  bottomInfo: { marginBottom: 10 },
  bottomCount: { fontSize: 14, fontWeight: '700', color: '#1A1A2E' },
  bottomNote: { fontSize: 11, color: '#9CA3AF' },
  bottomActions: { flexDirection: 'row', gap: 10 },
  shareBtn: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#23519D',
    borderRadius: BorderRadius.md,
    paddingVertical: 12,
    alignItems: 'center',
  },
  shareBtnText: { fontSize: 13, fontWeight: '600', color: '#23519D' },
  enquireBtn: {
    flex: 2,
    backgroundColor: '#16A34A',
    borderRadius: BorderRadius.md,
    paddingVertical: 12,
    alignItems: 'center',
  },
  enquireBtnText: { color: '#FFFFFF', fontSize: 13, fontWeight: '700' },
});
