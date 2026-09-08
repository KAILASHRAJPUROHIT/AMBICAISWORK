import { useMemo, useState } from 'react';
import { FlatList, Image, Pressable, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing, BorderRadius, Shadow } from '@/constants/theme';
import { byCategory, categories, imageFor } from '@/services/products';

export default function CollectionsScreen() {
  const router = useRouter();
  const cats = useMemo(() => categories(), []);
  const [active, setActive] = useState('all');
  const items = byCategory(active);

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <View style={styles.header}>
          <ThemedText style={styles.title}>Collections</ThemedText>
          <ThemedText style={styles.subtitle}>{items.length} designs</ThemedText>
        </View>

        <FlatList
          data={[{ key: 'all', name: 'All', count: items.length }, ...cats]}
          horizontal
          showsHorizontalScrollIndicator={false}
          keyExtractor={(c) => c.key}
          style={styles.chipsRow}
          contentContainerStyle={styles.chips}
          renderItem={({ item }) => (
            <Pressable onPress={() => setActive(item.key)} accessibilityLabel={item.name}>
              <View style={[styles.chip, active === item.key && styles.chipActive]}>
                <ThemedText style={[styles.chipText, active === item.key && styles.chipTextActive]}>
                  {item.name} ({item.count})
                </ThemedText>
              </View>
            </Pressable>
          )}
        />

        <FlatList
          data={items}
          numColumns={2}
          columnWrapperStyle={styles.column}
          contentContainerStyle={styles.grid}
          keyExtractor={(p) => p.id}
          showsVerticalScrollIndicator={false}
          renderItem={({ item }) => (
            <Pressable
              style={[styles.card, Shadow.sm]}
              onPress={() => router.push(`/product/${item.id}`)}
              accessibilityLabel={`${item.categoryName} ${item.label}`}>
              <View style={styles.imgWrap}>
                <Image source={imageFor(item)} style={styles.img} resizeMode="cover" />
                <View style={styles.imgOverlay}>
                  <ThemedText style={styles.imgOverlayText}>{item.karat ? `${item.karat}K` : ''}</ThemedText>
                </View>
              </View>
              <View style={styles.cardInfo}>
                <ThemedText style={styles.cardName} numberOfLines={1}>{item.categoryName}</ThemedText>
                <ThemedText style={styles.cardMeta} numberOfLines={1}>
                  {[item.weight ? `${item.weight.toFixed(2)}g` : null].filter(Boolean).join(' \u00B7 ')}
                </ThemedText>
              </View>
            </Pressable>
          )}
        />
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFBF5' },
  safeArea: { flex: 1 },
  header: { paddingHorizontal: 16, marginBottom: 12 },
  title: { fontSize: 24, fontWeight: '700', color: '#1A1A2E', letterSpacing: -0.3 },
  subtitle: { fontSize: 13, color: '#C9A84C', marginTop: 2, fontWeight: '500' },
  chipsRow: { height: 44, flexGrow: 0 },
  chips: { paddingHorizontal: 16, gap: 8, alignItems: 'center' },
  chip: {
    borderWidth: 1.5,
    borderColor: '#E5E1D8',
    borderRadius: BorderRadius.full,
    paddingHorizontal: 16,
    paddingVertical: 7,
    backgroundColor: '#FFFFFF',
  },
  chipActive: { backgroundColor: '#23519D', borderColor: '#23519D' },
  chipText: { fontSize: 12, fontWeight: '500', color: '#1A1A2E' },
  chipTextActive: { color: '#FFFFFF', fontWeight: '700' },
  grid: { paddingHorizontal: 16, gap: 14, paddingBottom: Spacing.six, paddingTop: 8 },
  column: { gap: 14 },
  card: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: '#E8D9A8',
    overflow: 'hidden',
  },
  imgWrap: {
    width: '100%',
    aspectRatio: 0.8,
    backgroundColor: '#FDF8ED',
  },
  img: { width: '100%', height: '100%' },
  imgOverlay: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: 'rgba(35,81,157,0.9)',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  imgOverlayText: { color: '#FFFFFF', fontSize: 10, fontWeight: '700', letterSpacing: 0.5 },
  cardInfo: { padding: 12, gap: 3 },
  cardName: { fontSize: 13, fontWeight: '600', color: '#1A1A2E' },
  cardMeta: { fontSize: 11, color: '#C9A84C', fontWeight: '500' },
});
