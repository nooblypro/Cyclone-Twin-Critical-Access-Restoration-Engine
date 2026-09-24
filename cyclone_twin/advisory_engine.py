"""
Cyclone Twin Advisory Engine
Generates concise operational disaster advisories via Gemini with deterministic
and emergency fallback layers. Gemini is strictly an explanatory layer.
"""

import os
from typing import List, Optional
from .models import (
    ActionVerb,
    AdvisoryGenerateRequest,
    AdvisoryGenerateResponse,
    ScoreBreakdown,
)


class AdvisoryEngine:
    """
    Produces schema-constrained operational advisories.
    Ranking is never modified by this layer.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    def generate_advisory(
        self,
        corridor_id: str,
        score_breakdown: ScoreBreakdown,
        road_names: Optional[List[str]] = None,
        communities_affected: Optional[List[str]] = None,
    ) -> AdvisoryGenerateResponse:
        """
        Generates advisory using 3-tier fallback:
        Tier 1: Gemini API (if key available and call succeeds)
        Tier 2: Deterministic rule-based template
        Tier 3: Emergency static fallback
        """
        roads = road_names or [corridor_id]
        communities = communities_affected or ["Adjacent GCC Wards"]

        # Tier 1: Attempt Gemini
        if self.api_key:
            try:
                from google import genai
                client = genai.Client(api_key=self.api_key)

                prompt = (
                    f"You are the GCC Disaster Management emergency dispatch advisor.\n"
                    f"Corridor: {corridor_id} ({', '.join(roads[:2])})\n"
                    f"Hospitals recovered: {score_breakdown.hospitals_recovered}\n"
                    f"Population recovered: {score_breakdown.population_recovered:,}\n"
                    f"Time saved: {score_breakdown.time_saved_minutes} min\n"
                    f"Score: {score_breakdown.score:.3f}\n"
                    f"Combined intervention required: {score_breakdown.combined_intervention_required}\n\n"
                    f"Task: Write an operational dispatch directive for GCC field responders.\n"
                    f"STRICT CONSTRAINT: Must be <= 200 characters. Single paragraph. Direct, urgent tone."
                )

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                raw_text = (response.text or "").strip()
                if raw_text:
                    if len(raw_text) > 220:
                        raw_text = raw_text[:217] + "..."

                    # Select action verb based on metrics
                    if score_breakdown.hospitals_recovered > 0:
                        verb = ActionVerb.DEPLOY_PUMPS
                    elif score_breakdown.combined_intervention_required:
                        verb = ActionVerb.PRIORITIZE_ACCESS
                    else:
                        verb = ActionVerb.CLEAR_DEBRIS

                    return AdvisoryGenerateResponse(
                        advisory_text=raw_text,
                        language="en",
                        source_corridor_id=corridor_id,
                        validated=True,
                        fallback=False,
                        road_names=roads,
                        communities_affected=communities,
                        action_verb=verb,
                    )
            except Exception:
                # Silently cascade to Tier 2 deterministic fallback
                pass

        # Tier 2: Deterministic Rule-Based Fallback
        try:
            return self._deterministic_fallback(
                corridor_id=corridor_id,
                breakdown=score_breakdown,
                roads=roads,
                communities=communities,
            )
        except Exception:
            # Tier 3: Emergency Static Fallback
            return AdvisoryGenerateResponse(
                advisory_text=f"EMERGENCY: Expedite clearance on {corridor_id} to restore regional arterial ambulance access.",
                language="en",
                source_corridor_id=corridor_id,
                validated=True,
                fallback=True,
                road_names=roads,
                communities_affected=communities,
                action_verb=ActionVerb.PRIORITIZE_ACCESS,
            )

    def _deterministic_fallback(
        self,
        corridor_id: str,
        breakdown: ScoreBreakdown,
        roads: List[str],
        communities: List[str],
    ) -> AdvisoryGenerateResponse:
        """Deterministic templated advisory complying with <= 220 chars limit."""
        road_label = roads[0] if roads else corridor_id

        if breakdown.combined_intervention_required:
            text = (
                f"ADVISORY: Clearing {road_label} alone will not reconnect cutoff zones. "
                f"Simultaneous unblocking of tributary corridors required for emergency transit."
            )
            verb = ActionVerb.PRIORITIZE_ACCESS
        elif breakdown.hospitals_recovered > 0:
            text = (
                f"PRIORITY 1: Deploy high-capacity dewatering pumps on {road_label}. "
                f"Restores critical ambulance access to {breakdown.hospitals_recovered} isolated hospital(s) "
                f"and {breakdown.population_recovered:,} residents."
            )
            verb = ActionVerb.DEPLOY_PUMPS
        elif breakdown.population_recovered > 10000:
            text = (
                f"CRITICAL ACCESS: Mobilize earthmovers to clear {road_label}. "
                f"Re-establishes lifeline routing for {breakdown.population_recovered:,} cut-off citizens "
                f"saving ~{breakdown.time_saved_minutes:.0f}m transit time."
            )
            verb = ActionVerb.CLEAR_DEBRIS
        else:
            text = (
                f"DISPATCH: Clear {road_label} to optimize secondary emergency routes, "
                f"reducing emergency travel degradation by {breakdown.delta_t * 100:.1f}% across {communities[0]}."
            )
            verb = ActionVerb.CLEAR_DEBRIS

        if len(text) > 220:
            text = text[:217] + "..."

        return AdvisoryGenerateResponse(
            advisory_text=text,
            language="en",
            source_corridor_id=corridor_id,
            validated=True,
            fallback=True,
            road_names=roads,
            communities_affected=communities,
            action_verb=verb,
        )
