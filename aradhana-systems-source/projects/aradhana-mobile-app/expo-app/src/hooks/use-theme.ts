import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';

// Light theme locked for v1 (brand decision pending on dark palette).
export function useTheme() {
  void useColorScheme();
  return Colors.light;
}
