"""
Cyclone Twin Realistic Chennai Road Multigraph & Landmark Dataset
Generates an operational MultiDiGraph of Greater Chennai Corporation (GCC)
arterial corridors, emergency health facilities, and community populations.
"""

from typing import Dict, List, Tuple
import networkx as nx
from pyproj import Transformer
from shapely.geometry import LineString
from .models import Community, HealthFacility

# WGS84 -> UTM 43N (Chennai)
_TRANSFORMER_TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)


def project_lon_lat(lon: float, lat: float) -> Tuple[float, float]:
    """Projects (longitude, latitude) in WGS84 to (easting, northing) in EPSG:32643."""
    x, y = _TRANSFORMER_TO_UTM.transform(lon, lat)
    return round(x, 2), round(y, 2)


def get_chennai_communities() -> List[Community]:
    """
    Standard GCC community populations with real Chennai coordinates and populations.
    """
    raw_communities = [
        # Velachery: Low-lying high-density marshland overflow basin
        {"id": "COMM_VELACHERY", "name": "Velachery Ward 178", "pop": 48000, "lon": 80.2185, "lat": 12.9792},
        # Saidapet: Adyar river basin, low-elevation residential area
        {"id": "COMM_SAIDAPET", "name": "Saidapet West Ward 141", "pop": 54000, "lon": 80.2220, "lat": 13.0210},
        # Jafferkhanpet: Adyar river corridor vulnerable to backflow
        {"id": "COMM_JAFFERKHANPET", "name": "Jafferkhanpet Ward 138", "pop": 36000, "lon": 80.2045, "lat": 13.0255},
        # Kotturpuram: South bank Adyar, adjacent to major bridge
        {"id": "COMM_KOTTURPURAM", "name": "Kotturpuram Ward 170", "pop": 29000, "lon": 80.2435, "lat": 13.0165},
        # Madipakkam: Downstream lake overflow vulnerability
        {"id": "COMM_MADIPAKKAM", "name": "Madipakkam Ward 188", "pop": 41000, "lon": 80.1980, "lat": 12.9640},
        # Guindy: Industrial and residential junction
        {"id": "COMM_GUINDY", "name": "Guindy Thiru-Vi-Ka Ward 168", "pop": 37000, "lon": 80.2120, "lat": 13.0075},
        # T. Nagar: High density commercial/residential core
        {"id": "COMM_TNAGAR", "name": "T. Nagar Ward 117", "pop": 68000, "lon": 80.2330, "lat": 13.0415},
        # Mylapore: Historic coastal urban ward
        {"id": "COMM_MYLAPORE", "name": "Mylapore Ward 124", "pop": 58000, "lon": 80.2670, "lat": 13.0330},
        # Sholinganallur: Outer IT corridor residential node
        {"id": "COMM_SHOLINGANALLUR", "name": "Sholinganallur Ward 197", "pop": 62000, "lon": 80.2280, "lat": 12.9010},
        # Koyambedu: Transport hub and residential area
        {"id": "COMM_KOYAMBEDU", "name": "Koyambedu Ward 127", "pop": 44000, "lon": 80.1940, "lat": 13.0690},
    ]

    communities: List[Community] = []
    for c in raw_communities:
        communities.append(
            Community(
                id=c["id"],
                name=c["name"],
                population=c["pop"],
                coords=(c["lon"], c["lat"]),
            )
        )
    return communities


def get_chennai_health_facilities() -> List[HealthFacility]:
    """
    Major tertiary and emergency health facilities across Chennai.
    """
    raw_facilities = [
        # Fortis Malar Hospital (Adyar)
        {"id": "FAC_FORTIS_MALAR", "name": "Fortis Malar Hospital Adyar", "beds": 180, "lon": 80.2580, "lat": 13.0060, "power": True},
        # MIOT International (Manapakkam / Mount-Poonamallee Rd)
        {"id": "FAC_MIOT", "name": "MIOT International Manapakkam", "beds": 500, "lon": 80.1830, "lat": 13.0235, "power": True},
        # Apollo Hospital (Greams Road, Thousand Lights)
        {"id": "FAC_APOLLO_GREAMS", "name": "Apollo Hospitals Greams Road", "beds": 600, "lon": 80.2512, "lat": 13.0592, "power": True},
        # Rajiv Gandhi Govt General Hospital (Chennai Central)
        {"id": "FAC_RGGGH", "name": "Rajiv Gandhi Govt General Hospital", "beds": 1500, "lon": 80.2785, "lat": 13.0818, "power": True},
        # Gleneagles Health City (Perumbakkam / OMR)
        {"id": "FAC_GLENEAGLES", "name": "Gleneagles Health City Perumbakkam", "beds": 450, "lon": 80.2010, "lat": 12.9050, "power": True},
        # Kilpauk Medical College Hospital
        {"id": "FAC_KMC", "name": "Govt Kilpauk Medical College Hospital", "beds": 750, "lon": 80.2415, "lat": 13.0789, "power": True},
    ]

    facilities: List[HealthFacility] = []
    for f in raw_facilities:
        facilities.append(
            HealthFacility(
                id=f["id"],
                name=f["name"],
                beds=f["beds"],
                coords=(f["lon"], f["lat"]),
                power_status=f["power"],
            )
        )
    return facilities


def build_mock_chennai_graph() -> nx.MultiDiGraph:
    """
    Constructs a calibrated, realistic MultiDiGraph of Chennai's arterial emergency network.
    Includes parallel edges, bridges, tunnels, and arterial segments crossing flood-prone corridors.
    """
    G = nx.MultiDiGraph()
    G.graph["crs"] = "EPSG:32643"
    G.graph["name"] = "Greater Chennai Corporation Emergency Arterial Network"

    # Key arterial intersection nodes in Chennai (WGS84 lon, lat)
    nodes_wgs84 = {
        "N_CENTRAL": (80.2760, 13.0820),       # Chennai Central / Park Town
        "N_OMANDURAR": (80.2720, 13.0670),     # Omandurar Estate / Anna Salai
        "N_THOUSAND_LIGHTS": (80.2520, 13.0580), # Mount Road / Greams Rd
        "N_TEYNAMPET": (80.2450, 13.0420),     # Teynampet / Anna Salai
        "N_NANDANAM": (80.2380, 13.0300),      # Nandanam Junction
        "N_SAIDAPET_NORTH": (80.2240, 13.0220), # Saidapet / North Adyar Bank
        "N_SAIDAPET_SOUTH": (80.2210, 13.0180), # Maraimalai Adigal Bridge South
        "N_GUINDY_KATHIPARA": (80.2050, 13.0070), # Kathipara Cloverleaf
        "N_MANAPAKKAM": (80.1820, 13.0230),    # Mount-Poonamallee / MIOT
        "N_PORUR": (80.1580, 13.0340),         # Porur Junction
        "N_KOYAMBEDU": (80.1930, 13.0680),     # Koyambedu Junction / Inner Ring
        "N_VADAPALANI": (80.2120, 13.0510),    # Vadapalani / 100ft Rd
        "N_JAFFERKHANPET": (80.2060, 13.0260), # Inner Ring at Adyar River
        "N_VELACHERY_CENTRAL": (80.2180, 12.9790), # Velachery Vijayanagar
        "N_VELACHERY_CHECKPOST": (80.2160, 12.9980), # Velachery / Guindy Link
        "N_MADIPAKKAM": (80.1970, 12.9630),    # Madipakkam Lake Link
        "N_KOTTURPURAM": (80.2430, 13.0160),   # Kotturpuram Bridge
        "N_ADYAR_GATE": (80.2520, 13.0150),    # TTK Rd / Adyar Gate
        "N_ADYAR_CENTRAL": (80.2570, 13.0050), # Adyar Depot / Fortis Malar
        "N_TIDEL_PARK": (80.2490, 12.9880),    # Tidel Park / OMR Entry
        "N_SHOLINGANALLUR": (80.2280, 12.9000),# OMR Sholinganallur Junction
        "N_PERUMBAKKAM": (80.2000, 12.9040),   # Perumbakkam / Gleneagles
        "N_MYLAPORE_LUZ": (80.2660, 13.0340),  # Luz Church Rd
        "N_SANTHOME": (80.2780, 13.0330),      # Santhome High Rd
        "N_KILPAUK": (80.2410, 13.0780),       # Kilpauk Medical Junction
    }

    # Add nodes with WGS84 and projected UTM 43N coordinates
    for node_id, (lon, lat) in nodes_wgs84.items():
        x_m, y_m = project_lon_lat(lon, lat)
        G.add_node(
            str(node_id),
            lon=lon,
            lat=lat,
            x=x_m,
            y=y_m,
        )

    # Edge definitions (u, v, key, physical_segment_id, road_name, length_m, speed_kph, bridge, tunnel, layer, oneway)
    # Using bidirectional corridors where appropriate
    raw_edges = [
        # Anna Salai Arterial Corridor (Northern section: Central -> Nandanam)
        ("N_CENTRAL", "N_OMANDURAR", 0, "seg_anna_01", "Anna Salai (North)", 1800, 45, "no", "no", 0, False),
        ("N_OMANDURAR", "N_THOUSAND_LIGHTS", 0, "seg_anna_02", "Anna Salai (Thousand Lights)", 2300, 40, "no", "no", 0, False),
        ("N_THOUSAND_LIGHTS", "N_TEYNAMPET", 0, "seg_anna_03", "Anna Salai (Teynampet)", 1900, 40, "no", "no", 0, False),
        ("N_TEYNAMPET", "N_NANDANAM", 0, "seg_anna_04", "Anna Salai (Nandanam)", 1400, 45, "no", "no", 0, False),

        # CORRIDOR B: Crucial Saidapet Adyar River Crossing (HIGH NETWORK CRITICALITY)
        # Low-elevation causeway / surface road vulnerable to Adyar river flooding
        ("N_NANDANAM", "N_SAIDAPET_NORTH", 0, "seg_saidapet_01", "Anna Salai Saidapet Approach", 1600, 35, "no", "no", 0, False),
        ("N_SAIDAPET_NORTH", "N_SAIDAPET_SOUTH", 0, "seg_saidapet_bridge_low", "Saidapet Low Causeways", 850, 30, "no", "no", 0, False),
        ("N_SAIDAPET_SOUTH", "N_GUINDY_KATHIPARA", 0, "seg_saidapet_02", "Guindy Anna Salai Link", 1900, 45, "no", "no", 0, False),

        # High Elevated Bridge bypass over Saidapet (parallel edge demonstrating bridge/layer rule)
        ("N_SAIDAPET_NORTH", "N_SAIDAPET_SOUTH", 1, "seg_saidapet_elevated", "Saidapet Metro Elevated Span", 850, 60, "yes", "no", 1, False),

        # Kathipara Junction to MIOT Hospital / Manapakkam & Porur
        ("N_GUINDY_KATHIPARA", "N_MANAPAKKAM", 0, "seg_mount_poonamallee_01", "Mount-Poonamallee Rd (MIOT)", 2700, 35, "no", "no", 0, False),
        ("N_MANAPAKKAM", "N_PORUR", 0, "seg_mount_poonamallee_02", "Mount-Poonamallee Rd (Porur)", 2800, 40, "no", "no", 0, False),

        # Inner Ring Road (100ft Road: Koyambedu -> Kathipara)
        ("N_KOYAMBEDU", "N_VADAPALANI", 0, "seg_inner_ring_01", "Inner Ring Road (Vadapalani)", 2600, 50, "no", "no", 0, False),
        ("N_VADAPALANI", "N_JAFFERKHANPET", 0, "seg_inner_ring_02", "Inner Ring Road (Ashok Nagar)", 3100, 45, "no", "no", 0, False),
        ("N_JAFFERKHANPET", "N_GUINDY_KATHIPARA", 0, "seg_inner_ring_03", "Inner Ring Road (Jafferkhanpet Adyar Basin)", 1800, 35, "no", "no", 0, False),

        # Velachery Arterial System (HIGH FLOOD IMPACT)
        ("N_GUINDY_KATHIPARA", "N_VELACHERY_CHECKPOST", 0, "seg_guindy_velachery", "Guindy-Velachery Link Rd", 1800, 35, "no", "no", 0, False),
        ("N_VELACHERY_CHECKPOST", "N_VELACHERY_CENTRAL", 0, "seg_velachery_main_01", "Velachery Main Road North", 2100, 30, "no", "no", 0, False),
        ("N_VELACHERY_CENTRAL", "N_MADIPAKKAM", 0, "seg_velachery_madipakkam", "Velachery-Madipakkam Connector", 2200, 25, "no", "no", 0, False),
        ("N_VELACHERY_CENTRAL", "N_TIDEL_PARK", 0, "seg_taramani_link", "Taramani Link Road", 2800, 40, "no", "no", 0, False),

        # Kotturpuram & Adyar River Crossing
        ("N_NANDANAM", "N_KOTTURPURAM", 0, "seg_kotturpuram_01", "Kotturpuram Approach Rd", 1700, 35, "no", "no", 0, False),
        ("N_KOTTURPURAM", "N_ADYAR_GATE", 0, "seg_kotturpuram_bridge", "Kotturpuram Bridge", 1100, 35, "no", "no", 0, False),
        ("N_ADYAR_GATE", "N_ADYAR_CENTRAL", 0, "seg_adyar_01", "L.B. Road / Adyar Central", 1300, 35, "no", "no", 0, False),

        # Rajiv Gandhi IT Expressway (OMR)
        ("N_ADYAR_CENTRAL", "N_TIDEL_PARK", 0, "seg_omr_01", "Rajiv Gandhi IT Expressway (Tidel)", 2000, 50, "no", "no", 0, False),
        ("N_TIDEL_PARK", "N_SHOLINGANALLUR", 0, "seg_omr_02", "Rajiv Gandhi IT Expressway (OMR Mid)", 9500, 55, "no", "no", 0, False),
        ("N_SHOLINGANALLUR", "N_PERUMBAKKAM", 0, "seg_omr_perumbakkam", "Sholinganallur-Perumbakkam Link", 2900, 35, "no", "no", 0, False),

        # CORRIDOR A: Peripheral Low-Criticality Arterial Link
        # Santhome / Coastal feeder (floods physically, but alternate inland route Luz/Greams exists)
        ("N_MYLAPORE_LUZ", "N_SANTHOME", 0, "seg_coastal_feeder_01", "Kutchery Road Feeder", 1200, 30, "no", "no", 0, False),
        ("N_SANTHOME", "N_ADYAR_CENTRAL", 0, "seg_coastal_feeder_02", "Santhome-Adyar Coastal Connector", 3400, 40, "no", "no", 0, False),

        # Urban connecting links
        ("N_TEYNAMPET", "N_MYLAPORE_LUZ", 0, "seg_teynampet_mylapore", "Eldams Road / Luz Church Rd", 2400, 35, "no", "no", 0, False),
        ("N_CENTRAL", "N_KILPAUK", 0, "seg_poonamallee_01", "Poonamallee High Road East", 3900, 45, "no", "no", 0, False),
        ("N_KILPAUK", "N_KOYAMBEDU", 0, "seg_poonamallee_02", "Poonamallee High Road West", 5200, 45, "no", "no", 0, False),
    ]

    for u, v, key, seg_id, name, length_m, speed_kph, bridge, tunnel, layer, oneway in raw_edges:
        u_node = G.nodes[u]
        v_node = G.nodes[v]
        travel_time_sec = length_m / (speed_kph * 1000.0 / 3600.0)

        # Build LineString geometry in WGS84 for map visualization
        geom = LineString([(u_node["lon"], u_node["lat"]), (v_node["lon"], v_node["lat"])])

        edge_attrs = {
            "physical_segment_id": seg_id,
            "name": name,
            "length": float(length_m),
            "speed_kph": float(speed_kph),
            "travel_time": float(travel_time_sec),
            "bridge": bridge,
            "tunnel": tunnel,
            "layer": int(layer),
            "highway": "primary" if speed_kph >= 45 else "secondary",
            "geometry": geom,
        }

        # Forward edge
        G.add_edge(u, v, key=key, **edge_attrs)

        # Reverse edge for two-way streets
        if not oneway:
            rev_attrs = dict(edge_attrs)
            # Reconstruct reversed geometry
            rev_attrs["geometry"] = LineString([(v_node["lon"], v_node["lat"]), (u_node["lon"], u_node["lat"])])
            G.add_edge(v, u, key=key, **rev_attrs)

    return G
