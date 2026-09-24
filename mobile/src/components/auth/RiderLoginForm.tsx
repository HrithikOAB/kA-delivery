import { Ionicons } from '@expo/vector-icons';
import { Link, useRouter } from 'expo-router';
import { useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { ApiError } from '@/api/client';
import { useAuth } from '@/auth/auth-context';
import { ErrorState } from '@/components/ErrorState';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/TextField';
import { Text } from '@/components/ui/Text';
import { colors, radius, spacing } from '@/theme';

export function RiderLoginForm() {
  const router = useRouter();
  const { loginRider, requestRiderOtp } = useAuth();
  const [showEmail, setShowEmail] = useState(false);
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const demo = 'rider@digimess.app';

  const continuePhone = async () => {
    const normalized = phone.replace(/\s/g, '');
    if (normalized.length < 10) {
      setError('Enter a valid 10-digit mobile number');
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const devCode = await requestRiderOtp(`+91${normalized}`);
      router.push({ pathname: '/(auth)/otp', params: { phone: `+91${normalized}`, dev: devCode ?? '' } } as never);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send OTP');
    } finally {
      setBusy(false);
    }
  };

  const submitEmail = async () => {
    setError(null);
    setBusy(true);
    try {
      await loginRider(email.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Login failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.screen}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.wrap}>
      <View style={styles.hero}>
        <View style={styles.logoWrap}>
          <View style={styles.logoCircle}>
            <Ionicons name="bicycle" size={32} color={colors.primary} />
          </View>
          <View style={styles.boltBadge}>
            <Ionicons name="flash" size={12} color={colors.onSecondary} />
          </View>
        </View>

        <View style={styles.hubPill}>
          <View style={styles.hubDot} />
          <Text variant="caption" style={styles.hubText}>Khana Delivery Fleet Hub</Text>
        </View>

        <Text variant="h2" style={styles.title}>Welcome, Partner!</Text>
        <Text variant="bodySmall" style={styles.subtitle}>
          Enter your registered mobile number to access your daily delivery routes and earnings.
        </Text>
      </View>

      {error ? <ErrorState message={error} variant="inline" title="Could not sign in" /> : null}

      {!showEmail ? (
        <View style={styles.card}>
          <Text variant="label" style={styles.fieldLabel}>Mobile Number</Text>
          <View style={styles.phoneRow}>
            <View style={styles.countryCode}>
              <Text style={styles.flag}>🇮🇳</Text>
              <Text style={styles.countryCodeText}>+91</Text>
              <Ionicons name="chevron-down" size={16} color={colors.outline} />
            </View>
            <View style={styles.phoneDivider} />
            <TextInput
              style={styles.phoneInput}
              value={phone}
              onChangeText={setPhone}
              keyboardType="phone-pad"
              placeholder="98765 43210"
              placeholderTextColor={colors.outline}
              maxLength={10}
            />
          </View>

          <View style={styles.otpNote}>
            <Ionicons name="shield-checkmark" size={14} color={colors.secondary} />
            <Text variant="caption" style={styles.otpNoteText}>
              We will send a 6-digit OTP to verify your account
            </Text>
          </View>

          <View style={styles.perksRow}>
            <View style={styles.perk}>
              <View style={[styles.perkIcon, { backgroundColor: colors.secondarySoft }]}>
                <Ionicons name="cash" size={16} color={colors.secondary} />
              </View>
              <Text variant="caption" style={styles.perkTitle}>Instant Payouts</Text>
              <Text variant="caption" style={styles.perkSub}>Daily transfers</Text>
            </View>
            <View style={styles.perk}>
              <View style={[styles.perkIcon, { backgroundColor: colors.primaryFixed }]}>
                <Ionicons name="medkit" size={16} color={colors.primary} />
              </View>
              <Text variant="caption" style={styles.perkTitle}>Accident Cover</Text>
              <Text variant="caption" style={styles.perkSub}>Free for riders</Text>
            </View>
          </View>

          <Pressable style={styles.continueBtn} onPress={continuePhone} disabled={busy}>
            <Text variant="button" style={styles.continueText}>{busy ? 'Sending OTP…' : 'Continue'}</Text>
            <Ionicons name="arrow-forward" size={18} color={colors.onPrimary} />
          </Pressable>
        </View>
      ) : (
        <View style={styles.card}>
          <TextField label="Email" value={email} onChangeText={setEmail} keyboardType="email-address" placeholder={demo} autoCapitalize="none" />
          <TextField label="Password" value={password} onChangeText={setPassword} secureTextEntry placeholder="password123" />
          <Button title="Sign in" onPress={submitEmail} loading={busy} style={{ marginTop: spacing.md }} />
          <Text variant="caption" style={styles.hint}>Demo: {demo} / password123</Text>
        </View>
      )}

      <View style={styles.footer}>
        <Pressable style={styles.helpLink} onPress={() => Linking.openURL('tel:+911800000000')}>
          <Ionicons name="headset" size={14} color={colors.primary} />
          <Text style={styles.helpText}>Trouble signing in? Contact Partner Helpdesk</Text>
        </Pressable>

        <View style={styles.testimonial}>
          <View style={styles.testimonialAvatar}>
            <Text style={styles.testimonialEmoji}>🧑‍🍳</Text>
          </View>
          <View style={styles.testimonialBody}>
            <Text style={styles.testimonialTitle}>Earned ₹2,400 today in 6 hours!</Text>
            <View style={styles.testimonialMeta}>
              <Text style={styles.testimonialSub}>Ramesh K. • Top Fleet Partner</Text>
              <View style={styles.ratingPill}>
                <Ionicons name="star" size={12} color={colors.tertiary} />
                <Text style={styles.ratingText}>4.9</Text>
              </View>
            </View>
          </View>
        </View>

        <Text style={styles.legal}>
          By continuing, you agree to the{' '}
          <Text style={styles.legalLink}>Terms of Service</Text>
          {' '}and{' '}
          <Text style={styles.legalLink}>Privacy Policy</Text>.
        </Text>

        <Pressable onPress={() => setShowEmail((v) => !v)} style={styles.footerAction}>
          <Text style={styles.footerLink}>
            {showEmail ? '← Back to phone login' : 'Sign in with email (demo)'}
          </Text>
        </Pressable>
      </View>
        </View>
      </ScrollView>

      <View style={styles.bottomBar}>
        <Link href="/register-rider" asChild>
          <Pressable
            style={styles.bottomBarLink}
            accessibilityRole="button"
            accessibilityLabel="Apply as a delivery partner"
          >
            <Text style={styles.applyText}>
              New partner? <Text style={styles.applyLinkText}>Apply as a delivery partner</Text>
            </Text>
          </Pressable>
        </Link>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, width: '100%' },
  scroll: { flex: 1, width: '100%' },
  scrollContent: {
    flexGrow: 1,
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  wrap: { width: '100%', maxWidth: 380, paddingTop: spacing.md },
  hero: { alignItems: 'center', marginBottom: spacing.md, width: '100%' },
  logoWrap: { position: 'relative', marginBottom: spacing.sm },
  logoCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: colors.primaryFixed,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: colors.primary,
    shadowOpacity: 0.12,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  boltBadge: {
    position: 'absolute',
    top: 0,
    right: -2,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.secondary,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: colors.surface,
  },
  hubPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: colors.surfaceContainerHigh,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 16,
    marginBottom: spacing.sm,
  },
  hubDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.secondary },
  hubText: { color: colors.textMuted, fontSize: 11, lineHeight: 14, fontWeight: '600' },
  title: { textAlign: 'center', fontSize: 22, lineHeight: 28, letterSpacing: -0.3 },
  subtitle: {
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: 4,
    maxWidth: 280,
    fontSize: 14,
    lineHeight: 20,
  },
  card: {
    width: '100%',
    backgroundColor: colors.surfaceContainerLow,
    borderRadius: radius.lg,
    padding: spacing.md,
    shadowColor: '#000',
    shadowOpacity: 0.04,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  fieldLabel: { marginBottom: 6, fontSize: 12, lineHeight: 16, fontWeight: '500', color: colors.textMuted },
  phoneRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.borderLight,
    paddingHorizontal: spacing.md,
    height: 52,
  },
  countryCode: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  countryCodeText: { fontSize: 14, lineHeight: 20, fontWeight: '500', color: colors.text },
  flag: { fontSize: 16 },
  phoneDivider: { width: 1, height: 24, backgroundColor: colors.borderLight, marginHorizontal: spacing.sm },
  phoneInput: { flex: 1, fontSize: 16, lineHeight: 24, color: colors.text, paddingVertical: 0 },
  otpNote: { flexDirection: 'row', alignItems: 'flex-start', gap: 6, marginTop: spacing.sm },
  otpNoteText: { color: colors.secondary, flex: 1, fontSize: 11, lineHeight: 15, fontWeight: '600' },
  perksRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  perk: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: 6,
    alignItems: 'center',
    justifyContent: 'flex-start',
    minHeight: 88,
  },
  perkIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
  },
  perkTitle: { fontSize: 11, lineHeight: 14, fontWeight: '700', textAlign: 'center' },
  perkSub: { color: colors.textMuted, textAlign: 'center', fontSize: 10, lineHeight: 13 },
  continueBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: colors.primaryContainer,
    borderRadius: radius.lg,
    height: 52,
    marginTop: spacing.md,
  },
  continueText: { color: colors.onPrimary, fontSize: 15, lineHeight: 20, fontWeight: '700' },
  footer: {
    width: '100%',
    marginTop: spacing.md,
    gap: 12,
    alignItems: 'stretch',
  },
  helpLink: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    paddingVertical: 2,
  },
  helpText: {
    color: colors.primary,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '600',
    textAlign: 'center',
    flexShrink: 1,
  },
  testimonial: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.borderLight,
    width: '100%',
  },
  testimonialAvatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surfaceContainerHigh,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    marginTop: 1,
  },
  testimonialEmoji: { fontSize: 20, lineHeight: 22 },
  testimonialBody: { flex: 1, minWidth: 0, gap: 4 },
  testimonialTitle: {
    fontWeight: '700',
    color: colors.text,
    fontSize: 12,
    lineHeight: 16,
  },
  testimonialMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  testimonialSub: {
    flex: 1,
    minWidth: 0,
    color: colors.textMuted,
    fontSize: 10,
    lineHeight: 14,
  },
  ratingPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    backgroundColor: colors.tertiaryFixed,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 8,
    flexShrink: 0,
  },
  ratingText: { fontSize: 10, lineHeight: 12, fontWeight: '700', color: colors.text },
  legal: {
    color: colors.outline,
    textAlign: 'center',
    fontSize: 10,
    lineHeight: 14,
    paddingHorizontal: 8,
  },
  legalLink: { color: colors.primary, fontSize: 10, lineHeight: 14, fontWeight: '600' },
  footerAction: { alignItems: 'center', justifyContent: 'center', paddingVertical: 2, width: '100%' },
  footerLink: { color: colors.primary, fontSize: 11, lineHeight: 15, fontWeight: '600', textAlign: 'center' },
  bottomBar: {
    width: '100%',
    maxWidth: 380,
    alignSelf: 'center',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
    backgroundColor: colors.bg,
    zIndex: 2,
    elevation: 2,
  },
  bottomBarLink: { width: '100%', alignItems: 'center', paddingVertical: spacing.sm },
  applyText: { color: colors.textMuted, fontSize: 11, lineHeight: 16, textAlign: 'center' },
  applyLinkText: { color: colors.primary, fontSize: 11, lineHeight: 16, fontWeight: '700' },
  hint: { textAlign: 'center', marginTop: spacing.md, color: colors.textMuted, fontSize: 12 },
});
