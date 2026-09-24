"""
Cyclone Twin Network Engine
Maintains the road multi-directed network graph, edge states, and shortest-path queries.
"""

import heapq
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import networkx as nx
from shapely.geometry import LineString


class NetworkEngine:
    """
    Core graph simulation engine using NetworkX MultiDiGraph.
    Tracks active and disabled road physical segments, calculates multi-source
    Dijkstra travel times on forward and reversed graphs, and guards against parallel edge traps.
    """

    def __init__(self, graph: Optional[nx.MultiDiGraph] = None):
        self.graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self.disabled_segments: Set[str] = set()
        self.valid_segment_ids: Set[str] = set()
        self.segment_to_edges: Dict[str, List[Tuple[str, str, int]]] = {}
        self.edge_to_segment: Dict[Tuple[str, str, int], str] = {}

        if graph is not None:
            self.set_graph(graph)

    def set_graph(self, graph: nx.MultiDiGraph) -> None:
        """
        Loads and indexes graph, normalizing node IDs to strings and registering
        all physical segments and geometries.
        """
        # Create a new MultiDiGraph with string node IDs
        normalized_graph = nx.MultiDiGraph()
        normalized_graph.graph.update(graph.graph)

        for node, data in graph.nodes(data=True):
            normalized_graph.add_node(str(node), **data)

        self.segment_to_edges.clear()
        self.edge_to_segment.clear()
        self.valid_segment_ids.clear()
        self.disabled_segments.clear()

        for u, v, key, data in graph.edges(keys=True, data=True):
            u_str, v_str = str(u), str(v)
            edge_data = dict(data)

            # Ensure travel_time exists
            if "travel_time" not in edge_data:
                length = float(edge_data.get("length", 100.0))
                speed_kph = float(edge_data.get("speed_kph", 30.0))
                edge_data["travel_time"] = length / (speed_kph * 1000.0 / 3600.0)

            # TEST 20: Missing edge geometry reconstructed from node coordinates
            if "geometry" not in edge_data or edge_data["geometry"] is None:
                u_node = normalized_graph.nodes.get(u_str, {})
                v_node = normalized_graph.nodes.get(v_str, {})
                u_x = u_node.get("x", u_node.get("lon"))
                u_y = u_node.get("y", u_node.get("lat"))
                v_x = v_node.get("x", v_node.get("lon"))
                v_y = v_node.get("y", v_node.get("lat"))
                if u_x is not None and u_y is not None and v_x is not None and v_y is not None:
                    edge_data["geometry"] = LineString([(float(u_x), float(u_y)), (float(v_x), float(v_y))])

            # Ensure physical_segment_id
            seg_id = str(edge_data.get("physical_segment_id") or f"seg_{u_str}_{v_str}_{key}")
            edge_data["physical_segment_id"] = seg_id

            normalized_graph.add_edge(u_str, v_str, key=key, **edge_data)

            self.valid_segment_ids.add(seg_id)
            self.segment_to_edges.setdefault(seg_id, []).append((u_str, v_str, key))
            self.edge_to_segment[(u_str, v_str, key)] = seg_id

        self.graph = normalized_graph

    def disable_segments(self, segment_ids: Iterable[str], validate: bool = True) -> int:
        """
        Disables physical segments.
        TEST 15: Invalid segment ID raises AssertionError when validate=True.
        """
        disabled_count = 0
        for seg_id in segment_ids:
            seg_str = str(seg_id)
            if validate:
                assert seg_str in self.valid_segment_ids, f"Invalid segment ID: {seg_str}"
            if seg_str in self.valid_segment_ids and seg_str not in self.disabled_segments:
                self.disabled_segments.add(seg_str)
                disabled_count += 1
        return disabled_count

    def restore_segments(self, segment_ids: Iterable[str]) -> int:
        """Restores specified physical segments."""
        restored = 0
        for seg_id in segment_ids:
            seg_str = str(seg_id)
            if seg_str in self.disabled_segments:
                self.disabled_segments.remove(seg_str)
                restored += 1
        return restored

    def restore_all(self) -> int:
        """Restores all disabled segments."""
        count = len(self.disabled_segments)
        self.disabled_segments.clear()
        return count

    def is_edge_active(self, u: str, v: str, key: int) -> bool:
        """Returns True if the edge exists and its physical segment is not disabled."""
        u_str, v_str = str(u), str(v)
        if not self.graph.has_edge(u_str, v_str, key):
            return False
        seg_id = self.edge_to_segment.get((u_str, v_str, key))
        return seg_id is not None and seg_id not in self.disabled_segments

    def _active_weight(self, u: str, v: str, edge_dict: Optional[Dict[Any, Dict[str, Any]]] = None) -> Optional[float]:
        """
        Inspects all parallel edges between u and v.
        1. Inspects every parallel edge
        2. Ignores disabled physical segments
        3. Chooses minimum active travel_time
        4. Returns None if every parallel edge is disabled
        (TEST 16)
        """
        u_str, v_str = str(u), str(v)
        if edge_dict is None:
            if not self.graph.has_edge(u_str, v_str):
                return None
            edge_dict = self.graph[u_str][v_str]

        min_time: Optional[float] = None
        for key, data in edge_dict.items():
            seg_id = data.get("physical_segment_id") or self.edge_to_segment.get((u_str, v_str, key))
            if seg_id in self.disabled_segments:
                continue  # Disabled segment

            t = float(data.get("travel_time", 0.0))
            if min_time is None or t < min_time:
                min_time = t

        return min_time

    def community_to_hospital_times(
        self,
        community_nodes: Iterable[str],
        active_hospital_nodes: Iterable[str],
        cutoff: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Calculates travel time from communities to active hospitals using multi-source
        Dijkstra on the REVERSED graph.
        Guards empty source sets (TEST 18: returns {} if hospitals are empty).
        """
        h_nodes = [str(n) for n in active_hospital_nodes if str(n) in self.graph]
        if not h_nodes:
            return {}

        c_set = {str(n) for n in community_nodes}
        if not c_set:
            return {}

        # Reverse graph edge lookup for multi-source Dijkstra:
        # In G^R, an edge from v to u has the weight of u -> v in G.
        # So when traversing out from hospital node h in G^R, we look at incoming edges to h in G.
        # NetworkX in_edges(u) gives (w, u, key, data) where w -> u in G.
        # Dijkstra priority queue: (dist, node)
        distances: Dict[str, float] = {h: 0.0 for h in h_nodes}
        heap: List[Tuple[float, str]] = [(0.0, h) for h in h_nodes]
        visited: Set[str] = set()

        while heap:
            d, curr = heapq.heappop(heap)
            if curr in visited:
                continue
            visited.add(curr)

            if cutoff is not None and d > cutoff:
                continue

            # Look at incoming edges to curr in forward graph G (outgoing in reversed graph G^R)
            # predecessors of curr: nodes `pred` such that `pred -> curr` in G
            for pred in self.graph.predecessors(curr):
                weight = self._active_weight(pred, curr, self.graph[pred][curr])
                if weight is None:
                    continue  # All parallel edges between pred -> curr are disabled

                new_d = d + weight
                if cutoff is not None and new_d > cutoff:
                    continue

                if new_d < distances.get(pred, float("inf")):
                    distances[pred] = new_d
                    heapq.heappush(heap, (new_d, pred))

        # Return distances only for the requested community nodes that were reached
        return {c: distances[c] for c in c_set if c in distances}

    def hub_to_hospital_times(
        self,
        hub_nodes: Iterable[str],
        active_hospital_nodes: Iterable[str],
        cutoff: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Forward graph Dijkstra from hubs to hospitals.
        Guards empty source sets.
        """
        hubs = [str(n) for n in hub_nodes if str(n) in self.graph]
        hospitals = {str(n) for n in active_hospital_nodes if str(n) in self.graph}

        if not hubs or not hospitals:
            return {}

        results: Dict[str, float] = {}

        # For each hub, find minimum time to any active hospital
        for hub in hubs:
            distances: Dict[str, float] = {hub: 0.0}
            heap: List[Tuple[float, str]] = [(0.0, hub)]
            visited: Set[str] = set()
            found_min: Optional[float] = None

            while heap:
                d, curr = heapq.heappop(heap)
                if curr in visited:
                    continue
                visited.add(curr)

                if curr in hospitals:
                    if found_min is None or d < found_min:
                        found_min = d
                    break  # Found nearest hospital for this hub

                if cutoff is not None and d > cutoff:
                    continue

                for succ in self.graph.successors(curr):
                    weight = self._active_weight(curr, succ, self.graph[curr][succ])
                    if weight is None:
                        continue

                    new_d = d + weight
                    if cutoff is not None and new_d > cutoff:
                        continue

                    if new_d < distances.get(succ, float("inf")):
                        distances[succ] = new_d
                        heapq.heappush(heap, (new_d, succ))

            if found_min is not None:
                results[hub] = found_min

        return results
