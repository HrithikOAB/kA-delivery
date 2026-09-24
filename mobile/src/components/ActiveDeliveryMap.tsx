import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { useCallback, useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { useAnimatedStyle, useSharedValue } from 'react-native-reanimated';
import type { TrackerMarker } from '@/components/DeliveryTrackerMap';
import { DeliveryMapLayer } from '@/components/DeliveryMapLayer';
import { OsmTileBackground, projectPointInBounds } from '@/components/OsmTileBackground';
import { config, useInteractiveMap } from '@/config';
import { boundsFor, pickOsmZoom, staticMapUrl, type LatLng } from '@/lib/map-route';
import { colors, radius, shadow, spacing } from '@/theme';
import { Text } from './ui/Text';

const PIN_COLORS: Record<TrackerMarker['kind'], string> = {
  mess: '#F59E0B',
  rider: colors.primary,
  dropoff: '#E53935',
};

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
        top: cy - 3,
        width: length,
        height: 6,
        backgroundColor: colors.primary,
        borderRadius: 3,
        transform: [{ rotate: `${angle}deg` }],
        opacity: 0.95,
      }}
    />
  );
}

function StaticDeliveryMap({
  markers,
  route,
  mapUrl,
  bounds,
}: {
  markers: TrackerMarker[];
  route: LatLng[];
  mapUrl: string;
  bounds: ReturnType<typeof boundsFor>;
}) {
  const [size, setSize] = useState({ width: 0, height: 0 });
  // Default to OSM tiles: Google Static Maps requires the Static Maps API + a
  // referrer-unrestricted key, which often 403s and renders a broken error
  // image. OSM tiles need no key and align with our projected pins. (The APK's
  // interactive path uses native Google Maps and never reaches this fallback.)
  const [mapFailed, setMapFailed] = useState(true);
  const zoom = useMemo(() => pickOsmZoom(bounds), [bounds]);
  const tx = useSharedValue(0);
  const ty = useSharedValue(0);
  const startX = useSharedValue(0);
  const startY = useSharedValue(0);

  const projectedRoute = useMemo(() => {
    if (!size.width) return [];
    return route.map((p) => projectPoint(p, bounds, size.width, size.height, zoom));
  }, [route, bounds, size, zoom]);

  const projectedMarkers = useMemo(() => {
    if (!size.width) return [];
    return markers.map((m) => ({ marker: m, ...projectPoint(m, bounds, size.width, size.height, zoom) }));
  }, [markers, bounds, size, zoom]);

  const pan = Gesture.Pan()
    .onBegin(() => {
      startX.value = tx.value;
      startY.value = ty.value;
    })
    .onUpdate((e) => {
      tx.value = startX.value + e.translationX;
      ty.value = startY.value + e.translationY;
    });

  const mapStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: tx.value }, { translateY: ty.value }, { scale: 1.15 }],
  }));

  return (
    <GestureDetector gesture={pan}>
      <Animated.View
        style={[styles.mapLayer, mapStyle]}
        onLayout={(e) => {
          const { width, height } = e.nativeEvent.layout;
          setSize({ width, height });
        }}
      >
        {mapFailed ? (
          <OsmTileBackground bounds={bounds} width={size.width} height={size.height} />
        ) : (
          <Image source={{ uri: mapUrl }} style={StyleSheet.absoluteFill} contentFit="cover" onError={() => setMapFailed(true)} />
        )}
        <View style={styles.tint} pointerEvents="none" />
        {projectedRoute.slice(0, -1).map((p, i) => {
          const next = projectedRoute[i + 1];
          return <RouteSegment key={i} x1={p.x} y1={p.y} x2={next.x} y2={next.y} />;
        })}
        {projectedMarkers.map(({ marker, x, y }, i) => {
          const isDrop = marker.kind === 'dropoff';
          const isRider = marker.kind === 'rider';
          return (
            <View key={i} style={[styles.marker, { left: x - 20, top: y - (isDrop ? 44 : 36) }]}>
              {isDrop ? (
                <View style={styles.dropTag}><Text variant="caption" style={styles.dropTagText}>DROP</Text></View>
              ) : null}
              <View style={[styles.pin, isDrop ? styles.dropPin : isRider ? styles.riderPin : styles.messPin]}>
                <Ionicons name={isDrop ? 'location' : isRider ? 'bicycle' : 'restaurant'} size={16} color={colors.onPrimary} />
              </View>
            </View>
          );
        })}
      </Animated.View>
    </GestureDetector>
  );
}

export function ActiveDeliveryMap({
  markers,
  route,
  etaLabel,
  routeLabel,
  onRecenter,
}: {
  markers: TrackerMarker[];
  route: LatLng[];
  etaLabel: string;
  routeLabel: string;
  onRecenter?: () => void;
}) {
  const fitRef = useRef<(() => void) | null>(null);
  const useGoogleMap = useInteractiveMap;

  const allPoints = useMemo(() => [...route, ...markers.map((m) => ({ lat: m.lat, lng: m.lng }))], [route, markers]);
  const bounds = useMemo(() => boundsFor(allPoints), [allPoints]);
  const mapUrl = useMemo(() => staticMapUrl(allPoints, 900, 700, config.mapApiKey, route), [allPoints]);

  const nativeMarkers = useMemo(
    () => markers.map((m) => ({ lat: m.lat, lng: m.lng, title: m.label, pinColor: PIN_COLORS[m.kind] })),
    [markers],
  );

  const handleMapReady = useCallback((fit: () => void) => {
    fitRef.current = fit;
  }, []);

  const recenter = () => {
    fitRef.current?.();
    onRecenter?.();
  };

  return (
    <View style={styles.wrap}>
      {useGoogleMap ? (
        <DeliveryMapLayer route={route} markers={nativeMarkers} style={StyleSheet.absoluteFill} onMapReady={handleMapReady} />
      ) : (
        <StaticDeliveryMap markers={markers} route={route} mapUrl={mapUrl} bounds={bounds} />
      )}

      <View style={styles.etaPill} pointerEvents="none">
        <View style={styles.liveDot} />
        <Text variant="caption" style={styles.etaText}>{etaLabel}</Text>
      </View>
      <View style={styles.routePill} pointerEvents="none">
        <Ionicons name="git-network-outline" size={14} color={colors.primary} />
        <Text variant="caption" style={styles.routeText}>{routeLabel}</Text>
      </View>
      <View style={styles.mapControls}>
        <Pressable style={styles.mapBtn} onPress={recenter}>
          <Ionicons name="locate" size={18} color={colors.text} />
        </Pressable>
        <Pressable style={styles.mapBtn}>
          <Ionicons name="volume-high-outline" size={18} color={colors.text} />
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: '#E8EDF2', overflow: 'hidden' },
  mapLayer: { ...StyleSheet.absoluteFill },
  tint: { ...StyleSheet.absoluteFill, backgroundColor: 'rgba(91,61,245,0.03)' },
  fallbackBg: { ...StyleSheet.absoluteFill, backgroundColor: '#E4EBE8' },
  marker: { position: 'absolute', alignItems: 'center' },
  pin: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', borderWidth: 3, borderColor: colors.surface, ...shadow },
  riderPin: { backgroundColor: colors.primary },
  messPin: { backgroundColor: colors.warning },
  dropPin: { backgroundColor: '#E53935' },
  dropTag: { backgroundColor: '#1A1A1A', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, marginBottom: 4 },
  dropTagText: { color: colors.onPrimary, fontWeight: '800', fontSize: 10 },
  etaPill: {
    position: 'absolute', top: spacing.md, left: spacing.md,
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: colors.surface, paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderRadius: radius.pill, ...shadow,
  },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.secondary },
  etaText: { fontWeight: '700', color: colors.text },
  routePill: {
    position: 'absolute', top: spacing.md, right: spacing.md,
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: colors.surface, paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderRadius: radius.pill, ...shadow,
  },
  routeText: { fontWeight: '800', color: colors.primary, fontSize: 11 },
  mapControls: { position: 'absolute', right: spacing.md, bottom: spacing.xl, gap: spacing.sm },
  mapBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', ...shadow },
});
