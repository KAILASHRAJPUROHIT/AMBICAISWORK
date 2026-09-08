import { useMemo, useState } from 'react';
import { FlatList, Image, Pressable, TextInput, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing, BorderRadius } from '@/constants/theme';
import { imageFor, products, searchProducts } from '@/services/products';

const popularSearches = ['Ring', 'Earring', 'Bangle', 'Jhumka', 'Mangalsutra', 'Necklace', 'Chain', '22K'];

export default function SearchScreen() {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const results = useMemo(() => searchProducts(query), [query]);

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        {/* Search Header */}
        <View style={styles.searchHeader}>
          <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
            <ThemedText style={styles.backText}>{'\u2190'}</ThemedText>
          </Pressable>
          <View style={[styles.searchInputWrap, { borderColor: '#23519D' }]}>
            <ThemedText style={styles.searchIcon}>{'\u2315'}</ThemedText>
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Search rings, earrings, bangles..."
              placeholderTextColor="#9CA3AF"
              autoFocus
              style={styles.searchInput}
            />
            {query.length > 0 && (
              <Pressable onPress={() => setQuery('')} style={styles.clearBtn}>
                <ThemedText style={styles.clearBtnText}>{'\u2715'}</ThemedText>
              </Pressable>
            )}
          </View>
        </View>

        {/* Popular Searches */}
        {!query && (
          <View style={styles.section}>
            <ThemedText style={styles.sectionTitle}>POPULAR SEARCHES</ThemedText>
            <View style={styles.chipWrap}>
              {popularSearches.map((s) => (
                <Pressable key={s} onPress={() => setQuery(s)}>
                  <View style={styles.chip}>
                    <ThemedText style={styles.chipText}>{s}</ThemedText>
                  </View>
                </Pressable>
              ))}
            </View>
          </View>
        )}

        {/* Results */}
        <FlatList
          data={query ? results : products.slice(0, 12)}
          keyExtractor={(p) => p.id}
          numColumns={3}
          columnWrapperStyle={styles.row}
          contentContainerStyle={styles.grid}
          keyboardShouldPersistTaps="handled"
          ListHeaderComponent={
            query && results.length > 0 ? (
              <ThemedText style={styles.resultCount}>{results.length} results for &quot;{query}&quot;</ThemedText>
            ) : null
          }
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <ThemedText style={styles.emptyIcon}>{'\uD83D\uDD0D'}</ThemedText>
              <ThemedText style={styles.emptyTitle}>No matches found</ThemedText>
              <ThemedText style={styles.emptySub}>Try a category like &quot;ring&quot; or &quot;earring&quot;</ThemedText>
            </View>
          }
          renderItem={({ item }) => {
            const img = imageFor(item);
            return (
              <Pressable
                style={styles.cell}
                onPress={() => router.push(`/product/${item.id}`)}
                accessibilityLabel={`Open ${item.categoryName} ${item.label}`}>
                <View style={[styles.thumbWrap, { backgroundColor: '#FFFBF5' }]}>
                  <Image source={img} style={styles.thumb} resizeMode="contain" />
                </View>
                <ThemedText style={styles.cellName} numberOfLines={1}>{item.categoryName}</ThemedText>
                <ThemedText style={styles.cellLabel} numberOfLines={1}>{item.label}</ThemedText>
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

  searchHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 16,
    paddingBottom: 12,
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
    borderWidth: 1,
    borderColor: '#E5E1D8',
  },
  backText: { fontSize: 18, color: '#1A1A2E' },
  searchInputWrap: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1.5,
    borderRadius: BorderRadius.md,
    paddingHorizontal: 12,
    height: 44,
    backgroundColor: '#FFFFFF',
    gap: 8,
  },
  searchIcon: { fontSize: 16, color: '#9CA3AF' },
  searchInput: { flex: 1, fontSize: 15, color: '#1A1A2E', paddingVertical: 0 },
  clearBtn: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#F0ECE4',
    alignItems: 'center',
    justifyContent: 'center',
  },
  clearBtnText: { fontSize: 12, color: '#6B7280' },

  section: { paddingHorizontal: 16, paddingTop: 16, gap: 10 },
  sectionTitle: { fontSize: 11, fontWeight: '700', color: '#9CA3AF', letterSpacing: 1.5 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    backgroundColor: '#FFFFFF',
    borderRadius: BorderRadius.md,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: '#E5E1D8',
  },
  chipText: { fontSize: 13, fontWeight: '500', color: '#1A1A2E' },

  grid: { paddingHorizontal: 16, gap: 12, paddingBottom: Spacing.six, paddingTop: 12 },
  row: { gap: 12 },
  resultCount: { fontSize: 12, color: '#6B7280', marginBottom: 4 },
  cell: { flex: 1 },
  thumbWrap: { width: '100%', aspectRatio: 1, borderRadius: BorderRadius.md, borderWidth: 1, borderColor: '#E5E1D8' },
  thumb: { width: '100%', height: '100%' },
  cellName: { fontSize: 11, fontWeight: '600', color: '#1A1A2E', marginTop: 6 },
  cellLabel: { fontSize: 10, color: '#9CA3AF' },

  emptyState: { alignItems: 'center', paddingVertical: 48, gap: 6 },
  emptyIcon: { fontSize: 36, marginBottom: 4 },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: '#1A1A2E' },
  emptySub: { fontSize: 13, color: '#6B7280' },
});
