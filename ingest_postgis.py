import geopandas as gpd
from sqlalchemy import create_engine

DB_URL = "postgresql://postgres:password@localhost:5432/floodlens_db"
engine = create_engine(DB_URL)

def ingest_to_postgis(geojson_path, table_name):
    print(f"Loading {geojson_path}...")
    gdf = gpd.read_file(geojson_path)
    
    if gdf.crs != 'EPSG:4326':
        gdf = gdf.to_crs('EPSG:4326')
        
    gdf.to_postgis(name=table_name, con=engine, if_exists='replace', index=False)
    print(f"✅ Successfully ingested into {table_name}")

if __name__ == '__main__':
    ingest_to_postgis('flood_polygons_web.geojson', 'flood_extent_2017')
    print('Integration script ready for backend team!')
