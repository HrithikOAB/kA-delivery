/** Active delivery — map + drop-off bottom sheet (design-matched). */
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { api, ApiError } from '@/api/client';
import type { Batch, DeliveryStop } from '@/api/types';
import { ActiveDeliveryMap } from '@/components/ActiveDeliveryMap';
import type { TrackerMarker } from '@/components/DeliveryTrackerMap';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { useFeedback } from '@/components/FeedbackProvider';
import { Loading } from '@/components/Loading';
import { PartnerCard } from '@/components/partner';
import { Button } from '@/components/ui/Button';
import { FlowScreenHeader } from '@/components/ui/FlowScreenHeader';
import { Text } from '@/components/ui/Text';
import { config } from '@/config';
import { useDirectionsRoute } from '@/hooks/useDirectionsRoute';
import { useRiderPosition } from '@/hooks/useRiderPosition';
import { useTabBarHeight } from '@/hooks/useTabBarStyle';
import { colors, spacing } from '@/theme';

export default function ActiveDelivery() {
  const tabBarHeight = useTabBarHeight();
  const router = useRouter();
  const feedback = useFeedback();
  const [batch, setBatch] = useState<Batch | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setBatch(await api.riderActive());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load delivery');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    void load();
    const t = setInterval(load, config.locationIntervalMs);
    return () => clearInterval(t);
  }, [load]));

  useEffect(() => {
    if (batch?.status === 'assigned') {
      router.replace('/(rider)/pickup' as never);
    }
  }, [batch?.status, router]);

  const nextStop = batch?.stops.find((s) => s.status !== 'delivered') ?? batch?.stops[0];
  const active = batch?.active;
  const isDelivering = batch?.status === 'picked_up';

  const messPoint = useMemo(
    () => (batch ? { lat: batch.mess_lat, lng: batch.mess_lng } : null),
    [batch],
  );
  const dropPoint = useMemo(
    () =>
      nextStop?.address_lat != null && nextStop.address_lng != null
        ? { lat: nextStop.address_lat, lng: nextStop.address_lng }
        : null,
    [nextStop],
  );
  const liveRiderPosition = useRiderPosition();

  const riderPoint = useMemo(() => {
    if (active?.rider_lat != null && active?.rider_lng != null) {
      return { lat: active.rider_lat, lng: active.rider_lng };
    }
    return liveRiderPosition;
  }, [active?.rider_lat, active?.rider_lng, liveRiderPosition]);

  const routeOrigin = useMemo(() => {
    if (riderPoint) return riderPoint;
    if (isDelivering && messPoint) return messPoint;
    return null;
  }, [riderPoint, isDelivering, messPoint]);

  const { route } = useDirectionsRoute(routeOrigin, dropPoint, !!routeOrigin && !!dropPoint);

  const markers: TrackerMarker[] = useMemo(() => {
    if (!batch || !nextStop) return [];
    const list: TrackerMarker[] = [];
    if (riderPoint) {
      list.push({ lat: riderPoint.lat, lng: riderPoint.lng, label: 'You', kind: 'rider' });
    }
    if (dropPoint) {
      const dropLabel = nextStop.address_title || nextStop.customer_name || 'Drop-off';
      list.push({ lat: dropPoint.lat, lng: dropPoint.lng, label: dropLabel, kind: 'dropoff' });
    }
    return list;
  }, [batch, dropPoint, nextStop, riderPoint]);

  const etaLabel = active
    ? `${active.eta_minutes} mins (${active.distance_remaining_km.toFixed(1)} km remaining)`
    : 'Calculating route…';

  const handleArrived = async (stop: DeliveryStop) => {
    setBusy(true);
    try {
      await api.arrivedAtDrop(stop.delivery_id);
      router.push(`/(rider)/complete/${stop.delivery_id}` as never);
    } catch (err) {
      feedback.error(err instanceof ApiError ? err.message : 'Could not mark arrival');
    } finally {
      setBusy(false);
    }
  };

  const callCustomer = (phone?: string) => {
    if (!phone) {
      feedback.info('Customer phone is not available.', 'Unavailable');
      return;
    }
    void Linking.openURL(`tel:${phone.replace(/\s/g, '')}`);
  };

  if (loading && !batch) return <Loading label="Loading delivery…" />;
  if (error && !batch) return <ErrorState message={error} onRetry={load} variant="page" />;
  if (!batch || !nextStop) {
    return (
      <EmptyState
        icon="bicycle-outline"
        title="No active delivery"
        subtitle="Go online and accept an order to start delivering."
        actionLabel="Back to dashboard"
        onAction={() => router.replace('/(rider)/' as never)}
      />
    );
  }

  const addressTitle = nextStop.address_title || nextStop.address_text;
  const addressSubtitle = nextStop.address_subtitle || '';
  const helperText = nextStop.helper_text || active?.helper_text || 'Tap when you reach the drop location';

  return (
    <View style={styles.screen}>
      <View style={styles.mapArea}>
        <ActiveDeliveryMap
          markers={markers}
          route={route}
          etaLabel={etaLabel}
          routeLabel={active?.route_label || 'FAST ROUTE'}
        />
        <View style={styles.mapHeader}>
          <FlowScreenHeader title="Active Delivery" showLogo />
        </View>
      </View>

      <View style={styles.sheet}>
        <View style={styles.sheetHandle} />
        <ScrollView contentContainerStyle={[styles.sheetContent, { paddingBottom: tabBarHeight + spacing.lg }]} showsVerticalScrollIndicator={false}>
          {error ? <ErrorState message={error} variant="inline" onRetry={load} /> : null}

          <View style={styles.statusRow}>
            <View style={styles.statusLeft}>
              <View style={styles.statusDot} />
              <Text variant="label" style={{ color: colors.secondary }}>
                {active?.status_label || 'On the way to customer'}
              </Text>
            </View>
            <View style={styles.timePill}>
              <Ionicons name="time-outline" size={14} color={colors.textMuted} />
              <Text variant="caption" style={styles.timeText}>{nextStop.deliver_by_label || active?.deliver_by_label || 'BY SOON'}</Text>
            </View>
          </View>

          <PartnerCard variant="container" style={styles.addressCard}>
            <View style={styles.addressRow}>
              <View style={styles.addressIcon}>
                <Ionicons name="location" size={20} color="#E91E63" />
              </View>
              <View style={{ flex: 1 }}>
                <View style={styles.addressTop}>
                  <Text variant="caption" style={styles.addressLabel}>DESTINATION ADDRESS</Text>
                  {nextStop.address_tag ? (
                    <View style={styles.tagPill}><Text variant="caption" style={styles.tagText}>{nextStop.address_tag}</Text></View>
                  ) : null}
                </View>
                <Text variant="label" style={styles.addressTitle}>{addressTitle}</Text>
                {addressSubtitle ? <Text variant="bodySmall" style={styles.addressSub}>{addressSubtitle}</Text> : null}
              </View>
            </View>
            {nextStop.customer_note ? (
              <View style={styles.noteBox}>
                <Ionicons name="document-text-outline" size={14} color={colors.textMuted} />
                <View style={{ flex: 1 }}>
                  <Text variant="caption" style={styles.noteLabel}>CUSTOMER NOTE:</Text>
                  <Text variant="caption" style={styles.noteText}>{nextStop.customer_note}</Text>
                </View>
              </View>
            ) : null}
          </PartnerCard>

          <PartnerCard variant="lowest" style={styles.customerCard}>
            <View style={styles.customerRow}>
              <View style={styles.avatar}>
                <Text style={{ fontSize: 22 }}>👩</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text variant="label">{nextStop.customer_name}</Text>
                {nextStop.customer_verified ? (
                  <View style={styles.verifiedRow}>
                    <Ionicons name="checkmark-circle" size={12} color={colors.secondary} />
                    <Text variant="caption" style={styles.verifiedText}>Verified Diner</Text>
                  </View>
                ) : null}
              </View>
              <Pressable style={styles.actionBtn} onPress={() => callCustomer(nextStop.customer_phone)}>
                <Ionicons name="call" size={18} color={colors.primary} />
              </Pressable>
              <Pressable style={styles.actionBtn} onPress={() => feedback.info('In-app chat coming soon.', 'Coming soon')}>
                <Ionicons name="chatbubble-ellipses" size={18} color={colors.primary} />
                <View style={styles.chatDot} />
              </Pressable>
            </View>
          </PartnerCard>

          <Button
            title="✓  Arrived at Drop Location"
            onPress={() => handleArrived(nextStop)}
            loading={busy}
            style={styles.arriveBtn}
          />
          <Text variant="caption" style={styles.helperText}>{helperText}</Text>
        </ScrollView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  mapArea: { flex: 1, minHeight: 280 },
  mapHeader: { position: 'absolute', top: 0, left: 0, right: 0, zIndex: 10 },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    maxHeight: '52%',
    shadowColor: '#000',
    shadowOpacity: 0.12,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: -4 },
    elevation: 8,
  },
  sheetHandle: {
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: colors.borderLight, alignSelf: 'center', marginTop: spacing.sm,
  },
  sheetContent: { padding: spacing.lg, gap: spacing.md },
  statusRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  statusLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  statusDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.secondary },
  timePill: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  timeText: { color: colors.textMuted, fontWeight: '700' },
  addressCard: { padding: spacing.md, gap: spacing.md },
  addressRow: { flexDirection: 'row', gap: spacing.md },
  addressIcon: {
    width: 44, height: 44, borderRadius: 12,
    backgroundColor: '#FCE4EC', alignItems: 'center', justifyContent: 'center',
  },
  addressTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm },
  addressLabel: { color: colors.textMuted, fontWeight: '700', letterSpacing: 0.4 },
  tagPill: { backgroundColor: colors.surfaceContainerHigh, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  tagText: { color: colors.textMuted, fontWeight: '700', fontSize: 10 },
  addressTitle: { marginTop: 4, fontSize: 16 },
  addressSub: { color: colors.textMuted, marginTop: 2 },
  noteBox: {
    flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start',
    backgroundColor: '#FFF8E1', borderRadius: 12, padding: spacing.md,
    borderWidth: 1, borderColor: '#FFE082',
  },
  noteLabel: { color: colors.textMuted, fontWeight: '800', fontSize: 10 },
  noteText: { color: colors.text, marginTop: 2, fontStyle: 'italic' },
  customerCard: { padding: spacing.md },
  customerRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  avatar: {
    width: 48, height: 48, borderRadius: 24,
    backgroundColor: colors.primaryFixed, alignItems: 'center', justifyContent: 'center',
  },
  verifiedRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 },
  verifiedText: { color: colors.secondary, fontWeight: '700' },
  actionBtn: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: colors.primaryFixed, alignItems: 'center', justifyContent: 'center',
  },
  chatDot: {
    position: 'absolute', top: 8, right: 8,
    width: 8, height: 8, borderRadius: 4, backgroundColor: '#E53935',
    borderWidth: 1.5, borderColor: colors.surface,
  },
  arriveBtn: { marginTop: spacing.sm },
  helperText: { textAlign: 'center', color: colors.textMuted, marginTop: -spacing.sm },
});
