import { NativeTabs } from 'expo-router/unstable-native-tabs';
import { Colors } from '@/constants/theme';
import { useLang } from '@/store/lang';

export default function AppTabs() {
  const colors = Colors.light;
  const { t } = useLang();

  return (
    <NativeTabs
      backgroundColor={colors.background}
      indicatorColor={colors.background}
      labelStyle={{
        selected: { color: colors.primary, fontWeight: '700', fontSize: 11 },
        default: { color: colors.textSecondary, fontWeight: '500', fontSize: 10 },
      }}
      iconColor={{ selected: colors.primary, default: colors.textSecondary }}>

      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Label>{t('home')}</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon src={require('@/assets/images/tabIcons/home.png')} renderingMode="template" />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="collections">
        <NativeTabs.Trigger.Label>{t('category')}</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon src={require('@/assets/images/tabIcons/collections.png')} renderingMode="template" />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="gold-rate">
        <NativeTabs.Trigger.Label>{t('goldRate')}</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon src={require('@/assets/images/tabIcons/goldrate.png')} renderingMode="template" />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="sip">
        <NativeTabs.Trigger.Label>{t('goldScheme')}</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon src={require('@/assets/images/tabIcons/sip.png')} renderingMode="template" />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="more">
        <NativeTabs.Trigger.Label>{t('account')}</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon src={require('@/assets/images/tabIcons/more.png')} renderingMode="template" />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
