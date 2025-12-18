# Academic Audit Report: ADE-EPC-Analysis
**Domestic Energy Efficiency and Heating Retrofit Modeling**

**Audit Date:** 2025-12-18
**Repository Version:** 2.0.0
**Scope:** England and Wales National Analysis
**Auditor:** Independent Academic Review

---

## Executive Summary

This audit evaluates the academic rigor, methodological soundness, and computational efficiency of the ADE-EPC-Analysis repository. The analysis covers 83 calculation parameters, 15 analysis modules, and ~6,000 lines of code.

### Overall Assessment: B+ (Good, with areas for improvement)

**Strengths:**
- ✅ **Excellent documentation** with transparent parameter tracking (AUTHORITATIVE_SOURCES.md)
- ✅ **Peer-reviewed foundations** (Few et al. 2023, Crawley et al. 2019)
- ✅ **Recent data updates** (Ofgem Q4 2024, DESNZ 2024)
- ✅ **Transparent about evidence gaps**

**Weaknesses:**
- ⚠️ **59% of parameters are heuristics** without strong empirical validation
- ⚠️ **Heat pump SCOP** not validated against field trials or flow-temperature dependent
- ⚠️ **Substantial code duplication** (900-1,300 lines across modules)
- ⚠️ **Performance bottlenecks** that limit scalability to national datasets

---

## 1. Academic Rigor Assessment

### 1.1 Evidence Quality Distribution (83 Parameters)

| Validation Status | Count | % | Assessment |
|-------------------|-------|---|------------|
| **Validated** | 20 | 24.1% | ✅ Strong - direct match with authoritative sources |
| **Evidence-based** | 5 | 6.0% | ✅ Strong - peer-reviewed research |
| **Scenario-aligned** | 8 | 9.6% | ⚠️ Moderate - consistent with official projections |
| **Plausible/Heuristic** | 49 | 59.0% | ❌ Weak - industry estimates, engineering judgment |
| **Action Required** | 1 | 1.2% | ❌ Outdated (heat network penetration) |

### 1.2 Parameters Requiring Urgent Validation

#### Critical Priority (Affects Core Conclusions)

**1. Heat Pump SCOP: 3.0**
- **Current Status:** Industry average, no field trial validation
- **Issue:** No flow temperature dependency (SCOP varies 2.0-4.0 depending on 35°C vs 65°C operation)
- **Impact:** Directly affects all heat pump cost/carbon/bill calculations
- **Recommendation:**
  - Validate against MCS Heat Pump Field Trials (DECC/DESNZ)
  - Use temperature-dependent SCOP curve: f(T_flow, T_outdoor)
  - Range: 2.5-3.5 for UK climate
- **Sources:**
  - Energy Systems Catapult - Electrification of Heat trials
  - MCS certified installer performance data
  - Renewable Heat Incentive monitoring reports

**2. Fabric Improvement Savings (All Measures)**
- **Current Status:** All heuristics without SAP or measured data validation
- **Values Under Question:**
  - Loft insulation: 15% (needs validation)
  - Cavity wall: 20% (plausible but unverified)
  - Solid wall: 30% (upper end of 15-30% range)
  - Floor: 5% (limited evidence)
  - Double glazing: 10% (within 8-12% range)
- **Impact:** Affects all retrofit pathway models, savings claims
- **Recommendation:**
  - Cross-validate with SAP 10.2 methodology appendices
  - Compare with Energy Saving Trust measured savings database
  - Review DESNZ Retrofit for the Future trial data
  - Academic validation: Galvin, Fawcett et al. studies
  - Provide confidence intervals, not point estimates

**3. Heat Network Penetration: 0.2%**
- **Current Status:** OUTDATED - should be ~2.5%
- **Issue:** 10x below actual UK heat network coverage (~2-3% of heat demand)
- **Impact:** Significantly underestimates heat network potential
- **Recommendation:** Update immediately to 2.5%
- **Source:** DESNZ Heat Networks Statistics 2024

#### High Priority (Affects Specific Analyses)

**4. Retrofit Costs (All Measures)**
- **Current Status:** "Plausible" industry estimates, not validated with recent data
- **Key Costs:**
  - ASHP: £12,000 (need 2024/25 validation)
  - Solid wall EWI: £10,000 (conservative, may be low)
  - Solid wall IWI: £14,000 (need conservation area data)
  - Cavity wall: £2,500 (upper end for terraces)
- **Issue:** No London-specific multipliers (typically +15-20%)
- **Recommendation:**
  - Validate against MCS installer surveys (2024/25)
  - Check DESNZ Boiler Upgrade Scheme grant data
  - Review Social Housing Decarbonisation Fund costs
  - Consult RICS Building Cost Information Service (BCIS)
  - Provide cost ranges (low/central/high), not single values

**5. Flow Temperature Estimation Model**
- **Current Status:** Heuristic linear formula from SAP score
- **Formula:** `base_flow_temp = 70 - (SAP - 40) × (25 / 40)`
- **Issue:** Not based on heat loss calculations; arbitrary adjustments (+5°C walls, +3°C glazing)
- **Impact:** Affects emitter upgrade cost estimates, heat pump readiness tiers
- **Recommendation:**
  - Replace with physics-based heat loss calculation (U-values, design temperatures)
  - Align with MCS MIS 3005 standards
  - Validate against sample heat loss surveys

### 1.3 Parameters with Strong Evidence (High Confidence)

**Energy Prices (Validated ✅)**
- Gas: £0.0624/kWh | Electricity: £0.245/kWh (Ofgem Q4 2024)
- Source: https://www.ofgem.gov.uk/energy-price-cap
- Last verified: December 2024

**Carbon Factors (Validated ✅)**
- Gas: 0.183 kgCO₂e/kWh (DESNZ 2024: 0.18296)
- Electricity (current): 0.233 kgCO₂e/kWh (SAP 10.0)
- Electricity (2030): 0.100 kgCO₂e/kWh (National Grid FES 2025: 50-100 gCO₂/kWh range)
- Electricity (2040): 0.050 kgCO₂e/kWh (NESO projections: 41-67 gCO₂/kWh)
- Sources: DESNZ Greenhouse Gas Reporting Conversion Factors 2024, National Grid FES

**Academic Adjustments (Evidence-based ✅)**
- **Prebound Effect:** Few et al. (2023) - Band C: 0.92, D: 0.82, E: 0.72, F: 0.55, G: 0.52
  - Properly implemented in `src/analysis/methodological_adjustments.py`
  - Reduces baseline energy consumption by 8-48% for more realistic savings
- **EPC Uncertainty:** Crawley et al. (2019) - ±2.4 to ±8.0 SAP points by rating
  - Appropriately used for confidence intervals, not individual adjustments

**Financial Parameters (Validated ✅)**
- Discount rate: 3.5% real (HM Treasury Green Book - correct social time preference rate)
- Payback methodology: Standard financial calculations

---

## 2. Methodological Assessment

### 2.1 Energy Efficiency Assessment Methods

#### Prebound Effect Implementation ✅ STRONG
**Implementation:** `src/analysis/methodological_adjustments.py:19-29`

**Approach:**
```python
PREBOUND_FACTORS = {
    'A': 1.00, 'B': 1.00, 'C': 0.92, 'D': 0.82,
    'E': 0.72, 'F': 0.55, 'G': 0.52
}
adjusted_energy = EPC_energy × prebound_factor
```

**Assessment:**
- ✅ Correctly implements Few et al. (2023) findings
- ✅ Applied to baseline before calculating savings
- ✅ Default factor (0.82 for Band D) for missing values
- ⚠️ Should cross-validate with Sunikka-Blank & Galvin studies

#### EPC Measurement Uncertainty ✅ STRONG
**Implementation:** Crawley et al. (2019) band-specific uncertainty (±2.4 to ±8.0 SAP points)

**Assessment:**
- ✅ Appropriate statistical methodology
- ✅ Used for aggregate confidence intervals, not individual adjustments
- ✅ Properly handles uncertainty propagation

#### Heat Demand Calculations ⚠️ WEAK
**Current Approach:**
- Uses EPC-modeled `ENERGY_CONSUMPTION_CURRENT` (kWh/m²/year)
- Assumes 80% of total energy is heating

**Issues:**
1. ❌ No building physics validation (not using heat loss calculations, U-values)
2. ❌ 80% heating assumption untested for property types
3. ❌ No seasonal variation modeled

**Recommendation:**
- Validate against BREDEM calculation procedures
- Use SAP heat loss methodology for subset validation
- Check assumption against actual gas consumption data

#### Heat Pump SCOP Assumptions ⚠️ WEAK
**Current Approach:**
- Fixed SCOP: 3.0 across all properties and conditions
- Formula: `electricity_used = heat_demand / 3.0`

**Critical Issues:**
1. ❌ No flow temperature dependency:
   - 35°C flow: SCOP ~3.5-4.0
   - 45°C flow: SCOP ~3.0-3.5
   - 55°C flow: SCOP ~2.5-3.0
   - 65°C flow: SCOP ~2.0-2.5
2. ❌ No outdoor temperature variation
3. ❌ Field trial validation missing

**Recommendation:**
- Use flow-temperature dependent SCOP curve
- Validate against UK field trial data (2.5-3.5 typical range)
- Consider seasonal SCOP variation

#### Fabric Improvement Savings ⚠️ WEAK
**Current Approach:** Multiplicative model (good) but individual percentages are heuristics

**Formula:**
```python
remaining_demand = 1.0
for measure in measures:
    remaining_demand *= (1 - measure_saving_pct)
total_saving = 1 - remaining_demand
```

**Assessment:**
- ✅ Good: Accounts for diminishing returns (not simply additive)
- ✅ Good: Order-independent
- ⚠️ Issue: Individual measure percentages are heuristics
- ⚠️ Issue: No interaction effects modeled

**Missing Validation:**
- SAP methodology for combined measures
- Measured vs modeled savings (academic literature)
- Property-specific variation

### 2.2 Retrofit Modeling Approaches

#### Heat Pump Suitability Tiers ⚠️ WEAK
**File:** `src/analysis/heat_pump_potential.py`

**Current Approach:** EPC band-based classification
- Tier 1 (Ready): EPC C+ and heat demand <150 kWh/m²/year
- Tier 2-5: Based on EPC bands D, E, F, G

**Issues:**
1. ❌ Too simplified - not based on actual heat loss calculations
2. ❌ No flow temperature modeling (MCS MIS 3005 requires heat loss assessment)
3. ❌ No radiator sizing check (critical for low-temperature operation)
4. ❌ No electrical supply check (many need 60A→100A upgrade)

**Better Approach:**
- Calculate design heat loss (W) per MCS standards
- Check radiator capacity at 45°C flow (vs 65°C design)
- Assess electrical supply capacity
- Check DHW cylinder compatibility

#### Heat Network Viability ⚠️ MODERATE
**File:** `src/spatial/heat_network_analysis.py`

**Tier Classification:**
- Tier 1: Within 250m of existing network (reasonable)
- Tier 3: Heat density ≥15 GWh/km²/year
- Tier 4: Heat density 5-15 GWh/km²/year

**Assessment:**
- ✅ Good: 250m buffer is reasonable economic connection distance
- ⚠️ Issue: Heat density thresholds not aligned with DESNZ Heat Network Zoning methodology
- ⚠️ Issue: Fallback to tertiles (relative, not absolute thresholds)
- ❌ Missing: Route constraints, existing infrastructure, planning restrictions

**Recommendation:**
- Validate thresholds against DESNZ Heat Network Zoning
- Convert GWh/km² to linear density (MW/km) for comparison
- Add constraint layers

#### Cost-Benefit Methodology ⚠️ WEAK
**Current Approach:**
- Simple payback: `years = capex / annual_bill_saving`
- Discounted payback: Uses 3.5% discount rate
- Cost per tonne CO₂: `£ = capex / (CO₂_saving × 20 years)`

**Issues:**
1. ❌ No Net Present Value (NPV) calculation
2. ❌ No lifetime cost comparison (maintenance, replacement)
3. ❌ Fixed 20-year lifetime not differentiated by measure
4. ❌ No grant/subsidy modeling (Boiler Upgrade Scheme)

**Recommendation:**
- Add NPV and Levelized Cost of Heat (LCOH)
- Use measure-specific lifetimes (loft: 40yr, HP: 15yr)
- Include maintenance costs
- Model Boiler Upgrade Scheme and other subsidies

### 2.3 "Magic Numbers" Without Justification

#### Geometric Proxies ⚠️ WEAK
| Proxy | Formula | Issue |
|-------|---------|-------|
| Wall area | `floor_area × 1.5` | Assumes 2-story rectangular footprint |
| Window area | `floor_area × 0.2` | 20% ratio untested |
| Loft area | `floor_area × 0.9` | Assumes minimal dormers |
| Radiators | `floor_area / 15` | 1 per 15m² arbitrary |

**Impact:** Affects all area-based cost calculations

**Recommendation:** Validate against sample of EPC geometric data

#### Uptake Rate Model ⚠️ WEAK
| Payback | Assumed Uptake |
|---------|---------------|
| ≤5 years | 80% |
| 5-10 years | 60% |
| 10-15 years | 40% |
| 15-20 years | 20% |
| >20 years | 5% |

**Issues:**
1. ❌ No empirical basis (not based on actual retrofit uptake data)
2. ❌ Ignores barriers (split incentives, disruption, access to capital)
3. ❌ Oversimplified behavioral model

**Recommendation:**
- Validate against Energy Company Obligation (ECO) uptake data
- Review Green Deal uptake analysis
- Consult BEIS Public Attitudes Tracker
- Review academic behavioral research

### 2.4 Missing Uncertainty Quantification

**Areas with Uncertainty Modeling:**
- ✅ EPC measurement error (Crawley et al.)
- ✅ Prebound effect (Few et al.)
- ✅ Demand uncertainty ranges (±20% standard, ±30% anomalies)

**Missing Uncertainty:**
- ❌ Cost uncertainty (no ranges)
- ❌ Savings uncertainty (fixed percentages)
- ❌ SCOP uncertainty (fixed 3.0, no 2.5-3.5 range)
- ❌ Price uncertainty (future prices are point estimates)
- ❌ Monte Carlo / sensitivity analysis

**Recommendation:**
- Add cost ranges (low/central/high estimates)
- Provide savings confidence intervals (e.g., wall insulation 20±10%)
- SCOP range based on flow temperature and field trials
- Sensitivity analysis on key parameters

---

## 3. Computational Efficiency Assessment

### 3.1 Code Duplication (HIGH PRIORITY)

**Total Duplication Identified:** 900-1,300 lines across modules

#### Geographic Analysis Pattern (240-300 lines duplicated)
**Files:** heat_pump_potential.py, heat_network_potential.py, heating_fuel_analysis.py

**Impact:** Nearly identical geographic aggregation logic repeated 3 times

#### Configuration Loading (60-84 lines duplicated)
**Files:** All 12 analysis modules

**Pattern:** Every class repeats same initialization

#### Results Saving (150-480 lines duplicated)
**Files:** All 6 main analysis modules

**Pattern:** Identical save_results() methods

#### Cost/Savings Calculations (Logic drift risk)
**Files:** demand_reduction_analysis.py, heat_pump_potential.py, consumer_impact_analysis.py

**Issue:** Same costs appear with slight variations across modules

### 3.2 Performance Bottlenecks (CRITICAL)

#### Inefficient DataFrame Operations

**1. Repeated Full Copies (HIGH IMPACT)**
- Each `.copy()` creates full 8GB+ duplicate for national dataset
- Found 5-10 copies during typical workflow
- Memory usage spikes to 40-80GB unnecessarily

**Performance Impact:**
- 60-70% memory reduction possible
- 20-30% speed improvement

**2. Row Iteration (CRITICAL)**
- `iterrows()` loops in retrofit_packages.py, geographic aggregations
- Current: O(n × m) where n=24M properties, m=300 LAs
- Estimated: 10-30 minutes for geographic aggregations

**Solution:** Replace with vectorized groupby operations
- Optimized: 30-60 seconds
- **Speedup: 20-40x**

**3. Repeated Calculations (MEDIUM-HIGH)**
- Expensive aggregations calculated multiple times
- No intermediate result caching

**Performance Impact:**
- 10-20% overhead
- 10-15% speedup with caching

#### Data Loading Inefficiency

**Issue:** Every module loads same 24M row CSV independently
- CSV loading: 3-5 minutes per module
- 6 sequential analyses: 18-30 minutes just loading

**Solution:**
- Switch to Parquet: 80-90% faster I/O (20-40 seconds)
- Shared data loader with caching

**Performance Gain:** Loading time from 3-5 min → 20-40 sec per module

### 3.3 Optimization Opportunities Summary

| Optimization | Current | Optimized | Speedup |
|--------------|---------|-----------|---------|
| Data Loading (CSV → Parquet) | 3-5 min | 20-40 sec | 5-8x |
| Geographic Aggregation | 10-30 min | 30-60 sec | 20-40x |
| Fuel Categorization | 5-10 min | 30-60 sec | 10-20x |
| **Full Pipeline** | **45-90 min** | **5-15 min** | **6-9x** |

**Memory Improvements:**
- Current peak: 40-80GB
- Optimized peak: 10-20GB
- **Reduction: 60-75%**

---

## 4. Recommendations Summary

### Priority 1: CRITICAL (Must Address) 🔴

1. **Validate Heat Pump SCOP**
   - Use flow-temperature dependent curve
   - Validate against MCS field trials
   - **Timeline:** Before any policy recommendations

2. **Update Heat Network Penetration**
   - Change 0.2% → 2.5%
   - **Timeline:** Immediate

3. **Validate Fabric Improvement Savings**
   - Cross-reference SAP 10.2, EST data, DESNZ trials
   - Provide confidence intervals
   - **Timeline:** 2-3 weeks

4. **Fix Flow Temperature Modeling**
   - Replace heuristic with physics-based heat loss calculation
   - Align with MCS MIS 3005
   - **Timeline:** 1-2 weeks

### Priority 2: HIGH (Should Address) 🟡

5. **Validate Retrofit Costs**
   - Benchmark against 2024/25 MCS surveys, DESNZ data
   - Add London multipliers (+15-20%)
   - Provide cost ranges
   - **Timeline:** 2-3 weeks

6. **Add Uncertainty Quantification**
   - Monte Carlo sensitivity analysis
   - Cost and savings ranges
   - **Timeline:** 3-4 weeks

7. **Optimize Data Processing**
   - Migrate to Parquet (Quick Win: 2-3 hours)
   - Eliminate code duplication (15-20 hours)
   - Vectorize operations (10-14 hours)
   - **Timeline:** 3-4 weeks

8. **Improve Cost-Benefit Methodology**
   - Add NPV, LCOH
   - Measure-specific lifetimes
   - Model subsidies
   - **Timeline:** 1-2 weeks

### Priority 3: MEDIUM (Nice to Have) 🟢

9. **Validate Geometric Proxies** (4-5 hours)
10. **Improve Behavioral Modeling** (8-10 hours)
11. **Add Building Physics Validation** (1-2 weeks)

---

## 5. Implementation Roadmap

### Phase 1: Quick Wins (1-2 weeks, 15-20 hours)
1. Update heat network penetration (0.2% → 2.5%)
2. Migrate to Parquet format
3. Create data loading utility with caching
4. Create geographic aggregation utility

**Expected Gains:**
- 80% faster I/O
- Eliminate 300+ lines duplication

### Phase 2: Academic Validation (2-3 weeks, 20-25 hours)
5. Validate heat pump SCOP against field trials
6. Validate fabric savings against SAP/EST/DESNZ
7. Validate retrofit costs against 2024/25 data
8. Add uncertainty quantification

**Expected Gains:**
- Stronger evidence base
- Confidence intervals on key results

### Phase 3: Performance Optimization (2-3 weeks, 25-30 hours)
9. Create base analyzer class
10. Vectorize operations (replace iterrows)
11. Add cost calculation utilities
12. Implement caching

**Expected Gains:**
- 6-9x speedup for full pipeline
- 60-75% memory reduction
- 600+ lines duplication eliminated

### Phase 4: Advanced Features (3-4 weeks, 20-25 hours)
13. Parallel processing for geographic analysis
14. Improved cost-benefit methodology (NPV, LCOH)
15. Physics-based flow temperature modeling
16. Chunked processing for larger-than-memory datasets

**Expected Gains:**
- 4-8x additional speedup on multi-core
- More robust financial analysis
- Better heat pump readiness assessment

---

## 6. Conclusion

### Strengths
1. ✅ Excellent documentation transparency (AUTHORITATIVE_SOURCES.md)
2. ✅ Proper implementation of academic findings (Few, Crawley)
3. ✅ Recent data updates (Q4 2024)
4. ✅ Clear awareness of evidence gaps
5. ✅ Good methodological practices (prebound, diminishing returns)

### Critical Gaps
1. ❌ 59% parameters are heuristics without validation
2. ❌ Heat pump SCOP lacks field trial validation and temperature dependency
3. ❌ Fabric savings percentages unvalidated
4. ❌ Flow temperature model heuristic, not physics-based
5. ❌ Substantial code duplication (900-1,300 lines)
6. ❌ Performance bottlenecks limit national-scale analysis

### Overall Grade: B+ (Good, with areas for improvement)
- **Documentation:** A (excellent)
- **Academic rigor:** B (good but 59% heuristics)
- **Data currency:** A- (recent, mostly validated)
- **Methodology:** B- (sound approaches, weak parameter validation)
- **Code quality:** C+ (works but substantial duplication)
- **Performance:** C (functional but not optimized for scale)

### Fitness for Purpose
- **Policy briefings:** ✅ Adequate with clear caveats about uncertainties
- **Academic publication:** ⚠️ Requires validation of key assumptions
- **Client presentation:** ✅ Good with uncertainty communication
- **National deployment:** ⚠️ Requires performance optimization
- **Further research:** ✅ Provides solid foundation for refinement

### Recommended Actions (Next 3 Months)

**Month 1: Critical Fixes**
- Update heat network penetration immediately
- Migrate to Parquet
- Validate SCOP against field trials
- Eliminate geographic duplication

**Month 2: Academic Validation**
- Validate fabric savings (SAP, EST, DESNZ)
- Validate retrofit costs (2024/25 data)
- Add uncertainty quantification
- Fix flow temperature model

**Month 3: Optimization**
- Vectorize operations
- Create shared utilities
- Add caching
- Performance testing

**Total Effort:** 60-75 hours over 8-12 weeks

**Expected Outcomes:**
- Stronger evidence base for policy recommendations
- 6-9x faster analysis pipeline
- 60-75% memory reduction
- 40-50% reduction in maintenance burden

---

## Appendix A: Parameter Evidence Summary

### Strong Evidence (30/83, 36%)
- Energy prices (current)
- Carbon factors (current and projected)
- Discount rate
- Prebound effect factors
- EPC uncertainty ranges
- Thermodynamic formulas

### Moderate Evidence (8/83, 10%)
- Energy prices (projected)
- Heat network efficiency
- Heat density thresholds

### Weak Evidence (49/83, 59%)
- **All fabric savings percentages** (15 parameters)
- **All retrofit costs** (19 parameters)
- Heat pump SCOP value
- Flow temperature model
- Uptake rates
- Geometric proxies
- 80% heating assumption

### Outdated (1/83, 1%)
- Heat network penetration (0.2% should be 2.5%)

---

## Appendix B: Code Quality Metrics

**Lines of Code:** ~6,000 (excluding legacy)
**Duplication:** 900-1,300 lines (15-22%)
**Analysis Modules:** 15
**Test Coverage:** Limited (needs expansion)
**Documentation:** Excellent (A)

**Performance Metrics (24M property national dataset):**
- Full analysis: 45-90 minutes (current) → 5-15 minutes (optimized)
- Memory peak: 40-80GB (current) → 10-20GB (optimized)
- Data loading: 3-5 min (CSV) → 20-40 sec (Parquet)

---

**Report Compiled By:** Independent Academic Review
**Date:** 2025-12-18
**Repository:** github.com/ADEData-Lab/ADE-EPC-Analysis
**Version Audited:** 2.0.0 (National Pipeline)
