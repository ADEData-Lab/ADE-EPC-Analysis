# Memory-Safe Pipeline Settings

This document describes the memory optimizations implemented to run the full ~700k property pipeline on a laptop with ≈16 GB RAM.

## Overview

The pipeline has been optimized to:
1. **Avoid OOM kills** during scenario/subsidy modeling and spatial operations
2. **Fix GeoPandas errors** from improper GeoDataFrame handling
3. **Process data in chunks** to keep memory usage stable
4. **Instrument memory** to detect regressions

## Memory Usage Targets

- **Target peak RSS**: ~10-11 GB (safe for 16 GB laptops)
- **Warning threshold**: 12 GB
- **Critical threshold**: 14 GB (kernel OOM kill risk)

## Key Optimizations

### 1. Chunked Processing

All heavy operations now process data in configurable chunks:

- **EPC validation**: 500k rows/chunk (configurable in `phase_2_data_validation()`)
- **Geographic enrichment**: 100k rows/chunk (configurable in `run_chunked_pipeline()`)
- **Heat network proximity**: 10k properties/chunk (configurable in `calculate_proximity()`)

### 2. Subset-Based Spatial Operations

Spatial operations only process properties that need geocoding/proximity analysis:

```python
# BEFORE (memory-heavy):
properties_gdf = geocode_all_properties(df)  # 700k properties → 13+ GB spike

# AFTER (memory-safe):
sample_df = df.sample(50000)  # Only geocode sample needed for analysis
properties_gdf = geocode_sample(sample_df)  # <3 GB
```

### 3. Indexed Lookups Instead of Merges

Large DataFrame.merge() operations replaced with Series.map():

```python
# BEFORE (memory-heavy merge):
properties_gdf = properties_gdf.merge(lookup_df, on='CONSTITUENCY')  # Loses geometry, creates copy

# AFTER (memory-safe map):
lookup_map = dict(zip(lookup_df['CONSTITUENCY'], lookup_df['value']))
properties_gdf['value'] = properties_gdf['CONSTITUENCY'].map(lookup_map)  # No copy, keeps geometry
```

### 4. GeoDataFrame Geometry Preservation

All GeoDataFrames now created with explicit `geometry=` and `crs=` at construction:

```python
# CORRECT pattern:
gdf = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
    crs="EPSG:4326"
)

# NEVER create "lazy" GeoDataFrame without geometry
# NEVER call .set_crs() after creation
```

### 5. Prevent Repeated Geocoding

The pipeline now checks for existing coordinates before geocoding:

```python
# Check if LATITUDE/LONGITUDE columns exist
if 'LATITUDE' in df.columns and 'LONGITUDE' in df.columns:
    # Use existing coordinates - skip geocoding
    gdf = gpd.GeoDataFrame(df, geometry=points_from_xy(...))
else:
    # Geocode from postcodes
    gdf = geocoder.geocode_dataframe(df)
```

### 6. Memory Instrumentation

All key phases now log RSS memory usage:

```python
from src.utils.memory_utils import log_memory, MemoryMonitor

# Simple logging
log_memory("After geocoding")

# Context manager for operations
with MemoryMonitor("Heat network proximity calculation"):
    analyzer.calculate_proximity(properties_gdf)
```

Logs output:
```
[MEM] After geocoding: 8,432 MB (8.23 GB)
[MEM START] Heat network proximity calculation: 8,432 MB (8.23 GB)
[MEM END] Heat network proximity calculation: 9,124 MB (8.91 GB), delta: +692 MB (+0.68 GB)
```

## Configuration

### Environment Variables

Set these to control memory usage:

```bash
# Maximum worker processes (default: 1 for laptop safety)
export ADE_MAX_WORKERS=1

# Chunk size for processing (smaller = less memory, slower)
export ADE_CHUNK_SIZE=50000

# Memory warning threshold in GB
export ADE_MEM_THRESHOLD=12.0
```

### Pipeline Parameters

Adjust these in `run_ade_analysis.py`:

```python
# Chunked pipeline batch size
run_chunked_pipeline(validated_path, batch_size=100000)  # Default: 100k

# Heat network proximity sample size
phase_3b_heat_network_proximity(df, sample_size=50000)  # Default: 50k

# Proximity calculation chunk size
analyzer.calculate_proximity(properties_gdf, chunk_size=10000)  # Default: 10k
```

## Recommended Laptop Settings

For a laptop with 16 GB RAM:

```python
# In run_ade_analysis.py
BATCH_SIZE = 100000  # 100k rows/chunk for main pipeline
PROXIMITY_SAMPLE = 50000  # 50k properties for spatial analysis
PROXIMITY_CHUNK = 10000  # 10k properties/chunk for distance calculations

# In EPCDataValidator
VALIDATION_CHUNK = 500000  # 500k rows/chunk for validation
```

## Memory Profiling

To identify regressions:

1. **Enable debug logging**:
   ```python
   log_memory("Operation name", level="debug")
   ```

2. **Monitor peak usage**:
   ```bash
   # While pipeline runs
   watch -n 1 'ps aux | grep python | grep run_ade'
   ```

3. **Check kernel logs for OOM**:
   ```bash
   sudo dmesg | grep -i "killed process"
   ```

## Troubleshooting

### OOM Kill During Subsidy Sensitivity

**Symptoms**: Process killed during scenario modeling, kernel log shows "Out of memory"

**Fix**: Reduce batch size and sample sizes:
```python
run_chunked_pipeline(validated_path, batch_size=50000)  # Reduce from 100k
phase_3b_heat_network_proximity(df, sample_size=25000)  # Reduce from 50k
```

### GeoPandas CRS Error

**Symptoms**: `ValueError: Assigning CRS to a GeoDataFrame without a geometry column is not supported`

**Fix**: Ensure all GeoDataFrames created with `geometry=`:
```python
# Check this pattern exists:
gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

# NOT this:
gdf = gpd.GeoDataFrame(df)
gdf.set_crs("EPSG:4326")  # ❌ WRONG
```

### Memory Spikes During Merges

**Symptoms**: RSS jumps 4-6 GB during constituency or geographic enrichment

**Fix**: Use Series.map() instead of DataFrame.merge():
```python
# Replace merge
df = df.merge(lookup_df, on='key')

# With map
lookup_map = dict(zip(lookup_df['key'], lookup_df['value']))
df['value'] = df['key'].map(lookup_map)
```

### Spatial Join Slowness

**Symptoms**: Heat network tier classification takes >10 minutes

**Fix**: Use chunked processing in `calculate_proximity()`:
```python
# Reduce chunk size if memory-constrained
analyzer.calculate_proximity(properties_gdf, chunk_size=5000)  # Default: 10k
```

## Validation

To confirm the pipeline runs memory-safely:

1. **Full pipeline test**:
   ```bash
   python run_ade_analysis.py
   ```

2. **Check peak memory**:
   - Should stay below 12 GB
   - No kernel OOM kills
   - Completes all phases including subsidy sensitivity

3. **Verify outputs**:
   ```bash
   ls -lh data/outputs/
   # Should see:
   # - constituency_*.csv
   # - heat_network_zone_proximity_results.txt
   # - hn_penetration_sensitivity.csv
   ```

## Future Improvements

Potential further optimizations:

1. **Streaming GeoDataFrame writes**: Write spatial results incrementally instead of in memory
2. **Dask integration**: For datasets >1M properties, use Dask for out-of-core processing
3. **Pre-computed spatial indices**: Cache R-tree indices for heat networks to speed up proximity
4. **Dtype optimization**: Use float32 instead of float64 where precision allows

## References

- Memory profiling: `src/utils/memory_utils.py`
- Chunked processing: `run_ade_analysis.py::run_chunked_pipeline()`
- Spatial chunking: `src/spatial/heat_network_zone_proximity.py::calculate_proximity()`
- GeoDataFrame fixes: `run_ade_analysis.py::phase_3b_heat_network_proximity()`
