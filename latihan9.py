import io
import json
import math
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import ezdxf
import folium
from streamlit_folium import st_folium
from pyproj import Transformer

# Set tetapan muka surat Streamlit
st.set_page_config(page_title="Sistem Maklumat Geografi (GIS)", layout="wide")

# ==========================================
# FUNGSI HEBAT / MATEMATIK GEOMETRI
# ==========================================

# 1. Luas Poligon (Shoelace Formula)
def calculate_polygon_area(x, y):
    n = len(x)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += x[i] * y[j]
        area -= x[j] * y[i]
    return abs(area) / 2.0

# 2. Kira Jarak dan Bearing antara 2 titik
def calculate_bearing_distance(e1, n1, e2, n2):
    de = e2 - e1
    dn = n2 - n1
    distance = math.sqrt(de**2 + dn**2)
    
    angle = math.degrees(math.atan2(de, dn))
    if angle < 0:
        angle += 360
        
    deg = int(angle)
    minutes = int((angle - deg) * 60)
    seconds = round(((angle - deg) * 60 - minutes) * 60)
    
    if seconds == 60:
        minutes += 1
        seconds = 0
    if minutes == 60:
        deg = (deg + 1) % 360
        minutes = 0

    bearing_str = f"{deg}°{minutes:02d}'{seconds:02d}\""
    return distance, bearing_str

# 3. Penjana Fail DXF
def generate_dxf(df):
    doc = ezdxf.new()
    msp = doc.modelspace()
    
    doc.layers.add("STESEN", color=1)
    doc.layers.add("POLIGON", color=5)
    doc.layers.add("TEKS_BEARING", color=3)

    points = [(row['E'], row['N']) for _, row in df.iterrows()]
    points_closed = points + [points[0]]

    msp.add_lwpolyline(points_closed, dxfattribs={'layer': 'POLIGON'})

    for _, row in df.iterrows():
        stn = str(row['STN']) if 'STN' in df.columns else "STN"
        e, n = row['E'], row['N']
        msp.add_point((e, n), dxfattribs={'layer': 'STESEN'})
        msp.add_text(stn, dxfattribs={'layer': 'STESEN', 'height': 2.0}).set_placement((e + 1, n + 1))

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue()

# 4. Penjana Fail GeoJSON
def generate_geojson(df):
    coordinates = [[row['E'], row['N']] for _, row in df.iterrows()]
    coordinates.append(coordinates[0])

    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [coordinates]
            },
            "properties": {"Name": "Sempadan Poligon"}
        }
    ]

    for _, row in df.iterrows():
        stn = str(row['STN']) if 'STN' in df.columns else "STN"
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row['E'], row['N']]
            },
            "properties": {"Stesen": stn}
        })

    geojson_data = {
        "type": "FeatureCollection",
        "features": features
    }
    return json.dumps(geojson_data, indent=4)

# 5. Penukaran Unjuran Koordinat (Reprojection QGIS Style)
def reproject_coordinates(df, src_epsg):
    """
    Menukar koordinat asal (m) kepada Lat/Lon WGS84 (EPSG:4326) untuk Folium
    """
    df_out = df.copy()
    
    if str(src_epsg) == "4326":
        df_out['lat'] = df_out['N']
        df_out['lon'] = df_out['E']
        return df_out

    # Cipta transformer dari CRS sumber ke EPSG:4326 (WGS84 Lat/Lon)
    transformer = Transformer.from_crs(f"EPSG:{src_epsg}", "EPSG:4326", always_xy=True)
    
    # always_xy=True memulangkan (Longitude, Latitude) -> (X, Y)
    lons, lats = transformer.transform(df['E'].values, df['N'].values)
    
    df_out['lon'] = lons
    df_out['lat'] = lats
    return df_out


# ==========================================
# SEKSYEN UTAMA STREAMLIT
# ==========================================

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

try:
    st.image("logo puo.png", width=200)
except Exception:
    pass

st.title("Sistem Maklumat Geografi (GIS)")

# --- 1. LOG MASUK ---
if not st.session_state["logged_in"]:
    st.write("Sila masukkan maklumat anda di bawah:")
    username = st.text_input("Nama Pengguna (Username)")
    password = st.text_input("Kata Laluan (Password)", type="password")

    if st.button("Log Masuk"):
        if username == "admin" and password == "1234":
            st.session_state["logged_in"] = True
            st.success("Log masuk berjaya!")
            st.rerun()
        elif username == "" or password == "":
            st.warning("Sila isi kedua-dua ruangan nama pengguna dan kata laluan.")
        else:
            st.error("Nama pengguna atau kata laluan salah.")

# --- 2. HALAMAN UTAMA ---
else:
    st.sidebar.success("Log masuk sebagai: Admin")
    if st.sidebar.button("Log Keluar"):
        st.session_state["logged_in"] = False
        st.rerun()

    st.subheader("Muat Naik Fail Koordinat & Visualisasi Peta")

    uploaded_file = st.file_uploader("Muat naik fail CSV koordinat", type=["csv"])

    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            st.write("### Data Koordinat Asal:")
            st.dataframe(df)

            if 'E' in df.columns and 'N' in df.columns:
                
                # --- TETAPAN UNJURAN (CRS) & LAYER DI SIDEBAR ---
                st.sidebar.markdown("---")
                st.sidebar.subheader("🌐 Tetapan Unjuran Peta (CRS)")
                
                crs_options = {
                    "Kertau / RSO Malaya (EPSG:3168)": "3168",
                    "Cassini-Soldner Perak (EPSG:2385)": "2385",
                    "Cassini-Soldner Selangor/KL (EPSG:2381)": "2381",
                    "Cassini-Soldner Johor (EPSG:2387)": "2387",
                    "WGS 84 / UTM Zone 47N (EPSG:32647)": "32647",
                    "WGS 84 / UTM Zone 48N (EPSG:32648)": "32648",
                    "WGS 84 / Geografik Lat Lon (EPSG:4326)": "4326"
                }
                
                selected_crs_label = st.sidebar.selectbox(
                    "Pilih Sistem Koordinat Asal CSV (Sama seperti QGIS):",
                    options=list(crs_options.keys())
                )
                selected_epsg = crs_options[selected_crs_label]

                custom_epsg = st.sidebar.text_input("Atau masukkan Kod EPSG Lain (Cth: 3168):", value="")
                if custom_epsg.strip():
                    selected_epsg = custom_epsg.strip()

                st.sidebar.markdown("---")
                st.sidebar.subheader("🎛️ Kawalan Layer (Plot Visual)")
                show_polygon = st.sidebar.checkbox("Paparkan Layer Poligon", value=True)
                show_points = st.sidebar.checkbox("Paparkan Layer Titik Stesen", value=True)
                show_bearing_dist = st.sidebar.checkbox("Paparkan Layer Bearing & Jarak", value=True)

                e_coords = df['E'].tolist()
                n_coords = df['N'].tolist()
                area = calculate_polygon_area(e_coords, n_coords)

                # ==========================================
                # PLOT GRAPH MATPLOTLIB (Local Coordinates)
                # ==========================================
                st.write("### Plot Visualisasi Poligon (Koordinat Tempatan):")
                fig, ax = plt.subplots(figsize=(8, 6))

                e_plot = e_coords + [e_coords[0]]
                n_plot = n_coords + [n_coords[0]]

                if show_polygon:
                    ax.plot(e_plot, n_plot, color='blue', linestyle='-', linewidth=2, label='Sempadan Poligon')
                    ax.fill(e_plot, n_plot, color='skyblue', alpha=0.3)

                if show_points:
                    ax.scatter(e_coords, n_coords, color='red', zorder=5, label='Titik Stesen')
                    if 'STN' in df.columns:
                        for idx, row in df.iterrows():
                            ax.annotate(str(row['STN']), (row['E'], row['N']), textcoords="offset points", xytext=(5,5), fontweight='bold')

                if show_bearing_dist:
                    n_pts = len(e_coords)
                    for i in range(n_pts):
                        j = (i + 1) % n_pts
                        x1, y1 = e_coords[i], n_coords[i]
                        x2, y2 = e_coords[j], n_coords[j]
                        dist, brg = calculate_bearing_distance(x1, y1, x2, y2)

                        mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
                        text_label = f"{brg}\n{dist:.2f}m"
                        ax.text(mid_x, mid_y, text_label, fontsize=8, color='darkgreen', ha='center', va='center', bbox=dict(boxstyle='square,pad=0.1', facecolor='yellow', alpha=0.5, edgecolor='none'))

                center_e = sum(e_coords) / len(e_coords)
                center_n = sum(n_coords) / len(n_coords)
                ax.text(center_e, center_n, f"Luas:\n{area:.2f} m²", fontsize=10, fontweight='bold', color='darkblue', ha='center', va='center', bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.8, edgecolor='blue'))

                ax.set_title("Plot Poligon Koordinat (E vs N)")
                ax.set_xlabel("Easting (E)")
                ax.set_ylabel("Northing (N)")
                ax.grid(True, linestyle='--', alpha=0.5)
                ax.legend(loc='upper right')
                ax.axis('equal')

                st.pyplot(fig)
                st.info(f"📐 **Luas Poligon:** `{area:.2f}` m²")

                # ==========================================
                # PAPARAN OVERLAY GOOGLE MAPS (FOLIUM)
                # ==========================================
                st.write("### 🛰️ Overlay Poligon di atas Google Maps:")
                
                try:
                    df_geo = reproject_coordinates(df, selected_epsg)
                    
                    center_lat = df_geo['lat'].mean()
                    center_lon = df_geo['lon'].mean()

                    # Papar info debug koordinat
                    st.caption(f"📍 Pusat Peta Hasil Reprojection (EPSG:{selected_epsg}): **Lat:** `{center_lat:.6f}`, **Lon:** `{center_lon:.6f}`")

                    # Buat peta folium asas
                    m = folium.Map(location=[center_lat, center_lon], zoom_start=17, max_zoom=20)

                    # 1. Google Satellite
                    folium.TileLayer(
                        tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                        attr='Google Satellite',
                        name='Google Satelit',
                        max_zoom=20,
                        overlay=False
                    ).add_to(m)

                    # 2. Google Hybrid (Satelit + Nama Jalan)
                    folium.TileLayer(
                        tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
                        attr='Google Hybrid',
                        name='Google Hybrid',
                        max_zoom=20,
                        overlay=False
                    ).add_to(m)

                    # 3. OpenStreetMap (Fail-safe Back-up)
                    folium.TileLayer('openstreetmap', name='OpenStreetMap', overlay=False).add_to(m)

                    # Lukis Poligon (Lokasi Lat/Lon)
                    geo_polygon_coords = [[row['lat'], row['lon']] for _, row in df_geo.iterrows()]
                    
                    folium.Polygon(
                        locations=geo_polygon_coords,
                        color="cyan",
                        weight=3,
                        fill=True,
                        fill_color="blue",
                        fill_opacity=0.4,
                        popup=f"Luas: {area:.2f} m²"
                    ).add_to(m)

                    # Marker Titik Stesen
                    for _, row in df_geo.iterrows():
                        stn_label = str(row['STN']) if 'STN' in df_geo.columns else "Stesen"
                        folium.Marker(
                            location=[row['lat'], row['lon']],
                            popup=f"Stesen: {stn_label}<br>Lat: {row['lat']:.6f}<br>Lon: {row['lon']:.6f}",
                            icon=folium.Icon(color='red', icon='info-sign')
                        ).add_to(m)

                    # Automatik fokus peta ke lingkungan koordinat poligon
                    m.fit_bounds(geo_polygon_coords)

                    # Tambah Kawalan Layer
                    folium.LayerControl().add_to(m)

                    st_folium(m, width=900, height=500)

                except Exception as proj_err:
                    st.error(f"Ralat penukaran unjuran EPSG: {proj_err}")

                # ==========================================
                # EKSPORT FAIL (DXF & GEOJSON)
                # ==========================================
                st.write("### 💾 Eksport Data:")
                col1, col2 = st.columns(2)

                dxf_data = generate_dxf(df)
                col1.download_button(
                    label="📥 Muat Turun Fail DXF (AutoCAD)",
                    data=dxf_data,
                    file_name="poligon_koordinat.dxf",
                    mime="application/dxf"
                )

                geojson_data = generate_geojson(df)
                col2.download_button(
                    label="📥 Muat Turun Fail GeoJSON (GIS)",
                    data=geojson_data,
                    file_name="poligon_koordinat.geojson",
                    mime="application/json"
                )

            else:
                st.error("Fail CSV mesti mengandungi lajur 'E' dan 'N'. Sila semak format fail anda.")

        except Exception as e:
            st.error(f"Ralat semasa membaca/memproses fail: {e}")
            