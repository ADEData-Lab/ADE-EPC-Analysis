# London GIS Data Integration

The Heat Street EPC Analysis previously downloaded GIS data from London Datastore
to enhance spatial analysis capabilities. That London-only workflow has been
retired; the downloader lives under `src/legacy/acquisition` for reference and
is no longer part of the maintained pipeline.

## What's Included

The GIS dataset from London Datastore contains:

### 🗺️ Heat Network Data
- **Existing District Heating Networks** - Currently operating heat networks across London (8 networks)
- **Potential Heat Network Zones** - Areas identified for potential heat network development
- **Potential Transmission Lines** - Proposed transmission line routes

### 🔥 Heat Demand & Supply Data
- **Heat Load Data** - Building-level heat demand data for all 33 London boroughs (488+ buildings per borough)
  - Building addresses and postcodes
  - Fuel consumption and heating systems
  - Number of dwellings
  - CO2 emissions
  - Installed capacity

- **Heat Supply Sources** - Heat generation sources across London
  - Power stations
  - Waste facilities
  - CHP installations
  - Energy centres

### 🏗️ Development Database
- **London Development Database (2010)** - Historical development projects data

## Data Source

**London Datastore - London Heat Map GIS Data**
- URL: https://data.london.gov.uk/dataset/london-heat-map
- Direct Download: https://data.london.gov.uk/download/2ogw5/1c75726b-0b5e-4f2c-9fd6-25fc83b32454/GIS_All_Data.zip
- Size: ~2.2 MB (compressed)
- Last Updated: April 2012
- Format: ESRI Shapefiles (.shp)

## How to Download

### Option 1: Manual Download (Most Reliable)

**If automatic download fails, follow these steps:**

1. **Download the ZIP file**:
   - Visit: https://data.london.gov.uk/download/2ogw5/1c75726b-0b5e-4f2c-9fd6-25fc83b32454/GIS_All_Data.zip
   - Or use browser/download manager to save `GIS_All_Data.zip`

2. **Create the directory**:
   ```bash
   # Create directory if it doesn't exist
   mkdir -p data/external
   ```

3. **Extract the ZIP file**:
   - Extract `GIS_All_Data.zip` to: `data/external/`
   - Result should be: `data/external/GIS_All_Data/` folder
   - Inside should be: `Heat Loads/`, `Heat Supply/`, `Networks/` folders

4. **Verify structure**:
   ```
   data/external/GIS_All_Data/
   ├── Heat Loads/            (33 shapefiles, one per borough)
   ├── Heat Supply/           (33 shapefiles)
   ├── Networks/              (4 network shapefiles)
   └── LDD 2010/              (Development database)
   ```

**✅ Once extracted to the correct location, the spatial analysis will automatically detect and use the data!**

### Option 2: Automatic Download

The interactive CLI will automatically prompt you to download GIS data:

```powershell
.\run-conda.ps1  # or run-conda.bat
```

When prompted:
```
London GIS Data (Optional)

This analysis can optionally use GIS data from London Datastore for:
  • Existing district heating networks
  • Potential heat network zones
  • Heat load and supply data by borough

? Download London GIS data? (~2 MB, required for spatial analysis) (Y/n)
```

### Option 3: Python API

Use the downloader directly in your code:

```python
from src.legacy.acquisition.london_gis_downloader import LondonGISDownloader

# Initialize downloader
downloader = LondonGISDownloader()

# Download and extract data
downloader.download_and_prepare()

# Check what's available
summary = downloader.get_data_summary()
print(f"Heat load files: {summary['heat_load_files']}")
print(f"Network files: {summary['network_files']}")
print(f"Heat supply files: {summary['heat_supply_files']}")

# Get specific file paths
networks = downloader.get_network_files()
print(f"Existing networks: {networks['existing']}")

heat_loads = downloader.get_heat_load_files(borough='Islington')
print(f"Islington heat loads: {heat_loads}")
```

## Data Structure

After download, data is organized as:

```
data/
└── external/
    ├── GIS_All_Data.zip          # Original download
    └── GIS_All_Data/              # Extracted data
        ├── Heat Loads/            # 33 borough heat load shapefiles
        │   ├── Heat_Loads_20120411Barking_and_Dagenham.shp
        │   ├── Heat_Loads_20120411Islington.shp
        │   └── ...
        ├── Heat Supply/           # Heat source data by borough
        │   ├── Heat_Supply_20120411Islington.shp
        │   └── ...
        ├── Networks/              # District heating networks
        │   ├── 2.3.1_Existing_DH_Networks.shp
        │   ├── 2.3.2.2._Potential_DH_Networks.shp
        │   └── ...
        └── LDD 2010/              # London Development Database
            └── ...
```

## Usage in Analysis

### Heat Network Tier Classification

The spatial analysis module automatically uses downloaded GIS data:

```python
from src.spatial.heat_network_analysis import HeatNetworkAnalyzer

analyzer = HeatNetworkAnalyzer()

# Load heat networks (automatically uses downloaded data)
heat_networks, heat_zones = analyzer.load_london_heat_map_data()

# Classify properties by heat network tiers
properties_gdf = analyzer.classify_heat_network_tiers(
    properties=df_validated,
    heat_networks=heat_networks
)
```

### Heat Network Tiers

Properties are classified into 5 tiers:

1. **Tier 1** - Within 250m of existing heat network
2. **Tier 2** - Within planned Heat Network Zone
3. **Tier 3** - High heat density area (>15 GWh/km²)
4. **Tier 4** - Medium heat density area (5-15 GWh/km²)
5. **Tier 5** - Low heat density area (<5 GWh/km²)

This classification helps determine:
- Connection viability to existing networks
- Economic feasibility of heat network expansion
- Priority areas for heat network development

## Requirements

### For Basic Download
- No additional dependencies required
- Uses standard Python libraries + wget

### For Spatial Analysis (Reading Shapefiles)
If you want to actually use the GIS data for spatial analysis, you need optional spatial dependencies:

```bash
pip install -r requirements-spatial.txt
```

This includes:
- geopandas
- shapely
- fiona
- GDAL (see [WINDOWS_INSTALLATION.md](WINDOWS_INSTALLATION.md) for Windows setup)

## Data Fields

### Heat Load Files
Key fields in heat load shapefiles:
- `Name` - Building name
- `Address` - Building address
- `Postcode` - Postcode
- `Borough` - London borough
- `Typology` - Building type
- `Heating_su` - Heating supply type
- `Fuel_sourc` - Primary fuel source
- `Fuel_consu` - Annual fuel consumption
- `Number_of_` - Number of dwellings
- `CO2_emissi` - CO2 emissions

### Existing DH Networks
Key fields in network shapefiles:
- `Name` - Network name
- `Status` - Network status
- `AreaCovere` - Area covered
- `EnergyCent` - Energy centre location
- `Fuelsource` - Fuel source
- `Heatgenera` - Heat generation capacity
- `Installedp` - Installed power capacity

## Troubleshooting

### Download Fails with SSL Error

The download script automatically handles SSL certificate issues by using `wget --no-check-certificate`. If you encounter issues:

1. Try the standalone script: `.\download-gis-data.ps1`
2. Manual download: Visit the URL directly and place `GIS_All_Data.zip` in `data/external/`

### Cannot Read Shapefiles

If you get errors reading shapefiles:

1. **Check GDAL installation** (required for geopandas):
   ```powershell
   python -c "import geopandas; print('OK')"
   ```

2. **Install spatial dependencies**:
   ```powershell
   pip install -r requirements-spatial.txt
   ```

3. **Windows users**: See [WINDOWS_INSTALLATION.md](WINDOWS_INSTALLATION.md) for GDAL setup

### Data Already Downloaded

If you've already downloaded the data, the system will detect it:

```
✓ GIS data already downloaded
    Heat load files: 33
    Network files: 4
    Heat supply files: 33
```

To force re-download:
```python
downloader.download_and_prepare(force_redownload=True)
```

## Data Notes

⚠️ **Data Age**: This GIS data is from April 2012. While the spatial patterns remain relevant:
- Some heat networks may have expanded since 2012
- New networks may have been built
- Some heat sources may have changed

For the most current data, visit:
- [London Heat Map](https://www.london.gov.uk/programmes-strategies/environment-and-climate-change/energy/london-heat-map)
- [London Datastore](https://data.london.gov.uk/)

## Related Documentation

- [Interactive Mode Guide](INTERACTIVE_MODE.md) - Using the interactive CLI
- [API Usage](API_USAGE.md) - EPC API data download
- [Windows Installation](WINDOWS_INSTALLATION.md) - Installing spatial dependencies on Windows
- [Quickstart Guide](QUICKSTART.md) - Getting started
