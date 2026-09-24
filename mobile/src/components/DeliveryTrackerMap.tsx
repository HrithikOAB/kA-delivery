import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { useMemo, useState } from 'react';
import { LayoutChangeEvent, StyleSheet, View } from 'react-native';
import { DeliveryMapLayer } from '@/components/DeliveryMapLayer';
import { OsmTileBackground, projectPointInBounds } from '@/components/OsmTileBackground';
import { config, useInteractiveMap } from '@/config';
import { boundsFor, pickOsmZoom, staticGoogleMapUrl, staticMapUrl, type LatLng } from '@/lib/map-route';
import { colors, radius, shadow, spacing } from '@/theme';
import { Text } from './ui/Text';

export type TrackerMarkerKind = 'mess' | 'rider' | 'dropoff';

export interface TrackerMarker {
  lat: number;
  lng: number;
  label: string;
  kind: TrackerMarkerKind;
}

const MARKER_META: Record<TrackerMarkerKind, { color: string; icon: keyof typeof Ionicons.glyphMap }> = {
  rider: { color: '#4212DE', icon: 'navigate' },
  mess: { color: '#F59E0B', icon: 'restaurant' },
  dropoff: { color: '#10B981', icon: 'home' },
};

const PIN_COLORS: Record<TrackerMarkerKind, string> = {
  rider: '#4212DE',
  mess: '#F59E0B',
  dropoff: '#10B981',
};

export const TRACKER_LEGEND: Array<{ kind: TrackerMarkerKind; label: string }> = [
  { kind: 'rider', label: 'You' },
  { kind: 'mess', label: 'Pickup' },
  { kind: 'dropoff', label: 'Drop-off' },
];

function projectPoint(
  point: LatLng,
  bounds: ReturnType<typeof boundsFor>,
  width: number,
  height: number,
  zoom: number,
) {
  return projectPointInBounds(point, bounds, width, height, zoom);
}

function RouteSegment({ x1, y1, x2, y2 }: { x1: number; y1: number; x2: number; y2: number }) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const length = Math.hypot(dx, dy);
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;

  return (
    <View
      pointerEvents="none"
      style={{
        position: 'absolute',
        left: cx - length / 2,
        top: cy - 2,
        width: length,
        height: 4,
        backgroundColor: colors.primary,
        borderRadius: 2,
        transform: [{ rotate: `${angle}deg` }],
        opacity: 0.9,
      }}
    />
  );
}

function StaticTrackerMap({
  markers,
  route,
  mapUrl,
  bounds,
  height,
  style,
  onLayout,
}: {
  markers: TrackerMarker[];
  route: LatLng[];
  mapUrl: string;
  bounds: ReturnType<typeof boundsFor>;
  height: number;
  style?: object;
  onLayout: (e: LayoutChangeEvent) => void;
}) {
  const [size, setSize] = useState({ width: 0, height: 0 });
  // Default to OSM tiles — Google Static Maps often 403s (Static Maps API not
  // enabled / referrer-restricted key) and renders a broken error image. OSM
  // needs no key and aligns with the projected pins. The APK uses native
  // Google Maps and never reaches this static fallback.
  const [mapFailed, setMapFailed] = useState(true);
  const zoom = useMemo(() => pickOsmZoom(bounds), [bounds]);
  const googleMapUrl = useMemo(
    () => staticGoogleMapUrl(
      [...route, ...markers.map((m) => ({ lat: m.lat, lng: m.lng }))],
      Math.max(size.width, 720),
      Math.max(size.height, height),
      config.mapApiKey,
      route,
    ),
    [route, markers, size.width, size.height, height],
  );
  const backgroundUrl = googleMapUrl ?? mapUrl;

  const projectedRoute = useMemo(() => {
    if (!size.width) return [] as { x: number; y: number }[];
    return route.map((p) => projectPoint(p, bounds, size.width, size.height, zoom));
  }, [route, bounds, size, zoom]);

  const projectedMarkers = useMemo(() => {
    if (!size.width) return [] as Array<{ x: number; y: number; marker: TrackerMarker }>;
    return markers.map((m) => ({
      marker: m,
      ...projectPoint(m, bounds, size.width, size.height, zoom),
    }));
  }, [markers, bounds, size, zoom]);

  return (
    <View style={[styles.wrap, { height }, style]} onLayout={(e) => {
      const { width, height: h } = e.nativeEvent.layout;
      setSize({ width, height: h });
      onLayout(e);
    }}>
      {mapFailed ? (
        <OsmTileBackground bounds={bounds} width={size.width} height={size.height} />
      ) : (
        <Image
          source={{ uri: backgroundUrl }}
          style={StyleSheet.absoluteFill}
          contentFit="cover"
          onError={() => setMapFailed(true)}
        />
      )}

      <View style={styles.tint} pointerEvents="none" />

      {projectedRoute.slice(0, -1).map((p, i) => {
        const next = projectedRoute[i + 1];
        return <RouteSegment key={`seg-${i}`} x1={p.x} y1={p.y} x2={next.x} y2={next.y} />;
      })}

      {projectedMarkers.map(({ marker, x, y }, i) => {
        const meta = MARKER_META[marker.kind];
        return (
          <View key={`${marker.kind}-${marker.lat}-${marker.lng}-${i}`} style={[styles.marker, { left: x - 18, top: y - 36 }]}>
            <View style={[styles.pin, { backgroundColor: meta.color }]}>
              <Ionicons name={meta.icon} size={16} color={colors.onPrimary} />
            </View>
            <View style={styles.pinTail} />
            <Text variant="caption" style={styles.markerLabel} numberOfLines={1}>{marker.label}</Text>
          </View>
        );
      })}
    </View>
  );
}

export function DeliveryTrackerMap({
  markers,
  route,
  height,
  style,
  badgeLabel = 'LIVE TRACKING',
  showLegend = false,
}: {
  markers: TrackerMarker[];
  route: LatLng[];
  height: number;
  style?: object;
  badgeLabel?: string;
  showLegend?: boolean;
}) {
  const allPoints = useMemo(() => [...route, ...markers.map((m) => ({ lat: m.lat, lng: m.lng }))], [route, markers]);
  const bounds = useMemo(() => boundsFor(allPoints), [allPoints]);
  const mapUrl = useMemo(() => staticMapUrl(allPoints, 720, height, config.mapApiKey, route), [allPoints, height, route]);

  const nativeMarkers = useMemo(
    () => markers.map((m) => ({
      lat: m.lat,
      lng: m.lng,
      title: m.label,
      pinColor: PIN_COLORS[m.kind],
      kind: m.kind,
    })),
    [markers],
  );

  const noopLayout = (_e: LayoutChangeEvent) => {};

  const useInteractiveMapLayer = useInteractiveMap;

  return (
    <View style={[styles.wrap, { height }, style]}>
      {useInteractiveMapLayer ? (
        <DeliveryMapLayer route={route} markers={nativeMarkers} style={{ height }} />
      ) : (
        <StaticTrackerMap
          markers={markers}
          route={route}
          mapUrl={mapUrl}
          bounds={bounds}
          height={height}
          onLayout={noopLayout}
        />
      )}

      <View style={styles.badge} pointerEvents="none">
        <Text variant="caption" style={styles.badgeText}>{badgeLabel}</Text>
      </View>

      {showLegend ? (
        <View style={styles.legend} pointerEvents="none">
          {TRACKER_LEGEND.map(({ kind, label }) => (
            <View key={kind} style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: PIN_COLORS[kind] }]} />
              <Text variant="caption" style={styles.legendText}>{label}</Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { width: '100%', backgroundColor: '#E8EDF2', overflow: 'hidden' },
  tint: { ...StyleSheet.absoluteFill, backgroundColor: 'rgba(91,61,245,0.04)' },
  fallbackBg: { ...StyleSheet.absoluteFill, backgroundColor: '#E4EBE8', padding: spacing.lg },
  gridRow: { height: 1, backgroundColor: 'rgba(0,0,0,0.06)', width: '100%' },
  marker: { position: 'absolute', alignItems: 'center', width: 120 },
  pin: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', borderWidth: 3, borderColor: colors.surface, ...shadow },
  pinTail: { width: 2, height: 8, backgroundColor: colors.surface, marginTop: -1 },
  markerLabel: { marginTop: 2, fontWeight: '700', textAlign: 'center', backgroundColor: colors.surface, paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.sm, overflow: 'hidden' },
  badge: { position: 'absolute', top: spacing.md, left: spacing.md, backgroundColor: colors.surface, paddingHorizontal: spacing.md, paddingVertical: spacing.xs, borderRadius: radius.pill, ...shadow },
  badgeText: { color: colors.primary, fontWeight: '800', letterSpacing: 0.6 },
  legend: {
    position: 'absolute',
    bottom: spacing.sm,
    left: spacing.sm,
    right: spacing.sm,
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: 'rgba(255,255,255,0.94)',
    borderRadius: radius.md,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    ...shadow,
  },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendText: { fontWeight: '700', color: colors.text, fontSize: 11 },
});
