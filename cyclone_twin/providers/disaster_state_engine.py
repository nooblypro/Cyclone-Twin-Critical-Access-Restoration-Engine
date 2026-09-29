"""
Disaster State Engine & Operational Coordination Manager for Cyclone Twin
Provides deterministic state versioning, change detection, alert evaluation,
deduplication, lifecycle tracking, atomic transitions, and observation-to-state traceability.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from cyclone_twin.domain.entities import (
    DisasterState,
    StateDiff,
    OperationalAlert,
    OperationalEvent,
    InfrastructureObservation,
)

logger = logging.getLogger("cyclone_twin.disaster_state_engine")


class ChangeDetector:
    """
    Computes deterministic differences between two DisasterState snapshots.
    """

    @staticmethod
    def detect_state_changes(
        before: DisasterState,
        after: DisasterState,
        previous_top_candidate: Optional[str] = None,
        current_top_candidate: Optional[str] = None,
        priority_change_reason: Optional[str] = None,
    ) -> StateDiff:
        road_changes: List[Dict[str, Any]] = []
        hospital_changes: List[Dict[str, Any]] = []

        before_segs = set(before.affected_segments)
        after_segs = set(after.affected_segments)

        newly_blocked = after_segs - before_segs
        newly_opened = before_segs - after_segs

        for seg in sorted(list(newly_blocked)):
            road_changes.append({
                "segment_id": seg,
                "before_status": "OPEN",
                "after_status": "BLOCKED",
                "change_type": "ROAD_BLOCKED",
            })
        for seg in sorted(list(newly_opened)):
            road_changes.append({
                "segment_id": seg,
                "before_status": "BLOCKED",
                "after_status": "OPEN",
                "change_type": "ROAD_REOPENED",
            })

        before_facs = {f["facility_id"]: f for f in before.affected_facilities}
        after_facs = {f["facility_id"]: f for f in after.affected_facilities}

        for fac_id, a_fac in after_facs.items():
            b_fac = before_facs.get(fac_id)
            if not b_fac:
                continue
            if b_fac.get("status") != a_fac.get("status") or abs(b_fac.get("travel_time_min", 0.0) - a_fac.get("travel_time_min", 0.0)) > 0.1:
                hospital_changes.append({
                    "facility_id": fac_id,
                    "facility_name": a_fac.get("name", fac_id),
                    "before_status": b_fac.get("status"),
                    "after_status": a_fac.get("status"),
                    "before_travel_time_min": b_fac.get("travel_time_min"),
                    "after_travel_time_min": a_fac.get("travel_time_min"),
                    "change_type": "HOSPITAL_STATUS_CHANGED" if b_fac.get("status") != a_fac.get("status") else "TRAVEL_TIME_DEGRADED",
                })

        # Population changes
        b_iso = before.affected_population.get("isolated", 0)
        a_iso = after.affected_population.get("isolated", 0)
        b_acc = before.affected_population.get("accessible", 0)
        a_acc = after.affected_population.get("accessible", 0)

        iso_delta = a_iso - b_iso
        acc_delta = a_acc - b_acc

        newly_isolated_count = max(0, iso_delta)
        recovered_count = max(0, -iso_delta)

        pop_change = {
            "before_isolated": b_iso,
            "after_isolated": a_iso,
            "isolated_delta": iso_delta,
            "accessible_delta": acc_delta,
            "newly_isolated": newly_isolated_count,
            "newly_recovered": recovered_count,
        }

        priority_changed = False
        if previous_top_candidate and current_top_candidate and previous_top_candidate != current_top_candidate:
            priority_changed = True

        return StateDiff(
            from_version=before.state_version,
            to_version=after.state_version,
            road_changes=road_changes,
            hospital_changes=hospital_changes,
            population_change=pop_change,
            priority_changed=priority_changed,
            previous_top_candidate=previous_top_candidate,
            current_top_candidate=current_top_candidate,
            priority_change_reason=priority_change_reason,
        )


class AlertEngine:
    """
    Evaluates deterministic alert rules, deduplicates operational alerts,
    and manages alert lifecycle (NEW -> ACKNOWLEDGED -> RESOLVED / DISMISSED).
    """

    def __init__(self):
        self.alerts: Dict[str, OperationalAlert] = {}

    def evaluate_state_diff(
        self,
        diff: StateDiff,
        current_state: DisasterState,
        observations: Optional[List[InfrastructureObservation]] = None,
    ) -> List[OperationalAlert]:
        new_alerts: List[OperationalAlert] = []

        # Rule 1: CRITICAL_HOSPITAL_ACCESS_LOSS
        for hc in diff.hospital_changes:
            if hc.get("before_status") == "ACCESSIBLE" and hc.get("after_status") == "INACCESSIBLE":
                alert = self._create_or_update_alert(
                    alert_type="CRITICAL_HOSPITAL_ACCESS_LOSS",
                    severity="CRITICAL",
                    affected_entity_id=hc["facility_id"],
                    affected_entity_name=hc.get("facility_name"),
                    source_version=diff.to_version,
                    evidence=[{
                        "description": f"Hospital {hc.get('facility_name')} lost access",
                        "before_travel_time": hc.get("before_travel_time_min"),
                        "after_travel_time": hc.get("after_travel_time_min"),
                    }],
                )
                new_alerts.append(alert)

        # Rule 2: POPULATION_ISOLATION_INCREASE (HIGH severity if >= 10,000 isolated increase)
        iso_delta = diff.population_change.get("isolated_delta", 0)
        if iso_delta >= 10000:
            alert = self._create_or_update_alert(
                alert_type="POPULATION_ISOLATION_INCREASE",
                severity="HIGH",
                affected_entity_id="population_gcc",
                affected_entity_name="Greater Chennai Corporation Population",
                source_version=diff.to_version,
                evidence=[{
                    "isolated_delta": iso_delta,
                    "total_isolated": diff.population_change.get("after_isolated"),
                }],
            )
            new_alerts.append(alert)

        # Rule 3: HIGH_CONFIDENCE_ROAD_BLOCKAGE (MEDIUM severity)
        for rc in diff.road_changes:
            if rc.get("change_type") == "ROAD_BLOCKED":
                alert = self._create_or_update_alert(
                    alert_type="HIGH_CONFIDENCE_ROAD_BLOCKAGE",
                    severity="MEDIUM",
                    affected_entity_id=rc["segment_id"],
                    affected_entity_name=f"Road Segment {rc['segment_id']}",
                    source_version=diff.to_version,
                    evidence=[{
                        "segment_id": rc["segment_id"],
                        "change_type": "ROAD_BLOCKED",
                    }],
                )
                new_alerts.append(alert)

        # Rule 4: CORRIDOR_RESTORED (LOW severity)
        for rc in diff.road_changes:
            if rc.get("change_type") == "ROAD_REOPENED":
                alert = self._create_or_update_alert(
                    alert_type="CORRIDOR_RESTORED",
                    severity="LOW",
                    affected_entity_id=rc["segment_id"],
                    affected_entity_name=f"Road Segment {rc['segment_id']}",
                    source_version=diff.to_version,
                    evidence=[{
                        "segment_id": rc["segment_id"],
                        "change_type": "ROAD_REOPENED",
                    }],
                )
                new_alerts.append(alert)

        # Rule 5: PRIORITY_CHANGED (HIGH severity)
        if diff.priority_changed:
            alert = self._create_or_update_alert(
                alert_type="PRIORITY_CHANGED",
                severity="HIGH",
                affected_entity_id="decision_engine_ranking",
                affected_entity_name="Operational Intervention Priority",
                source_version=diff.to_version,
                evidence=[{
                    "previous_top": diff.previous_top_candidate,
                    "current_top": diff.current_top_candidate,
                    "reason": diff.priority_change_reason or "New validated evidence altered accessibility ranking",
                }],
            )
            new_alerts.append(alert)

        # Rule 6: OBSERVATION_CONFLICT (MEDIUM severity)
        if current_state.unresolved_conflicts > 0:
            alert = self._create_or_update_alert(
                alert_type="OBSERVATION_CONFLICT",
                severity="MEDIUM",
                affected_entity_id="reconciliation_pipeline",
                affected_entity_name="Observation Reconciliation Pipeline",
                source_version=diff.to_version,
                evidence=[{
                    "unresolved_conflicts": current_state.unresolved_conflicts,
                }],
            )
            new_alerts.append(alert)

        # Rule 7: STALE_CRITICAL_OBSERVATION (MEDIUM severity)
        if observations:
            now_dt = datetime.now(timezone.utc)
            for obs in observations:
                # Check if observation is older than 2 hours (7200s) and is ROAD_BLOCKED or FLOOD_DEPTH
                age_s = (now_dt - (obs.timestamp if obs.timestamp.tzinfo else obs.timestamp.replace(tzinfo=timezone.utc))).total_seconds()
                if age_s > 7200 and obs.observation_type in ("ROAD_BLOCKED", "FLOOD_DEPTH") and obs.status in ("accepted", "reconciled"):
                    alert = self._create_or_update_alert(
                        alert_type="STALE_CRITICAL_OBSERVATION",
                        severity="MEDIUM",
                        affected_entity_id=obs.observation_id,
                        affected_entity_name=f"Observation {obs.observation_id}",
                        source_version=diff.to_version,
                        evidence=[{
                            "observation_id": obs.observation_id,
                            "age_seconds": age_s,
                            "observation_type": obs.observation_type,
                        }],
                    )
                    new_alerts.append(alert)

        # Auto-resolve rules: If hospital becomes accessible again, resolve corresponding CRITICAL_HOSPITAL_ACCESS_LOSS alert
        for hc in diff.hospital_changes:
            if hc.get("before_status") == "INACCESSIBLE" and hc.get("after_status") == "ACCESSIBLE":
                self._auto_resolve_alert("CRITICAL_HOSPITAL_ACCESS_LOSS", hc["facility_id"])

        return new_alerts

    def _create_or_update_alert(
        self,
        alert_type: str,
        severity: str,
        affected_entity_id: str,
        affected_entity_name: Optional[str],
        source_version: int,
        evidence: List[Dict[str, Any]],
    ) -> OperationalAlert:
        """
        Deduplicates alerts by (affected_entity_id, alert_type).
        If an active alert (NEW or ACKNOWLEDGED) exists, appends evidence without creating duplicate.
        """
        for alert in self.alerts.values():
            if alert.affected_entity_id == affected_entity_id and alert.type == alert_type and alert.status in ("NEW", "ACKNOWLEDGED"):
                # Append evidence & update source version
                alert.evidence.extend(evidence)
                alert.source_state_version = source_version
                logger.info(f"Deduplicated alert {alert.alert_id} for {affected_entity_id} ({alert_type})")
                return alert

        alert_id = f"ALERT-{uuid.uuid4().hex[:8].upper()}"
        alert = OperationalAlert(
            alert_id=alert_id,
            type=alert_type,
            severity=severity,
            source_state_version=source_version,
            affected_entity_id=affected_entity_id,
            affected_entity_name=affected_entity_name or affected_entity_id,
            evidence=evidence,
            status="NEW",
        )
        self.alerts[alert_id] = alert
        logger.info(f"Created new operational alert {alert_id} [{severity}] ({alert_type})")
        return alert

    def _auto_resolve_alert(self, alert_type: str, affected_entity_id: str):
        for alert in self.alerts.values():
            if alert.affected_entity_id == affected_entity_id and alert.type == alert_type and alert.status != "RESOLVED":
                alert.status = "RESOLVED"
                alert.operator_action = {
                    "operator": "SYSTEM_DETERMINISTIC",
                    "action": "AUTO_RESOLVED",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "comment": "Condition restored deterministically by disaster state engine",
                }
                logger.info(f"Auto-resolved alert {alert.alert_id} ({alert_type})")

    def apply_operator_action(
        self,
        alert_id: str,
        action: str,
        operator_id: str = "Operator-01",
        comment: Optional[str] = None,
    ) -> OperationalAlert:
        """
        Applies human operator action: ACKNOWLEDGE, RESOLVE, DISMISS.
        """
        if alert_id not in self.alerts:
            raise KeyError(f"Alert ID '{alert_id}' not found.")
        alert = self.alerts[alert_id]

        action_upper = action.upper().strip()
        if action_upper not in ("ACKNOWLEDGE", "RESOLVE", "DISMISS"):
            raise ValueError(f"Invalid operator action '{action}'. Must be ACKNOWLEDGE, RESOLVE, or DISMISS.")

        if action_upper == "ACKNOWLEDGE":
            alert.status = "ACKNOWLEDGED"
        elif action_upper == "RESOLVE":
            alert.status = "RESOLVED"
        elif action_upper == "DISMISS":
            alert.status = "DISMISSED"

        alert.operator_action = {
            "operator": operator_id,
            "action": action_upper,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "comment": comment or "",
        }
        logger.info(f"Operator '{operator_id}' performed {action_upper} on alert {alert_id}")
        return alert


class DisasterStateManager:
    """
    Manages monotonically increasing DisasterState versions, state history,
    atomic state transitions with rollback, internal operational events,
    and observation-to-state provenance traceability.
    """

    def __init__(self, scenario_id: str = "chennai_michaung_default"):
        self.scenario_id = scenario_id
        self.current_version: int = 1
        self.history: Dict[int, DisasterState] = {}
        self.alert_engine = AlertEngine()
        self.events: List[OperationalEvent] = []

        # Create initial DisasterState v1
        initial_state = DisasterState(
            scenario_id=scenario_id,
            state_version=1,
            generated_at=datetime.now(timezone.utc),
            valid_from=datetime.now(timezone.utc),
            hazard_state={"scenario": "baseline", "water_level_m": 0.0},
            affected_segments=[],
            affected_facilities=[
                {"facility_id": "FAC-01", "name": "Rajiv Gandhi Govt General Hospital", "status": "ACCESSIBLE", "travel_time_min": 11.2, "baseline_min": 11.2, "confidence": 1.0},
                {"facility_id": "FAC-02", "name": "Stanley Medical College Hospital", "status": "ACCESSIBLE", "travel_time_min": 14.5, "baseline_min": 14.5, "confidence": 1.0},
                {"facility_id": "FAC-03", "name": "Kilpauk Medical College Hospital", "status": "ACCESSIBLE", "travel_time_min": 12.8, "baseline_min": 12.8, "confidence": 1.0},
                {"facility_id": "FAC-04", "name": "Government Royapettah Hospital", "status": "ACCESSIBLE", "travel_time_min": 10.1, "baseline_min": 10.1, "confidence": 1.0},
                {"facility_id": "FAC-05", "name": "Government Peripheral Hospital Teynampet", "status": "ACCESSIBLE", "travel_time_min": 15.3, "baseline_min": 15.3, "confidence": 1.0},
                {"facility_id": "FAC-06", "name": "Monomani Trauma Center", "status": "ACCESSIBLE", "travel_time_min": 18.0, "baseline_min": 18.0, "confidence": 1.0},
            ],
            affected_population={"total": 477000, "accessible": 477000, "isolated": 0, "delta_isolated": 0},
            confidence_summary={"confirmed": 100, "probable": 0, "uncertain": 0, "conflicting": 0},
            provenance_summary={"initialization": "Calibrated baseline state"},
        )
        self.history[1] = initial_state
        self.current_state = initial_state
        self._record_event("STATE_RECOMPUTED", 1, {"description": "Initial state v1 created"})

    def commit_transition(
        self,
        hazard_state: Dict[str, Any],
        affected_segments: List[str],
        affected_facilities: List[Dict[str, Any]],
        affected_population: Dict[str, Any],
        observations_count: int = 0,
        high_confidence_obs: int = 0,
        unresolved_conflicts: int = 0,
        active_interventions: Optional[List[str]] = None,
        completed_interventions: Optional[List[str]] = None,
        confidence_summary: Optional[Dict[str, int]] = None,
        provenance_summary: Optional[Dict[str, Any]] = None,
        previous_top_candidate: Optional[str] = None,
        current_top_candidate: Optional[str] = None,
        priority_change_reason: Optional[str] = None,
        observations: Optional[List[InfrastructureObservation]] = None,
    ) -> Tuple[DisasterState, StateDiff]:
        """
        Atomic state transition.
        Calculates invariants; if valid, commits v_{N+1}, computes diff, evaluates alerts,
        and logs event. If invariant fails, rolls back.
        """
        state_before = self.current_state
        next_version = state_before.state_version + 1

        # Invariant check: Population conservation
        tot = affected_population.get("total", 477000)
        acc = affected_population.get("accessible", 0)
        iso = affected_population.get("isolated", 0)
        if acc + iso != tot:
            err_msg = f"Population invariant violation: accessible ({acc}) + isolated ({iso}) != total ({tot})"
            logger.error(f"Atomic transition failed: {err_msg}. Rolling back to v{state_before.state_version}.")
            self._record_event("STATE_RECOMPUTATION_FAILED", state_before.state_version, {"error": err_msg})
            raise ValueError(err_msg)

        new_state = DisasterState(
            scenario_id=self.scenario_id,
            state_version=next_version,
            generated_at=datetime.now(timezone.utc),
            valid_from=datetime.now(timezone.utc),
            hazard_state=hazard_state,
            affected_segments=affected_segments,
            affected_facilities=affected_facilities,
            affected_population=affected_population,
            observations_count=observations_count,
            high_confidence_observations=high_confidence_obs,
            unresolved_conflicts=unresolved_conflicts,
            active_interventions=active_interventions or [],
            completed_interventions=completed_interventions or [],
            confidence_summary=confidence_summary or {"confirmed": 0, "probable": 0, "uncertain": 0, "conflicting": 0},
            provenance_summary=provenance_summary or {},
        )

        # Compute Diff
        diff = ChangeDetector.detect_state_changes(
            before=state_before,
            after=new_state,
            previous_top_candidate=previous_top_candidate,
            current_top_candidate=current_top_candidate,
            priority_change_reason=priority_change_reason,
        )

        # Evaluate Alerts
        new_alerts = self.alert_engine.evaluate_state_diff(diff, new_state, observations)
        diff.new_alerts = [a.alert_id for a in new_alerts]

        # Commit state to history & update current
        self.history[next_version] = new_state
        self.current_state = new_state
        self.current_version = next_version

        # Record event
        self._record_event(
            "STATE_RECOMPUTED",
            next_version,
            {
                "from_version": state_before.state_version,
                "to_version": next_version,
                "road_changes_count": len(diff.road_changes),
                "hospital_changes_count": len(diff.hospital_changes),
                "isolated_delta": diff.population_change.get("isolated_delta"),
            },
        )

        logger.info(f"Committed DisasterState v{next_version} (Diff: {len(diff.road_changes)} road changes, {len(diff.hospital_changes)} facility changes)")
        return new_state, diff

    def get_diff(self, from_version: int, to_version: int) -> StateDiff:
        if from_version not in self.history:
            raise KeyError(f"State version {from_version} not found in history.")
        if to_version not in self.history:
            raise KeyError(f"State version {to_version} not found in history.")
        return ChangeDetector.detect_state_changes(self.history[from_version], self.history[to_version])

    def get_traceability(self, entity_id: str, observation_pipeline: Optional[Any] = None) -> Dict[str, Any]:
        """
        Returns end-to-end traceability for any operational entity or value.
        Connects: Current Value <- State Version <- Reconciliation <- Observations <- Raw Evidence
        """
        curr = self.current_state

        trace_data: Dict[str, Any] = {
            "entity_id": entity_id,
            "current_state_version": curr.state_version,
            "timestamp": curr.generated_at.isoformat(),
            "provenance_chain": [],
        }

        # Case 1: Road Segment ID
        if entity_id in curr.affected_segments:
            trace_data["status"] = "BLOCKED"
            trace_data["provenance_chain"].append({
                "step": "STATE_SNAPSHOT",
                "version": curr.state_version,
                "detail": f"Segment {entity_id} is marked disabled in disaster state graph",
            })
            if observation_pipeline:
                matching_obs = [
                    obs for obs in observation_pipeline.observations.values()
                    if obs.affected_segment_id == entity_id or entity_id in obs.affected_node_ids
                ]
                obs_list = []
                for o in matching_obs:
                    obs_list.append({
                        "observation_id": o.observation_id,
                        "source": o.source,
                        "type": o.observation_type,
                        "confidence": o.confidence,
                        "timestamp": o.timestamp.isoformat(),
                        "raw_text": o.raw_text,
                        "provenance": o.provenance,
                    })
                trace_data["supporting_observations"] = obs_list
                trace_data["provenance_chain"].append({
                    "step": "GROUND_RECONCILIATION",
                    "detail": f"Reconciled from {len(matching_obs)} ground observations",
                })
        elif entity_id.startswith("FAC-") or any(f["facility_id"] == entity_id for f in curr.affected_facilities):
            fac = next((f for f in curr.affected_facilities if f["facility_id"] == entity_id), None)
            if fac:
                trace_data["status"] = fac.get("status")
                trace_data["travel_time_min"] = fac.get("travel_time_min")
                trace_data["baseline_min"] = fac.get("baseline_min")
                trace_data["provenance_chain"].append({
                    "step": "DETERMINISTIC_DIJKSTRA",
                    "version": curr.state_version,
                    "detail": f"Reverse Multi-Source Dijkstra calculated travel time {fac.get('travel_time_min')} min from facility node",
                })
        elif entity_id in ("population", "population_gcc", "isolated_population"):
            trace_data["status"] = f"{curr.affected_population.get('isolated', 0)} isolated"
            trace_data["provenance_chain"].append({
                "step": "WARD_ACCESSIBILITY_AGGREGATION",
                "version": curr.state_version,
                "detail": f"Summed isolated population across unreachable zone centroids on current graph",
            })
            trace_data["provenance_chain"].append({
                "step": "ROAD_NETWORK_GRAPH",
                "detail": f"Graph has {len(curr.affected_segments)} disabled segments causing disconnection",
            })
        else:
            trace_data["status"] = "UNKNOWN_ENTITY"
            trace_data["provenance_chain"].append({
                "step": "GENERAL_STATE",
                "version": curr.state_version,
                "detail": f"Entity {entity_id} query resolved against state v{curr.state_version}",
            })

        return trace_data

    def _record_event(self, event_type: str, state_version: int, details: Dict[str, Any]):
        evt = OperationalEvent(
            event_id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            state_version=state_version,
            details=details,
        )
        self.events.append(evt)
        # Bounded event log size to avoid memory growth
        if len(self.events) > 1000:
            self.events = self.events[-1000:]
        logger.info(f"Recorded event {evt.event_id} ({event_type}) for state v{state_version}")
