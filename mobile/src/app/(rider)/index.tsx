/** Partner home — online toggle, earnings stats, active delivery, offers. */
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { Image } from 'expo-image';
import { api, ApiError } from '@/api/client';
import type { Batch, Offer, RiderDashboard, UserOut } from '@/api/types';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { FeedbackBanner } from '@/components/FeedbackBanner';
import { useFeedback } from '@/components/FeedbackProvider';
import { Loading } from '@/components/Loading';
import { OnlineStatusBanner, PartnerCard, PartnerHeader } from '@/components/partner';
import { useRiderLocationStatus } from '@/components/RiderLiveLocation';
import { Button } from '@/components/ui/Button';
import { Text } from '@/components/ui/Text';
import { config } from '@/config';
import { useTabBarHeight } from '@/hooks/useTabBarStyle';
import { formatRelativeAgo } from '@/lib/format-time';
import { colors, formatStatus, money, spacing, statusColor } from '@/theme';

function hasPendingStops(batch: Batch | null) {
  return !!batch?.stops.some((s) => s.status !== 'delivered');
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

function OfferCountdown(_props: { expiresAt: string }) {
  return (
    <View style={styles.countdownPill}>
      <Ionicons name="flash" size={16} color={colors.tertiary} />
      <Text variant="caption" style={{ color: colors.onTertiaryFixed, fontWeight: '700' }}>
        New offer
      </Text>
    </View>
  );
}

export default function RiderDashboard() {
  const tabBarHeight = useTabBarHeight();
  const router = useRouter();
  const [me, setMe] = useState<UserOut | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [earningsToday, setEarningsToday] = useState(0);
  const [deliveriesToday, setDeliveriesToday] = useState(0);
  const [dashboard, setDashboard] = useState<RiderDashboard | null>(null);
  const [recentLines, setRecentLines] = useState<{ order_id: number; amount_cents: number; delivered_at: string | null }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const seenOfferId = useRef<number | null>(null);
  const statsWarnedRef = useRef(false);

  const online = me?.rider_profile?.is_online ?? false;
  const approved = me?.rider_profile?.approval_status === 'approved';
  const activeBatch = useMemo(() => (hasPendingStops(batch) ? batch : null), [batch]);
  const lastCompleted = dashboard?.last_completed ?? null;
  const surgeHotspot = dashboard?.surge_hotspot ?? null;
  const topHotspot = dashboard?.hotspots?.[0] ?? null;
  const quest = dashboard?.quest ?? dashboard?.incentive_quest;
  const pctVsYesterday = dashboard?.earnings_pct_vs_yesterday ?? 0;
  const onlineHours = dashboard?.online_hours_label ?? "—";
  const tipsToday = dashboard?.tips_cents ?? 0;
  const questPct = quest ? Math.min(100, (quest.completed_deliveries / quest.target_deliveries) * 100) : 0;
  const questRemaining = quest ? Math.max(0, quest.target_deliveries - quest.completed_deliveries) : 0;
  const { status: locStatus, lastError: locError } = useRiderLocationStatus();
  const feedback = useFeedback();

  const load = useCallback(async () => {
    try {
      const u = await api.me();
      setMe(u);
      if (u.rider_profile?.approval_status === 'approved') {
        const [o, b] = await Promise.all([api.riderOffers(), api.riderActive()]);
        setOffers(o);
        setBatch(b);
        if (o.length > 0 && !hasPendingStops(b) && seenOfferId.current !== o[0].id) {
          seenOfferId.current = o[0].id;
          feedback.info(`New delivery offer from ${o[0].mess_name ?? 'kitchen'}`, 'New dispatch');
          router.push(`/(rider)/request/${o[0].id}` as never);
        }
        try {
          const [e, d] = await Promise.all([api.riderEarnings(), api.riderDashboard()]);
          setEarningsToday(e.summary.today_earned_cents ?? e.summary.total_earned_cents);
          setDeliveriesToday(e.summary.today_deliveries ?? e.summary.total_deliveries);
          setRecentLines(e.lines.slice(0, 3));
          setDashboard(d);
          statsWarnedRef.current = false;
        } catch {
          setEarningsToday(0);
          setDeliveriesToday(0);
          setRecentLines([]);
          setDashboard(null);
          if (!statsWarnedRef.current) {
            statsWarnedRef.current = true;
            feedback.warning("Could not load today's stats", 'Partial load');
          }
        }
      }
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load dashboard');
    } finally {
      setRefreshing(false);
    }
  }, [router, feedback]);

  useFocusEffect(useCallback(() => {
    void load();
    timer.current = setInterval(load, config.locationIntervalMs);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [load]));

  const wrap = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed');
      await load();
    } finally {
      setBusy(false);
    }
  };

  const toggleOnline = (value: boolean) => wrap(() => value ? api.riderOnline() : api.riderOffline());

  if (!me) {
    return (
      <View style={styles.screen}>
        <PartnerHeader online={online} />
        <Loading label="Loading dashboard…" />
      </View>
    );
  }

  const riderName = me.full_name?.split(' ')[0] ?? 'Partner';

  return (
    <View style={styles.screen}>
      <PartnerHeader online={online} />
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: tabBarHeight + 16 }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(); }} tintColor={colors.primary} />}
      >
        {error ? <ErrorState message={error} variant="inline" /> : null}

        {!approved ? (
          <PartnerCard>
            <Text variant="h3">Verification: {me.rider_profile?.approval_status ?? 'draft'}</Text>
            {me.rider_profile?.approval_status === 'needs_correction' && me.rider_profile?.correction_reason ? (
              <FeedbackBanner severity="warning" title="Action needed" message={me.rider_profile.correction_reason} style={{ marginTop: spacing.sm }} />
            ) : (
              <Text variant="bodySmall" style={{ color: colors.textMuted, marginTop: spacing.sm }}>
                Submit your documents to get verified and start delivering.
              </Text>
            )}
            <Button
              title="Manage documents & verification"
              variant="secondary"
              onPress={() => router.push('/(rider)/documents' as never)}
              style={{ marginTop: spacing.md }}
            />
          </PartnerCard>
        ) : (
          <>
            <View style={styles.greetingRow}>
              <View style={{ flex: 1 }}>
                <Text variant="h1" style={styles.greetingTitle}>{greeting()}, {riderName}! ⚡</Text>
                <Text variant="bodySmall" style={{ color: colors.textMuted, marginTop: spacing.xs }}>
                  {online ? 'Ready for the dinner rush shift?' : 'Go online to start accepting orders.'}
                </Text>
              </View>
              {online ? (
                <View style={styles.greetingOnlinePill}>
                  <View style={styles.greetingOnlineDot} />
                  <Text variant="caption" style={styles.greetingOnlineText}>ONLINE</Text>
                </View>
              ) : null}
            </View>

            <OnlineStatusBanner online={online} onToggle={toggleOnline} disabled={busy} />

            {locStatus === 'denied' ? (
              <FeedbackBanner severity="warning" title="Location access needed" message="Enable location so customers can track your delivery." />
            ) : null}
            {locError ? (
              <FeedbackBanner severity="error" message={locError} title="Location update failed" />
            ) : null}
            {online && locStatus === 'tracking' ? (
              <FeedbackBanner severity="success" title="Live location on" message="Customers and ops can track you in real time." />
            ) : null}
            {online && (locStatus === 'idle' || locStatus === 'requesting') ? (
              <FeedbackBanner severity="info" title="Waiting for GPS" message="Allow location and keep the app open so your position is shared." />
            ) : null}

            <PartnerCard variant="lowest" style={styles.earningsCard}>
              <View style={styles.earningsHeader}>
                <View style={styles.earningsTitleRow}>
                  <Ionicons name="wallet" size={18} color={colors.primary} />
                  <Text variant="caption" style={styles.earningsLabel}>TODAY'S EARNINGS</Text>
                </View>
                <Pressable style={styles.earningsChevron} onPress={() => router.push('/(rider)/earnings' as never)}>
                  <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
                </Pressable>
              </View>
              <View style={styles.earningsAmountRow}>
                <Text variant="display" style={styles.earningsAmount}>{money(earningsToday)}</Text>
                {pctVsYesterday > 0 ? (
                  <View style={styles.growthPill}>
                    <Ionicons name="trending-up" size={12} color={colors.secondary} />
                    <Text variant="caption" style={{ color: colors.secondary, fontWeight: '700' }}>+{Math.round(pctVsYesterday)}%</Text>
                  </View>
                ) : null}
              </View>
              <View style={styles.metricsRow}>
                <View style={styles.metricCol}>
                  <View style={[styles.metricIcon, { backgroundColor: colors.primaryFixed }]}>
                    <Ionicons name="cube" size={16} color={colors.primary} />
                  </View>
                  <Text variant="caption" style={{ color: colors.textMuted }}>Deliveries</Text>
                  <Text variant="label">{deliveriesToday}</Text>
                </View>
                <View style={styles.metricCol}>
                  <View style={[styles.metricIcon, { backgroundColor: colors.tertiaryFixed }]}>
                    <Ionicons name="time" size={16} color={colors.tertiary} />
                  </View>
                  <Text variant="caption" style={{ color: colors.textMuted }}>Online Time</Text>
                  <Text variant="label">{onlineHours}</Text>
                </View>
                <View style={[styles.metricCol, { borderRightWidth: 0 }]}>
                  <View style={[styles.metricIcon, { backgroundColor: colors.secondaryFixed }]}>
                    <Ionicons name="heart" size={16} color={colors.secondary} />
                  </View>
                  <Text variant="caption" style={{ color: colors.textMuted }}>Tips</Text>
                  <Text variant="label">{tipsToday > 0 ? money(tipsToday) : '—'}</Text>
                </View>
              </View>
            </PartnerCard>

            {quest ? (
              <PartnerCard variant="lowest" style={styles.questCard}>
                <View style={styles.questHeader}>
                  <View style={styles.questBadge}>
                    <Ionicons name="flame" size={14} color={colors.tertiary} />
                    <Text variant="caption" style={{ fontWeight: '700' }}>Peak Dinner Bonus</Text>
                  </View>
                  <View style={styles.bonusPill}>
                    <Text variant="caption" style={{ color: colors.onTertiaryFixed, fontWeight: '700' }}>
                      +{money(quest.bonus_cents)}
                    </Text>
                  </View>
                </View>
                <View style={styles.questProgressRow}>
                  <View style={{ flex: 1 }}>
                    <Text variant="label" style={{ fontWeight: '700' }}>Peak Dinner Bonus</Text>
                    <Text variant="caption" style={{ color: colors.textMuted, marginTop: 2 }}>
                      {questRemaining > 0 ? `Complete ${questRemaining} more before 11:00 PM` : 'Bonus unlocked!'}
                    </Text>
                  </View>
                  <Text variant="h2" style={{ color: colors.secondary, fontWeight: '800' }}>{Math.round(questPct)}%</Text>
                </View>
                <View style={styles.progressTrack}>
                  <View style={[styles.progressFill, { width: `${questPct}%` }]} />
                </View>
                <View style={styles.questFooter}>
                  <Text variant="caption" style={{ color: colors.textMuted }}>{quest.completed_deliveries} completed</Text>
                  <Text variant="caption" style={{ color: colors.textMuted }}>Goal: {quest.target_deliveries} orders</Text>
                </View>
              </PartnerCard>
            ) : null}

            {(surgeHotspot || (topHotspot && topHotspot.demand_level !== 'normal')) ? (
              <PartnerCard style={styles.surgeCard}>
                <View style={styles.surgeTop}>
                  <View style={styles.surgePill}>
                    <Text variant="caption" style={{ color: colors.onPrimary, fontWeight: '700' }}>SURGE ALERT</Text>
                  </View>
                  <View style={styles.surgeMultiplier}>
                    <Text variant="caption" style={{ color: colors.onPrimary, fontWeight: '700' }}>{(surgeHotspot?.multiplier ?? topHotspot?.multiplier ?? 1.2)}x Surge</Text>
                  </View>
                </View>
                <Text variant="h3" style={{ color: colors.onPrimary, marginTop: spacing.sm }}>
                  {surgeHotspot?.title ?? `High demand in ${topHotspot?.mess_name ?? 'your zone'}`}
                </Text>
                <Text variant="caption" style={{ color: 'rgba(255,255,255,0.85)', marginTop: 4 }}>
                  {surgeHotspot?.subtitle ?? 'Head toward hotspot for guaranteed order requests under 3 mins.'}
                </Text>
                <View style={styles.surgeMap}>
                  <Image
                    source={{ uri: 'https://lh3.googleusercontent.com/aida-public/AB6AXuCMvO1mCyBfQ9inhfitD1rkA-NM9QtGJwRnCY02exJwaUuD_CfNo2T8fvqgSlAsnrDm4ARmNQpr9pDyWoBGpGqcAEo2h0wsKCVmxyySrKNKEal25BEI6pnl27SjgZMdoxVhHhyjMjOelWLnKR0F4v9tHfM0aj5hKypApoXCtpod-nUDCOTgwczs4POJsEkV6XFYp2OaU47u1EQXh2SOGmtKskvjlG2J4_nbIsXGY0Gx_2ByWPKPoYee' }}
                    style={StyleSheet.absoluteFill}
                    contentFit="cover"
                  />
                  <View style={styles.surgeMapGradient} />
                  <View style={styles.surgeMapOverlay}>
                    <Ionicons name="location" size={18} color={colors.primary} />
                    <Text variant="caption" style={{ color: colors.text, flex: 1 }}>
                      {surgeHotspot?.map_label ?? `${topHotspot?.open_batches ?? 0} open batches nearby`}
                    </Text>
                    <Pressable style={styles.navigateBtn}>
                      <Text variant="caption" style={{ color: colors.onPrimary, fontWeight: '700' }}>Navigate</Text>
                    </Pressable>
                  </View>
                </View>
              </PartnerCard>
            ) : null}

            {activeBatch ? (() => {
              const pending = activeBatch.stops.filter((s) => s.status !== 'delivered');
              const next = pending[0];
              const batchLabel = formatStatus(activeBatch.status);
              const stopLabel = next ? formatStatus(next.status) : batchLabel;
              const isPickup = activeBatch.status === 'assigned';
              return (
                <PartnerCard variant="container" style={styles.activeCard}>
                  <View style={styles.activeTop}>
                    <View style={styles.activeBadge}>
                      <View style={styles.activeDot} />
                      <Text variant="caption" style={{ color: colors.secondary, fontWeight: '700' }}>ACTIVE DELIVERY</Text>
                    </View>
                    <View style={[styles.statusPill, { backgroundColor: statusColor(next?.status ?? activeBatch.status) + '22' }]}>
                      <Text variant="caption" style={{ color: statusColor(next?.status ?? activeBatch.status), fontWeight: '700' }}>{stopLabel}</Text>
                    </View>
                  </View>
                  <Text variant="h3" style={{ marginTop: spacing.sm }}>{activeBatch.mess_name}</Text>
                  {next ? (
                    <View style={styles.nextStopRow}>
                      <View style={styles.nextStopIcon}><Ionicons name="navigate" size={16} color={colors.primary} /></View>
                      <View style={{ flex: 1 }}>
                        <Text variant="label">Next · Order #{next.order_id}</Text>
                        <Text variant="caption" style={{ color: colors.textMuted }}>{next.customer_name}</Text>
                      </View>
                    </View>
                  ) : null}
                  <Text variant="bodySmall" style={{ color: colors.textMuted, marginTop: spacing.sm }}>
                    {isPickup
                      ? 'Just received — collect order from kitchen'
                      : `${pending.length === 1 ? '1 stop remaining' : `${pending.length} stops remaining`} · ${batchLabel}`}
                  </Text>
                  <Button
                    title={isPickup ? 'Go to Pickup' : 'Continue Delivery'}
                    onPress={() => router.push((isPickup ? '/(rider)/pickup' : '/(rider)/active') as never)}
                    style={{ marginTop: spacing.md }}
                  />
                </PartnerCard>
              );
            })() : null}

            {offers.map((offer) => (
              <Pressable key={offer.id} onPress={() => router.push(`/(rider)/request/${offer.id}` as never)}>
                <PartnerCard variant="container">
                  <View style={styles.offerTop}>
                    <View style={styles.dispatchPill}>
                      <Ionicons name="flash" size={14} color={colors.primary} />
                      <Text variant="caption" style={{ color: colors.text, fontWeight: '600' }}>New Instant Dispatch</Text>
                    </View>
                    {offer.expires_at ? <OfferCountdown expiresAt={offer.expires_at} /> : null}
                  </View>
                  <Text variant="h2" style={{ color: colors.primary, marginTop: spacing.sm }}>
                    {money(offer.estimated_earning_cents)} estimated
                  </Text>
                  <Text variant="bodySmall" style={{ color: colors.textMuted }}>
                    Pickup: {offer.mess_name} · {offer.order_count} order(s)
                  </Text>
                  <Button
                    title="View Offer"
                    onPress={() => router.push(`/(rider)/request/${offer.id}` as never)}
                    style={{ marginTop: spacing.md }}
                  />
                </PartnerCard>
              </Pressable>
            ))}

            {lastCompleted && !activeBatch ? (
              <View style={styles.section}>
                <View style={styles.sectionHeader}>
                  <Text variant="caption" style={{ color: colors.textMuted, fontWeight: '700' }}>LAST COMPLETED</Text>
                  <Text variant="caption" style={{ color: colors.secondary, fontWeight: '700' }}>
                    {lastCompleted.completed_ago_label || 'Recent'}
                  </Text>
                </View>
                <PartnerCard style={{ marginTop: spacing.sm, padding: spacing.md }}>
                  <View style={styles.recentRow}>
                    <View style={styles.recentIcon}>
                      <Ionicons name="restaurant" size={18} color={colors.onSecondaryContainer} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text variant="label">{lastCompleted.mess_name}</Text>
                      <Text variant="caption" style={{ color: colors.textMuted }}>
                        Order #{lastCompleted.ticket_ref} · {lastCompleted.item_count} items
                      </Text>
                    </View>
                    <Text variant="label">{money(lastCompleted.amount_cents)}</Text>
                  </View>
                </PartnerCard>
              </View>
            ) : null}

            {recentLines.length > 1 ? (
              <View style={styles.section}>
                <Text variant="h3">Recent Deliveries</Text>
                {recentLines.slice(1).map((line) => (
                  <PartnerCard key={line.order_id} style={{ marginTop: spacing.sm, padding: spacing.md }}>
                    <View style={styles.recentRow}>
                      <View style={styles.recentIcon}>
                        <Ionicons name="restaurant" size={18} color={colors.onSecondaryContainer} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text variant="label">Order #{line.order_id}</Text>
                        <Text variant="caption" style={{ color: colors.textMuted }}>
                          Delivered {formatRelativeAgo(line.delivered_at)}
                        </Text>
                      </View>
                      <Text variant="label" style={{ color: colors.secondary }}>+{money(line.amount_cents)}</Text>
                    </View>
                  </PartnerCard>
                ))}
              </View>
            ) : null}

            {online && !activeBatch && offers.length === 0 ? (
              <EmptyState icon="bicycle-outline" title="You're all caught up!" subtitle="Waiting for new delivery requests." />
            ) : null}
            {!online && !activeBatch ? (
              <PartnerCard>
                <Text variant="bodySmall" style={{ color: colors.textMuted, textAlign: 'center' }}>
                  Go online to receive and view delivery assignments.
                </Text>
              </PartnerCard>
            ) : null}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, gap: spacing.lg },

  greetingRow: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  greetingTitle: { fontSize: 26, lineHeight: 32 },
  greetingOnlinePill: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.successContainer, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 20, borderWidth: 1, borderColor: colors.secondaryFixed },
  greetingOnlineDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.secondary },
  greetingOnlineText: { color: colors.secondary, fontWeight: '800', fontSize: 10 },
  earningsChevron: { width: 32, height: 32, borderRadius: 16, backgroundColor: colors.surfaceContainerHigh, alignItems: 'center', justifyContent: 'center' },
  earningsAmountRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginTop: spacing.sm },

  earningsCard: { padding: spacing.lg },
  earningsHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  earningsTitleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  earningsLabel: { color: colors.textMuted, fontWeight: '700', letterSpacing: 0.5 },
  growthPill: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.secondaryFixed, paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: 12 },
  earningsAmount: { color: colors.text, fontSize: 36, lineHeight: 42 },
  metricsRow: { flexDirection: 'row', marginTop: spacing.lg, borderTopWidth: 1, borderTopColor: colors.borderLight, paddingTop: spacing.md },
  metricCol: { flex: 1, alignItems: 'center', gap: 4, borderRightWidth: 1, borderRightColor: colors.borderLight },
  metricIcon: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  activeCard: { padding: spacing.lg, borderWidth: 1, borderColor: colors.secondaryFixed },
  activeTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  statusPill: { paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: 20 },
  nextStopRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginTop: spacing.md, padding: spacing.sm, backgroundColor: colors.surfaceContainerLow, borderRadius: 12 },
  nextStopIcon: { width: 32, height: 32, borderRadius: 16, backgroundColor: colors.primaryFixed, alignItems: 'center', justifyContent: 'center' },
  activeBadge: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  activeDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.secondary },
  offerTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  dispatchPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.surfaceContainerHigh,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: 20,
  },
  countdownPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.tertiaryFixed,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: 20,
  },
  section: { marginTop: spacing.sm },
  recentRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  questCard: { padding: spacing.lg, overflow: 'hidden' },
  questHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  questBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.tertiaryFixed, paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: 20 },
  bonusPill: { backgroundColor: colors.tertiary, paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: 12 },
  questProgressRow: { marginTop: spacing.md, gap: 2 },
  progressTrack: { height: 10, backgroundColor: colors.surfaceVariant, borderRadius: 5, marginTop: spacing.md, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: colors.secondary, borderRadius: 5 },
  questFooter: { flexDirection: 'row', justifyContent: 'space-between', marginTop: spacing.sm },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  surgeCard: { backgroundColor: colors.primaryContainer, borderWidth: 0 },
  surgeTop: { flexDirection: 'row', gap: spacing.sm },
  surgePill: { backgroundColor: 'rgba(255,255,255,0.2)', paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: 8 },
  surgeMultiplier: { backgroundColor: colors.secondary, paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: 8 },
  surgeMap: { marginTop: spacing.md, height: 140, borderRadius: 12, overflow: 'hidden', position: 'relative' },
  surgeMapGradient: { ...StyleSheet.absoluteFill, backgroundColor: 'rgba(66,18,222,0.15)' },
  surgeMapOverlay: { position: 'absolute', bottom: spacing.sm, left: spacing.sm, right: spacing.sm, flexDirection: 'row', alignItems: 'center', gap: spacing.sm, padding: spacing.md, backgroundColor: 'rgba(255,255,255,0.92)', borderRadius: 10 },
  navigateBtn: { backgroundColor: colors.primary, paddingHorizontal: spacing.md, paddingVertical: spacing.xs, borderRadius: 8 },
  recentIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.secondaryContainer,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
