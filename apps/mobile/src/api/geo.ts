/**
 * geo-svc API client — typed wrappers for geocoding endpoints.
 *
 * IMPORTANT: All calls go through the API Gateway → geo-svc proxy.
 * MAPBOX_SECRET_TOKEN is never exposed to the client. Public token usage
 * (e.g., Mapbox GL JS map rendering) uses EXPO_PUBLIC_MAPBOX_PUBLIC_TOKEN.
 */

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://api.colab.com";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface GeoFeatureContext {
  place?: string | null;
  region?: string | null;
  country?: string | null;
}

export interface GeoAutocompleteFeature {
  id: string;
  name: string;
  place_name: string;
  context: GeoFeatureContext;
  lng: number | null;
  lat: number | null;
}

export interface AutocompleteResponse {
  results: GeoAutocompleteFeature[];
  cached: boolean;
}

export interface ReverseGeocodeResponse {
  city: string | null;
  region: string | null;
  country: string | null;
  cached: boolean;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export async function geocodeAutocomplete(
  q: string,
  opts?: { types?: string; limit?: number }
): Promise<AutocompleteResponse> {
  const qs = new URLSearchParams({ q });
  if (opts?.types) qs.set("types", opts.types);
  if (opts?.limit) qs.set("limit", String(opts.limit));

  const res = await fetch(`${BASE_URL}/geo/autocomplete?${qs.toString()}`);
  if (!res.ok) {
    throw new Error(`Autocomplete failed: ${res.status}`);
  }
  return res.json() as Promise<AutocompleteResponse>;
}

export async function reverseGeocode(
  lat: number,
  lng: number
): Promise<ReverseGeocodeResponse> {
  const qs = new URLSearchParams({ lat: String(lat), lng: String(lng) });
  const res = await fetch(`${BASE_URL}/geo/reverse?${qs.toString()}`);
  if (!res.ok) {
    throw new Error(`Reverse geocode failed: ${res.status}`);
  }
  return res.json() as Promise<ReverseGeocodeResponse>;
}
