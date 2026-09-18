# RAKSHA NET AI — GIS & Routing Architecture

Database: **PostGIS 3** · Client: **Leaflet + OpenStreetMap**

---

## 1. Principle

**Geospatial business logic belongs to the backend. The map only draws.**

The front end never decides which ambulance is nearest, never computes
distances used in a decision, and never filters by geography in a way that
affects an operational outcome. It requests results and renders them.

## 2. Coordinate model

| Concern | Choice |
|---|---|
| Reference system | WGS84, SRID 4326 |
| Storage (durable) | `latitude`, `longitude` as `NUMERIC(9,6)` (~0.11 m) |
| Storage (query) | `geom geography(Point, 4326)` |
| Index | `GIST (geom)` |
| Distance | `ST_Distance(geography, geography)` — metres, geodesic |

Two representations are held deliberately: `NUMERIC` is the readable,
exportable, diff-friendly value; `geography` is the indexed one. The repository
layer writes both in the same transaction, so they cannot drift.

`geography` rather than `geometry` because the operating area spans a wide
latitude range and planar approximations accumulate error — and because
`ST_DWithin` on `geography` takes metres directly, with no projection choice to
get wrong.

## 3. Validation

Every inbound coordinate passes `app/utils/geo.py: validate_coordinates`:

1. `-90 <= latitude <= 90`, `-180 <= longitude <= 180`.
2. Inside the configured operating bounding box
   (`RAKSHA_GEO_BBOX_*`, default: India). Outside it is a `400`, not a silent
   accept — a mis-signed longitude is a common client bug and it would send
   responders to the wrong hemisphere.
3. Rejection of the exact null island `(0, 0)`, an unset-GPS signature.
4. Rounding to 6 decimal places on write.

Accuracy metadata from the browser (`coords.accuracy`) is carried in the client
payload and shown to the dispatcher, so a 2 km-accurate fix is not read as a
doorstep.

## 4. Core spatial queries

### Incidents within a radius

```sql
SELECT i.*, ST_Distance(i.geom, ref.geom) / 1000.0 AS distance_km
FROM incidents i,
     (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS geom) ref
WHERE ST_DWithin(i.geom, ref.geom, :radius_m)
  AND i.status = ANY(:statuses)
ORDER BY i.priority_score DESC NULLS LAST, distance_km ASC
LIMIT :limit;
```

`ST_DWithin` is used rather than `ST_Distance < x` because only the former uses
the `GIST` index.

### Map viewport (bounding box)

```sql
SELECT ... FROM incidents
WHERE geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)::geography
  AND status = ANY(:statuses)
LIMIT :limit;
```

Returned as a GeoJSON `FeatureCollection` so Leaflet consumes it directly.

### Nearest available resource (Phase 10)

```sql
SELECT r.*, ST_Distance(r.geom, :incident_geom) / 1000.0 AS distance_km
FROM resources r
WHERE r.status = 'AVAILABLE'
  AND r.resource_type = ANY(:required_types)
  AND ST_DWithin(r.geom, :incident_geom, :max_radius_m)
ORDER BY r.geom <-> :incident_geom     -- KNN, index-assisted
LIMIT :limit;
```

Straight-line distance orders the *candidate set*; road distance and ETA refine
the top N (§6). A dispatcher always sees both numbers and always approves.

## 5. Map rendering

- Tiles: OpenStreetMap by default; the tile URL is configuration
  (`NEXT_PUBLIC_MAP_TILE_URL`) so a deployment can self-host for an air-gapped
  or high-volume installation. Public OSM tile servers have a usage policy that
  production traffic must not violate.
- Markers are coloured by priority band: CRITICAL red, HIGH orange,
  MEDIUM amber, LOW green. Colour is never the only signal — the marker also
  carries a shape/label, and the list beside the map repeats the band in text.
- Clustering is applied above a configured incident count.
- Leaflet is loaded client-side only (`ssr: false`); it touches `window` at
  import time.

## 6. Routing (Phase 11)

V1 does not route. When routing is added:

| Concern | Decision |
|---|---|
| Engine | OSRM or Valhalla, self-hosted |
| Use | Refine the top N candidates from the KNN query |
| Fallback | Straight-line distance with a road-factor multiplier, clearly labelled as an estimate |
| Display | ETA always shown with its source (`routed` or `estimated`) |
| Blocked roads | An `road_closures` layer feeding avoid-polygons into the engine |

An ETA is never presented as a promise, and a routing outage degrades to a
labelled estimate rather than blocking dispatch.

## 7. Reverse geocoding

- Provider is pluggable behind `GeocodingProvider`; Nominatim for development.
- Results are cached in Redis by rounded coordinate (5 dp, ~1.1 m).
- Reverse geocoding is **advisory**. A failure never blocks a report — the
  incident keeps its coordinates and shows the citizen's own address text.
- Nominatim's usage policy forbids heavy automated use; production uses a
  self-hosted instance or a commercial provider.

## 8. Privacy

- Precise coordinates are returned only to operational roles and the reporter.
- Analytics and hotspot layers operate on coarsened coordinates (~1 km grid or
  H3 cell), never raw points.
- Closed incidents have their precise coordinates truncated after the retention
  window (see `DATABASE.md` §6).
- Coordinates are never written to application logs.

## 9. Performance

| Technique | Where |
|---|---|
| `GIST` index on `geom` | All spatial filters |
| `ST_DWithin` over distance comparison | Radius queries |
| KNN `<->` ordering | Nearest-resource |
| Viewport + zoom-dependent `LIMIT` | Map queries |
| Server-side clustering above a threshold | Map queries |
| Redis cache for reverse geocoding | Geocoding |

Materialised views for hotspot aggregation are planned for Phase 14, refreshed
on a schedule rather than per request.
