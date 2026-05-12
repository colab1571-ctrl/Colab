/**
 * matching-svc API client.
 *
 * NOTE: Most matching-svc endpoints are internal (service-to-service only).
 * The mobile client does not call matching-svc directly. This module provides
 * types for match score data returned indirectly through discovery-svc responses.
 *
 * If a future admin-facing mobile surface needs direct match score access,
 * those calls must go through the API Gateway with appropriate role gating.
 */

// Re-export shared types for convenience
export type { ProfileCard } from "./discovery";

/**
 * Match score components — internal to matching-svc, never returned to clients.
 * Defined here for admin tooling / debug screens only.
 */
export interface MatchScoreComponents {
  emb_sim: number | null;
  comp_voc: number | null;
  activity: number | null;
  health: number | null;
  rand: number | null;
}

export interface MatchScore {
  from_profile_id: string;
  to_profile_id: string;
  score: number;
  components: MatchScoreComponents;
  computed_at: string;
  version: number;
}
