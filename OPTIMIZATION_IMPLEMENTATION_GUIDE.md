# Optimization Implementation Guide
**ADE-EPC-Analysis Code Refactoring**

**Version:** 1.0
**Date:** 2025-12-18
**Purpose:** Step-by-step guide to implement performance optimizations and eliminate code duplication

---

## Overview

This guide provides practical instructions for refactoring the ADE-EPC-Analysis codebase to:
1. **Eliminate 900-1,300 lines of duplicated code**
2. **Achieve 6-9x speedup** for full analysis pipeline
3. **Reduce memory usage by 60-75%**
4. **Improve maintainability** by 40-50%

**Total Estimated Effort:** 60-75 hours over 6-9 weeks

---

## Phase 1: Quick Wins (Week 1-2, 15-20 hours)

### Step 1.1: Migrate to Parquet Format (2-3 hours)

**Priority:** HIGH (Quick Win)
**Performance Gain:** 80-90% faster data loading (3-5 min → 20-40 sec)

#### Implementation:

**1.1.1: Convert existing CSV data to Parquet**

```python
from src.utils.data_loader import EPCDataLoader

# Convert validated data
loader = EPCDataLoader()
loader.migrate_to_parquet(
    csv_path="data/processed/epc_england_wales_validated.csv",
    compression='snappy',
    delete_csv=False  # Keep CSV as backup initially
)
```

**1.1.2: Update all module imports**

Find all instances of:
```python
df = pd.read_csv(input_file, low_memory=False)
```

Replace with:
```python
from src.utils.data_loader import load_epc_data

df = load_epc_data(geography='england_wales')
```

**Files to update:**
- `src/analysis/heat_pump_potential.py:343-352`
- `src/analysis/heat_network_potential.py:431-440`
- `src/analysis/demand_reduction_analysis.py:592-601`
- `src/analysis/heating_fuel_analysis.py:352-361`
- Plus 6+ more analysis modules

**Test:** Run one analysis module and verify:
- Output is identical
- Loading is much faster
- Memory usage is similar

---

### Step 1.2: Implement Data Loader Utility (4-5 hours)

**Priority:** HIGH
**Benefit:** Eliminates 100 lines of duplication, enables caching

#### Implementation:

**1.2.1: Update main analysis scripts**

**Before:**
```python
# Old pattern (repeated 10+ times)
from config.config import DATA_PROCESSED_DIR

input_file = DATA_PROCESSED_DIR / "epc_london_validated.csv"
if not input_file.exists():
    logger.error(f"Input file not found: {input_file}")
    return

logger.info(f"Loading data from: {input_file}")
df = pd.read_csv(input_file, low_memory=False)
```

**After:**
```python
# New pattern
from src.utils.data_loader import load_epc_data

df = load_epc_data(geography='england_wales', use_cache=True)
```

**1.2.2: Enable caching for sequential analyses**

If running multiple analyses in sequence (e.g., in `run_ade_analysis.py`):

```python
from src.utils.data_loader import EPCDataLoader

# Load once
loader = EPCDataLoader()
df = loader.load_epc_data(use_cache=True)

# Run analyses
analyzer1 = HeatPumpPotentialAnalyzer()
analyzer1.analyze(df)

analyzer2 = HeatNetworkPotentialAnalyzer()
analyzer2.analyze(df)  # Uses same in-memory data

# Clear cache when done
EPCDataLoader.clear_cache()
```

**Test:** Verify that second analysis doesn't reload data (should be instant)

---

### Step 1.3: Implement Geographic Aggregation Utility (6-8 hours)

**Priority:** HIGH
**Benefit:** Eliminates 240-300 lines of duplication across 3 modules

#### Implementation:

**1.3.1: Refactor heat_pump_potential.py**

**Before (Lines 183-265):**
```python
def calculate_potential_by_geography(
    self,
    df: pd.DataFrame,
    level: str = 'national',
    geography_col: Optional[str] = None
) -> pd.DataFrame:
    if level == 'national':
        tier_counts = df['hp_suitability_tier'].value_counts().sort_index()
        total = len(df)
        result_df = pd.DataFrame({
            'geography': ['England and Wales'],
            'total_properties': [total],
            'tier_1_ready': [tier_counts.get(1, 0)],
            # ... 20+ more lines
        })
        return result_df

    else:
        # Geography breakdown - 40+ more lines
        geo_summary = []
        for geo_area in df[geography_col].unique():
            # ... iteration logic
        result_df = pd.DataFrame(geo_summary)
        return result_df
```

**After:**
```python
from src.utils.geographic_aggregator import GeographicAggregator

def calculate_potential_by_geography(
    self,
    df: pd.DataFrame,
    level: str = 'national',
    geography_col: Optional[str] = None
) -> pd.DataFrame:
    agg = GeographicAggregator()

    # Calculate tier distribution
    result = agg.calculate_tier_distribution(
        df,
        tier_column='hp_suitability_tier',
        geography_col=geography_col,
        level=level
    )

    return result
```

**1.3.2: Refactor heat_network_potential.py** (Similar pattern)

**Before (Lines 249-320):**
```python
def analyze_by_geography(self, df: pd.DataFrame, level: str = 'national', ...):
    if level == 'national':
        # 30 lines of national summary logic
    else:
        # 40+ lines of geographic breakdown
```

**After:**
```python
from src.utils.geographic_aggregator import GeographicAggregator

def analyze_by_geography(self, df: pd.DataFrame, level: str = 'national', ...):
    agg = GeographicAggregator()

    result = agg.aggregate_by_geography(
        df,
        metrics={
            'annual_heat_demand_kwh': 'sum',
            'property_count': 'count'
        },
        level=level,
        geography_col=geography_col
    )

    return result
```

**1.3.3: Refactor heating_fuel_analysis.py** (Similar pattern)

**Test after each module:**
1. Run analysis with old and new code
2. Compare outputs (should be identical)
3. Check for performance improvements

---

## Phase 2: Performance Optimization (Week 3-5, 25-30 hours)

### Step 2.1: Create Base Analyzer Class (8-10 hours)

**Priority:** HIGH
**Benefit:** Eliminates 200-560 lines of duplication across 12 modules

#### Implementation:

**2.1.1: Refactor one analysis module as template**

Let's start with `heat_pump_potential.py`:

**Before:**
```python
class HeatPumpPotentialAnalyzer:
    def __init__(self):
        self.config = load_config()
        self.policy_config = self.config.get('policy_metrics', {}).get('heat_pump', {})
        self.results = {}
        logger.info("Initialized Heat Pump Potential Analyzer")

    # ... 300+ lines of analysis code ...

    def save_results(self, output_path: Optional[Path] = None):
        if output_path is None:
            output_path = DATA_OUTPUTS_DIR / "heat_pump_results.txt"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("HEAT PUMP ANALYSIS RESULTS\n")
            f.write("=" * 70 + "\n\n")
            # ... 30+ more lines of formatting
```

**After:**
```python
from src.analysis.base_analyzer import BaseAnalyzer, requires_columns

class HeatPumpPotentialAnalyzer(BaseAnalyzer):
    def __init__(self):
        super().__init__(
            name="Heat Pump Potential Analyzer",
            config_section="policy_metrics.heat_pump"
        )

    @requires_columns('CURRENT_ENERGY_RATING', 'ENERGY_CONSUMPTION_CURRENT')
    def assess_suitability(self, df: pd.DataFrame) -> pd.DataFrame:
        # Analysis code (no changes needed)
        ...
        return df_assessed

    # save_results() inherited from BaseAnalyzer - no need to redefine!
```

**Benefits:**
- `__init__` reduced from 7 lines to 3 lines
- `save_results()` eliminated (30+ lines)
- Automatic column validation
- Standardized configuration loading

**2.1.2: Migrate remaining 11 modules**

Follow same pattern for:
- heat_network_potential.py
- demand_reduction_analysis.py
- heating_fuel_analysis.py
- consumer_impact_analysis.py
- policy_scenarios.py
- Plus 6 more modules

**Test each module:**
```python
# Verify inheritance works
analyzer = HeatPumpPotentialAnalyzer()
assert hasattr(analyzer, 'config')
assert hasattr(analyzer, 'results')
assert hasattr(analyzer, 'save_results')

# Verify results format is consistent
analyzer.analyze(df)
analyzer.save_results()
```

---

### Step 2.2: Implement Cost Calculator Utility (6-8 hours)

**Priority:** HIGH
**Benefit:** Eliminates cost logic drift, centralizes assumptions

#### Implementation:

**2.2.1: Update heat_pump_potential.py**

**Before:**
```python
df_assessed.loc[tier_2_mask, 'hp_fabric_cost_estimate'] = 1200  # Loft top-up
df_assessed.loc[tier_3_mask, 'hp_fabric_cost_estimate'] = 4000  # Cavity + loft
df_assessed.loc[tier_4_mask, 'hp_fabric_cost_estimate'] = 12000  # SWI + loft
```

**After:**
```python
from src.utils.cost_calculator import CostCalculator

calc = CostCalculator()

# More accurate fabric cost calculation
df_assessed['hp_fabric_cost_estimate'] = calc.calculate_fabric_costs(
    df_assessed,
    measures=['loft_insulation_topup', 'cavity_wall_insulation']
)
```

**2.2.2: Update consumer_impact_analysis.py**

**Before:**
```python
gas_annual_cost = (avg_demand / 0.85) * 0.0624
hp_annual_cost = (avg_demand / 3.0) * 0.245
```

**After:**
```python
from src.utils.cost_calculator import CostCalculator

calc = CostCalculator()

gas_annual_cost = calc.calculate_annual_running_costs(
    annual_demand=avg_demand,
    system_type='gas_boiler',
    price_scenario='baseline'
)

hp_annual_cost = calc.calculate_annual_running_costs(
    annual_demand=avg_demand,
    system_type='heat_pump',
    price_scenario='baseline'
)
```

**2.2.3: Update demand_reduction_analysis.py**

**Before:**
```python
FABRIC_MEASURES = {
    'loft_insulation': {'cost': 1200, ...},
    'cavity_wall_insulation': {'cost': 2500, ...},
    # ... duplicated from config
}
```

**After:**
```python
from src.utils.cost_calculator import CostCalculator

calc = CostCalculator()
# All costs now come from single source (config.yaml via CostCalculator)
```

**Test:**
1. Verify all cost calculations produce same results
2. Update costs in config.yaml
3. Verify all modules use updated costs (single source of truth)

---

### Step 2.3: Vectorize Operations (10-14 hours)

**Priority:** HIGH
**Performance Gain:** 20-50x speedup for geographic aggregations

#### Implementation:

**2.3.1: Replace iterrows() in retrofit_packages.py**

**Before (SLOW - O(n)):**
```python
for idx, (_, property_data) in enumerate(df.iterrows()):
    # Calculate retrofit package for each property
    cost = calculate_retrofit_cost(property_data)
    savings = calculate_savings(property_data)
    results.append({'cost': cost, 'savings': savings})
```

**After (FAST - vectorized):**
```python
# Vectorized calculations
df['retrofit_cost'] = calculate_retrofit_cost_vectorized(df)
df['savings'] = calculate_savings_vectorized(df)
```

**How to vectorize:**
```python
# Before (scalar function called per row)
def calculate_retrofit_cost(property_data: pd.Series) -> float:
    cost = 0
    if property_data['needs_loft']:
        cost += 1200
    if property_data['needs_wall']:
        cost += 2500
    return cost

# After (vectorized function)
def calculate_retrofit_cost_vectorized(df: pd.DataFrame) -> pd.Series:
    cost = pd.Series(0, index=df.index)
    cost[df['needs_loft']] += 1200
    cost[df['needs_wall']] += 2500
    return cost
```

**2.3.2: Replace loops with groupby**

**Before (SLOW - explicit loop):**
```python
geo_summary = []
for geo_area in df[geography_col].unique():
    area_df = df[df[geography_col] == geo_area]
    tier_counts = area_df['hp_suitability_tier'].value_counts()
    total = len(area_df)
    geo_summary.append({
        'geography': geo_area,
        'total': total,
        'tier_1': tier_counts.get(1, 0),
        # ...
    })
result_df = pd.DataFrame(geo_summary)
```

**After (FAST - groupby aggregation):**
```python
result_df = df.groupby(geography_col).agg({
    'hp_suitability_tier': lambda x: x.value_counts().to_dict(),
    geography_col: 'count'
}).reset_index()
```

**Files to optimize:**
- heat_network_potential.py:241-258
- heat_pump_potential.py:241-258
- retrofit_packages.py:552

**Test:** Benchmark before and after:
```python
import time

# Before
start = time.time()
result_old = calculate_old_way(df)
time_old = time.time() - start

# After
start = time.time()
result_new = calculate_new_way(df)
time_new = time.time() - start

print(f"Speedup: {time_old / time_new:.1f}x")
assert result_old.equals(result_new)  # Verify same results
```

**2.3.3: Vectorize fuel categorization in heating_fuel_analysis.py**

**Before (SLOW):**
```python
df['fuel_category'] = df['MAIN_FUEL'].apply(self.categorize_fuel_type)

def categorize_fuel_type(self, fuel_description: str) -> str:
    fuel_lower = str(fuel_description).lower()
    for category, keywords in self.FUEL_CATEGORIES.items():
        if any(keyword in fuel_lower for keyword in keywords):
            return category
    return 'other'
```

**After (FAST - 10-20x speedup):**
```python
def categorize_fuel_vectorized(self, df: pd.DataFrame) -> pd.Series:
    df['fuel_category'] = 'other'  # default
    fuel_col = df['MAIN_FUEL'].str.lower().fillna('')

    for category, keywords in self.FUEL_CATEGORIES.items():
        pattern = '|'.join(keywords)
        mask = fuel_col.str.contains(pattern, na=False, regex=True)
        df.loc[mask, 'fuel_category'] = category

    return df['fuel_category']

# Usage
df['fuel_category'] = self.categorize_fuel_vectorized(df)
```

---

## Phase 3: Advanced Optimization (Week 6-9, 20-25 hours)

### Step 3.1: Implement Parallel Processing (8-12 hours)

**Priority:** MEDIUM (for national-scale analysis)
**Performance Gain:** 4-8x speedup on multi-core systems

#### Implementation:

**3.1.1: Parallelize geographic analysis**

```python
from multiprocessing import Pool
import multiprocessing as mp

def analyze_geography_parallel(
    df: pd.DataFrame,
    geography_col: str,
    analysis_func
) -> pd.DataFrame:
    """Run analysis in parallel by geography."""

    # Split by geography
    geo_groups = [(name, group) for name, group in df.groupby(geography_col)]

    # Parallel processing
    with Pool(mp.cpu_count()) as pool:
        results = pool.starmap(analysis_func, geo_groups)

    # Combine results
    return pd.concat(results, ignore_index=True)
```

**Usage:**
```python
def analyze_single_geography(geo_name, geo_df):
    # Analysis for single geography
    result = perform_analysis(geo_df)
    result['geography'] = geo_name
    return result

# Run in parallel
results = analyze_geography_parallel(
    df,
    'local_authority_name',
    analyze_single_geography
)
```

**Alternative: Use Dask for built-in parallelism**

```python
import dask.dataframe as dd

# Convert to Dask DataFrame
ddf = dd.from_pandas(df, npartitions=mp.cpu_count())

# Parallel groupby
result = ddf.groupby('geography').agg({
    'energy_consumption': 'mean',
    'property_count': 'count'
}).compute()
```

**Warning:** Only use for CPU-intensive operations on large datasets. Overhead can make it slower for small datasets.

---

### Step 3.2: Implement Result Caching (3-4 hours)

**Priority:** MEDIUM
**Performance Gain:** 10-20% speedup for repeated calculations

#### Implementation:

**3.2.1: Add caching to expensive calculations**

```python
from functools import lru_cache

class Analyzer(BaseAnalyzer):
    def __init__(self):
        super().__init__(...)
        self._cache = {}

    def get_average_demand(self, df: pd.DataFrame) -> float:
        """Calculate average demand with caching."""
        cache_key = 'avg_demand'

        if cache_key not in self._cache:
            self._cache[cache_key] = df['ENERGY_CONSUMPTION_CURRENT'].mean()

        return self._cache[cache_key]

    def clear_cache(self):
        """Clear cache when DataFrame changes."""
        self._cache.clear()
```

**3.2.2: Cache expensive aggregations**

```python
# Instead of recalculating multiple times:
avg_demand = df['ENERGY_CONSUMPTION_CURRENT'].mean()  # Line 190
total_demand = df['ENERGY_CONSUMPTION_CURRENT'].sum()  # Line 220
avg_again = df['ENERGY_CONSUMPTION_CURRENT'].mean()  # Line 250 (redundant!)

# Calculate once and cache:
self._avg_demand = df['ENERGY_CONSUMPTION_CURRENT'].mean()
self._total_demand = df['ENERGY_CONSUMPTION_CURRENT'].sum()
```

---

### Step 3.3: Chunked Processing (5-6 hours)

**Priority:** LOW-MEDIUM (only for very large datasets)
**Benefit:** Enables processing datasets larger than RAM

#### Implementation:

```python
from src.utils.data_loader import EPCDataLoader

def analyze_in_chunks(chunk_size: int = 100000):
    """Process data in chunks."""
    loader = EPCDataLoader()

    results = []

    for chunk in loader.load_chunked(chunk_size=chunk_size):
        # Analyze chunk
        chunk_result = analyze_chunk(chunk)
        results.append(chunk_result)

    # Combine results
    final_result = combine_results(results)
    return final_result
```

---

## Phase 4: Validation & Testing (Throughout)

### Continuous Validation Process

**After each refactoring step:**

1. **Output Validation**
   ```bash
   python scripts/validate_outputs.py --before old_output.csv --after new_output.csv
   ```

2. **Performance Benchmarking**
   ```bash
   python scripts/benchmark_analysis.py
   ```

3. **Memory Profiling**
   ```bash
   python -m memory_profiler src/analysis/heat_pump_potential.py
   ```

4. **Unit Tests**
   ```bash
   pytest tests/ -v
   ```

### Create Validation Scripts

**scripts/validate_outputs.py:**
```python
import pandas as pd
import numpy as np

def validate_outputs(old_file, new_file, tolerance=1e-6):
    """Validate refactored code produces same results."""
    df_old = pd.read_csv(old_file)
    df_new = pd.read_csv(new_file)

    # Check row counts
    assert len(df_old) == len(df_new), "Row count mismatch"

    # Check columns
    assert set(df_old.columns) == set(df_new.columns), "Column mismatch"

    # Check numeric columns
    for col in df_old.select_dtypes(include=[np.number]).columns:
        diff = (df_old[col] - df_new[col]).abs().max()
        assert diff < tolerance, f"{col}: max diff {diff} > {tolerance}"

    print("✅ Validation passed: outputs are identical")
```

**scripts/benchmark_analysis.py:**
```python
import time
import psutil
import os

def benchmark_analysis(analyzer_func, df):
    """Benchmark analysis performance."""
    process = psutil.Process(os.getpid())

    # Measure initial memory
    mem_before = process.memory_info().rss / 1024 / 1024  # MB

    # Time analysis
    start = time.time()
    result = analyzer_func(df)
    elapsed = time.time() - start

    # Measure final memory
    mem_after = process.memory_info().rss / 1024 / 1024  # MB
    mem_used = mem_after - mem_before

    print(f"Time: {elapsed:.1f} seconds")
    print(f"Memory used: {mem_used:.1f} MB")
    print(f"Peak memory: {mem_after:.1f} MB")

    return result, elapsed, mem_used
```

---

## Troubleshooting Common Issues

### Issue 1: Import Errors

**Problem:** `ModuleNotFoundError: No module named 'src.utils'`

**Solution:**
```python
# Add to top of file
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
```

### Issue 2: Output Differences

**Problem:** Refactored code produces slightly different results

**Causes:**
1. Floating point precision differences (acceptable)
2. Different aggregation order (check if order matters)
3. Handling of NaN values differs

**Solution:**
```python
# Use np.allclose for float comparison
np.allclose(result_old, result_new, rtol=1e-5)

# Check if order matters
result_old_sorted = result_old.sort_values('geography')
result_new_sorted = result_new.sort_values('geography')
```

### Issue 3: Slower Performance

**Problem:** Refactored code is slower

**Causes:**
1. DataFrame copies not eliminated
2. Caching not enabled
3. Parquet not used
4. Vectorization not complete

**Solution:** Profile code to identify bottleneck:
```python
import cProfile
cProfile.run('analyzer.analyze(df)', sort='cumtime')
```

---

## Monitoring Progress

### Track Improvements

**Create progress tracking spreadsheet:**

| Module | Lines Before | Lines After | Reduction | Time Before | Time After | Speedup |
|--------|--------------|-------------|-----------|-------------|------------|---------|
| heat_pump_potential | 400 | 280 | 30% | 15 min | 2 min | 7.5x |
| heat_network_potential | 450 | 310 | 31% | 20 min | 3 min | 6.7x |
| ... | ... | ... | ... | ... | ... | ... |
| **Total** | **6,000** | **4,800** | **20%** | **90 min** | **13 min** | **6.9x** |

---

## Rollback Plan

### If Issues Arise

**Maintain git branches:**
```bash
# Create feature branch
git checkout -b optimization/phase1-quick-wins

# Make changes and commit
git commit -m "Phase 1: Migrate to Parquet"

# If issues, rollback
git checkout main
git branch -D optimization/phase1-quick-wins
```

**Keep old code temporarily:**
```python
# Add _deprecated suffix to old functions
def calculate_potential_by_geography_deprecated(self, ...):
    # Old implementation
    pass

def calculate_potential_by_geography(self, ...):
    # New implementation
    pass
```

---

## Success Metrics

### Target Metrics

**After full implementation:**

| Metric | Before | Target | Status |
|--------|---------|---------|--------|
| Full pipeline time | 45-90 min | 5-15 min | ... |
| Peak memory usage | 40-80 GB | 10-20 GB | ... |
| Lines of code | 6,000 | 4,800 | ... |
| Duplicated lines | 900-1,300 | 0-100 | ... |
| Data loading time | 3-5 min | 20-40 sec | ... |

---

## Next Steps

1. **Week 1:** Complete Phase 1 (Quick Wins)
2. **Week 2:** Validate Phase 1 and start Phase 2
3. **Week 3-5:** Complete Phase 2 (Performance)
4. **Week 6-9:** Implement Phase 3 (Advanced) if needed
5. **Throughout:** Continuous testing and validation

---

**Document Version:** 1.0
**Last Updated:** 2025-12-18
**Maintainer:** Development Team
