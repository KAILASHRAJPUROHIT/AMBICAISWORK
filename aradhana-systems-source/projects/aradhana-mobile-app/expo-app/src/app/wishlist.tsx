import { FlatList, Image, Pressable, Share, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing, BorderRadius, Shadow } from '@/constants/theme';
import { MASTER } from '@/config/master';
import { getById, imageFor } from '@/services/products';
import { useWishlist } from '@/store/wishlist';

export default function WishlistScreen() {
  const { ids } = useWishlist();
  const router = useRouter();
  const items = [...ids]
    .map((id) => getById(id))
    .filter((p): p is NonNullable<typeof p> => Boolean(p));

  const shareAll = () => {
    if (items.length === 0) return;
    const list = items.map((p) => `\u2022 ${p.categoryName} \u2014 ${p.label}`).join('\n');
    void Share.share({
      message: `My favourites from ${MASTER.displayName}, Boisar:\n\n${list}\n\nView in the Aradhana Jewellers app.`,
    });
  };

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <View style={styles.header}>
          <View style={{ flex: 1 }}>
            <ThemedText style={styles.title}>My Wishlist</ThemedText>
            <ThemedText style={styles.subtitle}>{items.length} saved designs</ThemedText>
          </View>
          {items.length > 0 && (
            <Pressable onPress={shareAll} style={styles.shareBtn}>
              <ThemedText style={styles.shareBtnText}>{'\u2197'} Share All</ThemedText>
            </Pressable>
          )}
        </View>

        <FlatList
          data={items}
          keyExtractor={(p) => p.id}
          numColumns={2}
          columnWrapperStyle={styles.row}
          contentContainerStyle={styles.grid}
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <ThemedText style={styles.emptyIcon}>{'\u2661'}</ThemedText>
              <ThemedText style={styles.emptyTitle}>Nothing saved yet</ThemedText>
              <ThemedText style={styles.emptySub}>Tap {'\u2661'} on any product to keep it here.</ThemedText>
              <Pressable onPress={() => router.push('/collections')} style={styles.emptyBtn}>
                <ThemedText style={styles.emptyBtnText}>Browse Collections</ThemedText>
              </Pressable>
            </View>
          }
          renderItem={({ item }) => {
            const img = imageFor(item);
            return (
              <Pressable
                style={[styles.card, Shadow.sm]}
                onPress={() => router.push(`/product/${item.id}`)}
                accessibilityLabel={`Open ${item.label}`}>
                <View style={styles.imgWrap}>
                  {img ? (
                    <Image source={img} style={styles.img} resizeMode="contain" />
                  ) : (
                    <View style={[styles.img, { backgroundColor: '#F8F6F3' }]} />
                  )}
                </View>
                <View style={styles.cardInfo}>
                  <ThemedText style={styles.cardName} numberOfLines={1}>{item.categoryName}</ThemedText>
                  <ThemedText style={styles.cardMeta} numberOfLines={1}>
                    {item.karat ? `${item.karat}K` : ''}
                    {item.karat && item.weight ? ' \u00B7 ' : ''}
                    {item.weight ? `${item.weight.toFixed(2)}g` : item.label}
                  </ThemedText>
                </View>
              </Pressable>
            );
          }}
        />
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFBF5' },
  safeArea: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    marginBottom: 12,
  },
  title: { fontSize: 24, fontWeight: '700', color: '#1A1A2E', letterSpacing: -0.3 },
  subtitle: { fontSize: 13, color: '#9CA3AF', marginTop: 2 },
  shareBtn: {
    borderWidth: 1,
    borderColor: '#23519D',
    borderRadius: BorderRadius.md,
    paddingHorizontal: 14,
    paddingVertical: 7,
  },
  shareBtnText: { fontSize: 12, fontWeight: '600', color: '#23519D' },
  grid: { paddingHorizontal: 16, gap: 12, paddingBottom: Spacing.six },
  row: { gap: 12 },
  card: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: '#E5E1D8',
    overflow: 'hidden',
  },
  imgWrap: { width: '100%', aspectRatio: 1, backgroundColor: '#FFFBF5' },
  img: { width: '100%', height: '100%' },
  cardInfo: { padding: 10, gap: 2 },
  cardName: { fontSize: 12, fontWeight: '600', color: '#1A1A2E' },
  cardMeta: { fontSize: 10.5, color: '#9CA3AF' },
  emptyState: { alignItems: 'center', paddingVertical: 48, gap: 6 },
  emptyIcon: { fontSize: 48, color: '#E5E1D8', marginBottom: 4 },
  emptyTitle: { fontSize: 18, fontWeight: '700', color: '#1A1A2E' },
  emptySub: { fontSize: 13, color: '#6B7280' },
  emptyBtn: {
    backgroundColor: '#23519D',
    borderRadius: BorderRadius.md,
    paddingHorizontal: 24,
    paddingVertical: 12,
    marginTop: 8,
  },
  emptyBtnText: { color: '#FFFFFF', fontWeight: '700', fontSize: 14 },
});
