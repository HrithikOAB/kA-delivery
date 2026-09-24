import type { PlaceDetails, PlaceSuggestion } from './google-places';

export async function fetchOsmSuggestions(input: string): Promise<PlaceSuggestion[]> {
  const q = input.trim();
  if (q.length < 2) return [];

  const url = `https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&limit=6&countrycodes=in&q=${encodeURIComponent(q)}`;
  const res = await fetch(url, { headers: { Accept: 'application/json', 'User-Agent': 'KhanaDeliveryAdmin/1.0 (admin place search)' } });
  if (!res.ok) throw new Error('OpenStreetMap search failed');

  const rows = await res.json() as Array<{ place_id: number; display_name: string; lat: string; lon: string; name?: string }>;
  return rows.map((r) => ({
    placeId: `osm:${r.place_id}`,
    label: r.name ?? r.display_name.split(',')[0],
    secondary: r.display_name,
    lat: Number(r.lat),
    lng: Number(r.lon),
  }));
}

export function osmPlaceDetails(item: PlaceSuggestion & { lat?: number; lng?: number }): PlaceDetails {
  if (item.lat == null || item.lng == null) throw new Error('Missing coordinates');
  return {
    lat: item.lat,
    lng: item.lng,
    label: item.label,
    address: item.secondary ?? item.label,
  };
}
