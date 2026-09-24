"""
Cyclone Twin Corridor Clustering Engine
Groups disabled road segments into connected restoration corridors.
"""

from typing import Any, Dict, List, Set, Tuple
import networkx as nx
from shapely.geometry import mapping, MultiLineString, LineString
from .models import Corridor


class CorridorEngine:
    """
    Builds restoration corridors by clustering contiguous disabled road segments
    into connected graph components.
    """

    @staticmethod
    def cluster_disabled_segments_into_corridors(
        graph: nx.MultiDiGraph,
        disabled_segment_ids: Set[str],
    ) -> List[Corridor]:
        """
        Groups disabled edges into connected components using an undirected graph.
        Ignores zero-edge components.
        Generates deterministic IDs and computes length and road classes.
        """
        if not disabled_segment_ids:
            return []

        # Build undirected graph of disabled segments
        H = nx.Graph()

        # Collect disabled edges
        disabled_edges: List[Tuple[str, str, int, Dict[str, Any]]] = []
        for u, v, key, data in graph.edges(keys=True, data=True):
            seg_id = str(data.get("physical_segment_id") or f"seg_{u}_{v}_{key}")
            if seg_id in disabled_segment_ids:
                disabled_edges.append((str(u), str(v), key, data))
                H.add_node(str(u))
                H.add_node(str(v))
                H.add_edge(str(u), str(v), key=key, segment_id=seg_id, data=data)

        if H.number_of_edges() == 0:
            return []

        # Find connected components in H
        raw_components = list(nx.connected_components(H))

        # Build corridor candidates
        corridors: List[Corridor] = []
        temp_clusters = []

        for comp_nodes in raw_components:
            comp_subgraph = H.subgraph(comp_nodes)
            if comp_subgraph.number_of_edges() == 0:
                continue

            comp_edges: List[Tuple[str, str, int]] = []
            comp_seg_ids: Set[str] = set()
            total_length: float = 0.0
            road_classes: Set[str] = set()
            lines: List[LineString] = []

            for u, v, k, d in disabled_edges:
                if u in comp_nodes and v in comp_nodes:
                    comp_edges.append((u, v, k))
                    seg_id = str(d.get("physical_segment_id") or f"seg_{u}_{v}_{k}")
                    comp_seg_ids.add(seg_id)
                    total_length += float(d.get("length", 100.0))
                    hw = d.get("highway")
                    if hw:
                        if isinstance(hw, list):
                            road_classes.update(hw)
                        else:
                            road_classes.add(str(hw))
                    geom = d.get("geometry")
                    if geom is not None and isinstance(geom, LineString):
                        lines.append(geom)

            if not comp_seg_ids:
                continue

            # Deterministic sorting key for cluster ordering
            sorted_segs = sorted(list(comp_seg_ids))
            first_seg = sorted_segs[0]

            temp_clusters.append({
                "first_seg": first_seg,
                "edges": comp_edges,
                "seg_ids": sorted_segs,
                "length": total_length,
                "road_classes": sorted(list(road_classes)),
                "lines": lines,
            })

        # Sort clusters deterministically by their initial segment ID
        temp_clusters.sort(key=lambda c: c["first_seg"])

        for idx, item in enumerate(temp_clusters):
            corr_id = f"corridor_{idx + 1:02d}"
            geom_dict = None
            if item["lines"]:
                if len(item["lines"]) == 1:
                    geom_dict = mapping(item["lines"][0])
                else:
                    geom_dict = mapping(MultiLineString(item["lines"]))

            corridor = Corridor(
                corridor_id=corr_id,
                edge_keys=item["edges"],
                physical_segment_ids=item["seg_ids"],
                total_length_m=round(item["length"], 2),
                road_classes=item["road_classes"],
                geometry=geom_dict,
            )
            corridors.append(corridor)

        return corridors
