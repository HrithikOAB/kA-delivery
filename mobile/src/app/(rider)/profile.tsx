import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { api, ApiError } from '@/api/client';
import type { RiderProfileDetail, WalletDetails } from '@/api/types';
import { useAuth } from '@/auth/auth-context';
import { ErrorState } from '@/components/ErrorState';
import { useFeedback } from '@/components/FeedbackProvider';
import { Loading } from '@/components/Loading';
import { ProfileMenuItem } from '@/components/ProfileMenuItem';
import { PartnerCard, PartnerHeader } from '@/components/partner';
import { Avatar } from '@/components/ui/Avatar';
import { Button } from '@/components/ui/Button';
import { Text } from '@/components/ui/Text';
import { useTabBarHeight } from '@/hooks/useTabBarStyle';
import { colors, money, spacing } from '@/theme';

const APP_VERSION = Constants.expoConfig?.version ?? '1.0.0';
const LANGUAGE_OPTIONS = ['English', 'English / ಕನ್ನಡ', 'हिन्दी', 'English / Hindi'] as const;

function SectionTitle({ children }: { children: string }) {
  return <Text variant="caption" style={styles.sectionTitle}>{children}</Text>;
}

function VerifiedBadge({ label = 'Verified' }: { label?: string }) {
  return (
    <View style={styles.verifiedPill}>
      <Ionicons name="checkmark-circle" size={12} color={colors.secondary} />
      <Text variant="caption" style={styles.verifiedText}>{label}</Text>
    </View>
  );
}

function vehicleIcon(type: string): keyof typeof Ionicons.glyphMap {
  const key = type.toLowerCase();
  if (key === 'car') return 'car';
  if (key === 'van') return 'bus';
  return 'bicycle';
}

export default function RiderProfile() {
  const { logout } = useAuth();
  const router = useRouter();
  const feedback = useFeedback();
  const tabBarHeight = useTabBarHeight();
  const [profile, setProfile] = useState<RiderProfileDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatingLanguage, setUpdatingLanguage] = useState(false);
  const [wallet, setWallet] = useState<WalletDetails | null>(null);

  const load = useCallback(async () => {
    try {
      const [data, walletData] = await Promise.all([
        api.riderProfile(),
        api.riderWallet().catch(() => null),
      ]);
      setProfile(data);
      setWallet(walletData);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load profile');
    }
  }, []);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const changeLanguage = () => {
    Alert.alert(
      'App Language',
      'Choose your preferred language for the partner app.',
      [
        ...LANGUAGE_OPTIONS.map((lang) => ({
          text: lang,
          onPress: () => {
            void (async () => {
              setUpdatingLanguage(true);
              try {
                const updated = await api.updateRiderProfile({ app_language: lang });
                setProfile(updated);
                feedback.success('Language preference updated.', 'Saved');
              } catch (err) {
                feedback.error(
                  err instanceof ApiError ? err.message : 'Could not update language',
                  'Update failed',
                );
              } finally {
                setUpdatingLanguage(false);
              }
            })();
          },
        })),
        { text: 'Cancel', style: 'cancel' },
      ],
    );
  };

  if (!profile && !error) {
    return (
      <View style={styles.screen}>
        <PartnerHeader />
        <Loading label="Loading profile…" />
      </View>
    );
  }

  if (!profile && error) {
    return (
      <View style={styles.screen}>
        <PartnerHeader />
        <ErrorState message={error} onRetry={load} variant="page" />
      </View>
    );
  }

  if (!profile) return null;

  const verified = profile.approval_status === 'approved';
  const tripLabel = profile.trip_count >= 540 ? `${profile.trip_count}+ trips` : `${profile.trip_count} trips`;
  const ratingLabel = `${profile.rating.toFixed(2)} (${tripLabel})`;

  return (
    <View style={styles.screen}>
      <PartnerHeader online={profile.is_online} />
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: tabBarHeight + 16 }]}>
        <PartnerCard variant="container" style={styles.heroCard}>
          <Pressable
            style={styles.editBtn}
            onPress={() => feedback.info('Profile editing will be available soon.', 'Coming soon')}
            accessibilityRole="button"
            accessibilityLabel="Edit profile"
          >
            <Ionicons name="create-outline" size={16} color={colors.primary} />
            <Text variant="caption" style={styles.editText}>Edit</Text>
          </Pressable>

          <View style={styles.avatarWrap}>
            <Avatar name={profile.full_name} size={88} />
            {verified ? (
              <View style={styles.avatarBadge}>
                <Ionicons name="shield-checkmark" size={14} color={colors.onSecondary} />
              </View>
            ) : null}
          </View>

          <Text variant="h2" style={styles.heroName}>{profile.full_name}</Text>
          <Text variant="bodySmall" style={styles.partnerCode}>{profile.partner_code}</Text>

          <View style={styles.ratingPill}>
            <Ionicons name="star" size={14} color={colors.tertiary} />
            <Text variant="caption" style={styles.ratingText}>{ratingLabel}</Text>
          </View>
        </PartnerCard>

        <PartnerCard variant="lowest" style={styles.fleetCard}>
          <View style={styles.fleetRow}>
            <View style={styles.fleetIcon}>
              <Ionicons name="trophy" size={20} color={colors.tertiary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text variant="caption" style={styles.fleetLabel}>FLEET STATUS</Text>
              <Text variant="label">{profile.fleet_tier}</Text>
            </View>
            <View style={styles.surgePill}>
              <Ionicons name="flash" size={12} color={colors.onTertiaryFixed} />
              <Text variant="caption" style={styles.surgeText}>
                +{profile.surge_priority_pct}% Surge Priority
              </Text>
            </View>
          </View>
        </PartnerCard>

        <View style={styles.sectionHeaderRow}>
          <SectionTitle>PARTNER DETAILS</SectionTitle>
          <View style={styles.primaryPill}>
            <View style={styles.primaryDot} />
            <Text variant="caption" style={{ color: colors.secondary, fontWeight: '700' }}>Primary Account</Text>
          </View>
        </View>
        <PartnerCard variant="container">
          <View style={styles.detailRow}>
            <View style={styles.detailIcon}>
              <Ionicons name="call" size={18} color={colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text variant="caption" style={styles.detailLabel}>Phone</Text>
              <Text variant="bodySmall">{profile.phone ?? '—'}</Text>
            </View>
            {profile.phone_verified ? <VerifiedBadge /> : null}
          </View>

          <View style={styles.detailDivider} />

          <View style={styles.detailRow}>
            <View style={styles.detailIcon}>
              <Ionicons name="mail" size={18} color={colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text variant="caption" style={styles.detailLabel}>Email</Text>
              <Text variant="bodySmall">{profile.email ?? '—'}</Text>
            </View>
          </View>

          <View style={styles.detailDivider} />

          <View style={styles.detailRow}>
            <View style={styles.detailIcon}>
              <Ionicons name="location" size={18} color={colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text variant="caption" style={styles.detailLabel}>Operating Hub</Text>
              <Text variant="bodySmall">{profile.operating_hub}</Text>
            </View>
          </View>
        </PartnerCard>

        <View style={styles.sectionHeaderRow}>
          <SectionTitle>REGISTERED VEHICLE</SectionTitle>
          <View style={styles.vehicleTypePill}>
            <Text variant="caption" style={{ color: colors.primary, fontWeight: '700' }}>{profile.vehicle_type_label}</Text>
          </View>
        </View>

        <PartnerCard variant="lowest" style={styles.vehicleCard}>
          <View style={styles.vehicleRow}>
            <View style={styles.vehicleIcon}>
              <Ionicons name={vehicleIcon(profile.vehicle_type)} size={22} color={colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text variant="label">{profile.vehicle_model}</Text>
              <Text variant="caption" style={{ color: colors.textMuted }}>
                {profile.vehicle_fuel_type} · {profile.vehicle_cargo_type}
              </Text>
            </View>
          </View>

          <View style={styles.plateRow}>
            <View style={styles.plateBadge}>
              <Text variant="label" style={styles.plateText}>{profile.vehicle_number}</Text>
            </View>
            <VerifiedBadge label={profile.rc_status_label} />
          </View>
        </PartnerCard>

        <PartnerCard variant="container" style={styles.menuCard}>
          <ProfileMenuItem
            icon="wallet"
            label="My Wallet"
            subtitle={wallet
              ? `${money(wallet.available_balance_cents)} available • Withdraw instantly`
              : 'View balance, withdraw & transactions'}
            highlighted
            onPress={() => router.push('/(rider)/wallet' as never)}
          />
          <ProfileMenuItem
            icon="document-text"
            label="Documents & Licenses"
            subtitle={profile.documents_summary}
            onPress={() => router.push('/(rider)/documents' as never)}
          />
          <ProfileMenuItem
            icon="card"
            label="Bank & Payout Settings"
            subtitle={profile.bank_summary || 'Link your bank account for weekly payouts'}
            onPress={() => router.push('/(rider)/wallet/withdraw' as never)}
          />
          <ProfileMenuItem
            icon="headset"
            label="Help & Partner Support"
            subtitle="24/7 partner support center"
            onPress={() => router.push('/(rider)/help' as never)}
          />
          <View style={styles.languageRow}>
            <View style={[styles.languageIcon, { backgroundColor: colors.primarySoft }]}>
              <Ionicons name="language" size={20} color={colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text variant="body">App Language</Text>
              <Text variant="caption">{profile.app_language}</Text>
            </View>
            <Pressable
              onPress={changeLanguage}
              disabled={updatingLanguage}
              style={({ pressed }) => [styles.changeBtn, pressed && { opacity: 0.7 }]}
              accessibilityRole="button"
              accessibilityLabel="Change app language"
            >
              <Text variant="caption" style={styles.changeText}>Change</Text>
            </Pressable>
          </View>
        </PartnerCard>

        <Button title="Log Out" variant="ghost" onPress={logout} style={styles.logoutBtn} />

        <Text variant="caption" style={styles.footer}>
          Khana Delivery Partner App v4.18.2 (Build 4910) ● All Systems Nominal
        </Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, gap: spacing.md },
  sectionHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: spacing.xs },
  primaryPill: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  primaryDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.secondary },
  vehicleTypePill: { backgroundColor: colors.primaryFixed, paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: 12 },
  sectionTitle: {
    color: colors.textMuted,
    fontWeight: '800',
    letterSpacing: 1.2,
    marginBottom: 0,
  },
  heroCard: { alignItems: 'center', paddingTop: spacing.xl },
  editBtn: {
    position: 'absolute',
    top: spacing.md,
    right: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.surfaceContainerHigh,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderRadius: 20,
  },
  editText: { color: colors.primary, fontWeight: '700' },
  avatarWrap: { position: 'relative' },
  avatarBadge: {
    position: 'absolute',
    right: -2,
    bottom: -2,
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.secondary,
    borderWidth: 2,
    borderColor: colors.surfaceContainer,
    alignItems: 'center',
    justifyContent: 'center',
  },
  heroName: { marginTop: spacing.md, textAlign: 'center' },
  partnerCode: { color: colors.textMuted, marginTop: spacing.xs },
  ratingPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.sm,
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: 20,
  },
  ratingText: { fontWeight: '700', color: colors.text },
  fleetCard: { padding: spacing.md },
  fleetRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  fleetIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.tertiaryFixed,
    alignItems: 'center',
    justifyContent: 'center',
  },
  fleetLabel: { color: colors.textMuted, fontWeight: '700', letterSpacing: 0.5, marginBottom: 2 },
  surgePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.secondaryFixed,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderRadius: 10,
  },
  surgeText: { color: colors.onSecondaryContainer, fontWeight: '800', fontSize: 10 },
  detailRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  detailIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.primaryFixed,
    alignItems: 'center',
    justifyContent: 'center',
  },
  detailLabel: { color: colors.textMuted, fontWeight: '700', marginBottom: 2 },
  detailDivider: { height: 1, backgroundColor: colors.borderLight, marginVertical: spacing.md },
  verifiedPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.successContainer,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: 12,
  },
  verifiedText: { color: colors.secondary, fontWeight: '700' },
  vehicleCard: { marginTop: spacing.xs },
  vehicleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  vehicleIcon: {
    width: 48,
    height: 48,
    borderRadius: 14,
    backgroundColor: colors.primaryFixed,
    alignItems: 'center',
    justifyContent: 'center',
  },
  plateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  plateBadge: {
    backgroundColor: colors.surfaceContainerHigh,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  plateText: { letterSpacing: 1 },
  menuCard: { paddingVertical: spacing.sm, paddingHorizontal: spacing.md },
  languageRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
  },
  languageIcon: {
    width: 40,
    height: 40,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  changeBtn: {
    backgroundColor: colors.primaryFixed,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: 20,
  },
  changeText: { color: colors.primary, fontWeight: '800' },
  logoutBtn: { marginTop: spacing.sm },
  footer: { textAlign: 'center', color: colors.textLight, marginTop: spacing.sm, marginBottom: spacing.md },
});
