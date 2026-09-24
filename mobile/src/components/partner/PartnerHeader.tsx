import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { BrandLogo } from '@/components/BrandLogo';
import { useFeedback } from '@/components/FeedbackProvider';
import { Text } from '@/components/ui/Text';
import { colors, spacing } from '@/theme';

export function PartnerHeader({
  onProfilePress,
  online,
}: {
  onProfilePress?: () => void;
  online?: boolean;
}) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { unreadCount, openPanel } = useFeedback();

  const goProfile = () => {
    if (onProfilePress) onProfilePress();
    else router.push('/(rider)/profile' as never);
  };

  return (
    <View style={[styles.wrap, { paddingTop: insets.top }]}>
      <View style={styles.row}>
        <View style={styles.brand}>
          <BrandLogo size={32} />
          <View>
            <Text variant="h3" style={styles.brandText}>Khana Delivery</Text>
            <Text variant="caption" style={styles.partnerTag}>PARTNER</Text>
          </View>
        </View>
        <View style={styles.actions}>
          {online != null ? (
            <View style={[styles.onlinePill, online ? styles.onlineOn : styles.onlineOff]}>
              <View style={[styles.onlineDot, { backgroundColor: online ? colors.secondary : colors.textMuted }]} />
              <Text variant="caption" style={{ color: online ? colors.secondary : colors.textMuted, fontWeight: '800', fontSize: 10 }}>
                {online ? 'ONLINE' : 'OFFLINE'}
              </Text>
            </View>
          ) : null}
          <Pressable onPress={openPanel} style={styles.iconBtn} accessibilityRole="button" accessibilityLabel="Notifications">
            <Ionicons name="notifications-outline" size={20} color={colors.text} />
            {unreadCount > 0 ? (
              <View style={styles.badge}>
                <Text variant="caption" style={styles.badgeText}>{unreadCount > 9 ? '9+' : unreadCount}</Text>
              </View>
            ) : null}
          </Pressable>
          <Pressable onPress={goProfile} style={styles.avatar} accessibilityRole="button" accessibilityLabel="Profile">
            <Text style={styles.avatarIcon}>👤</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: 'rgba(252, 248, 255, 0.92)',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderLight,
  },
  row: {
    height: 56,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
  },
  brand: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  brandText: { color: colors.text, fontWeight: '700', lineHeight: 20 },
  partnerTag: { color: colors.textMuted, fontSize: 9, fontWeight: '800', letterSpacing: 1.2, marginTop: -2 },
  actions: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  onlinePill: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 20, borderWidth: 1 },
  onlineOn: { backgroundColor: colors.successContainer, borderColor: colors.secondary },
  onlineOff: { backgroundColor: colors.surfaceContainerHigh, borderColor: colors.borderLight },
  onlineDot: { width: 6, height: 6, borderRadius: 3 },
  iconBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surfaceContainerHigh,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badge: {
    position: 'absolute',
    top: -2,
    right: -2,
    minWidth: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: colors.error,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 3,
  },
  badgeText: { color: colors.onPrimary, fontSize: 10, fontWeight: '800', lineHeight: 12 },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarIcon: { fontSize: 14 },
});
