import os
import re
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from screener_core import jalankan_pemindaian, generate_analisa_ai, muat_daftar_issi

st.set_page_config(page_title="ARB Hunter ISSI Screener", page_icon="🕌", layout="wide")

st.title("🕌 AI Screener: ARB Hunter & Rebound (Khusus Saham ISSI)")
st.caption("Terhubung ke TradingView Screener • Dilengkapi Kalkulator Risk Management ATR & Analisa Sentimen AI")

# ================= FUNGSI BACA FILE EXCEL / CSV UPLOAD =================
def ekstrak_kode_dari_file(uploaded_file):
    try:
        if uploaded_file.name.endswith(".csv"):
            df_up = pd.read_csv(uploaded_file)
        else:
            df_up = pd.read_excel(uploaded_file)
        
        kode_ditemukan = set()
        for col_name in df_up.columns:
            for val in df_up[col_name].dropna():
                teks = str(val).strip().upper()
                if re.fullmatch(r"[A-Z]{4}", teks): # Ambil kode saham 4 huruf (misal: AADI, BRIS)
                    kode_ditemukan.add(teks)
        return kode_ditemukan
    except Exception as e:
        st.sidebar.error(f"Gagal membaca file: {e}")
        return None

# ================= SIDEBAR PENGATURAN FILTER =================
with st.sidebar:
    st.header("📂 Daftar Saham ISSI")
    file_issi = st.file_uploader("Upload Excel/CSV ISSI (Opsional)", type=["xlsx", "xls", "csv"])
    
    custom_set = None
    if file_issi is not None:
        custom_set = ekstrak_kode_dari_file(file_issi)
        if custom_set:
            st.success(f"Terbaca {len(custom_set)} emiten dari file unggahan!")
    else:
        jumlah_default = len(muat_daftar_issi())
        st.info(f"Menggunakan daftar tersimpan ({jumlah_default} emiten ISSI).")

    st.divider()
    st.header("⚙️ Parameter Saringan")
    pilihan_mode = st.radio(
        "Mode Strategi:",
        [
            "SORE (Mentok ARB -20% s/d -35%)",
            "KOREKSI (Turun Tajam -7% s/d -18%)",
            "PAGI (Morning Rebound > +1%)"
        ]
    )
    if "SORE" in pilihan_mode:
        mode_sesi = "SORE"
    elif "KOREKSI" in pilihan_mode:
        mode_sesi = "KOREKSI"
    else:
        mode_sesi = "PAGI"
    
    min_trx = st.slider("Minimal Transaksi (Miliar Rp)", 1.0, 50.0, 3.0, step=1.0)
    min_vol = st.slider("Minimal Lonjakan Volume (x Rata-rata)", 0.5, 5.0, 1.2, step=0.1)
    max_rsi = st.slider("Maksimal RSI (14)", 15, 50, 35)
    hanya_uptrend = st.checkbox("Hanya Saham Uptrend (> EMA200)", value=False)
    
    st.divider()
    api_key_input = st.text_input("Gemini API Key", type="password", value=os.environ.get("GEMINI_API_KEY", ""))
    tombol_scan = st.button("🔍 Mulai Pindai Pasar Sekarang", type="primary", use_container_width=True)

# ================= EKSEKUSI PEMINDAIAN =================
if tombol_scan:
    with st.spinner("Memindai seluruh saham ISSI dari TradingView & menghitung level ATR..."):
        df_hasil = jalankan_pemindaian(
            sesi=mode_sesi,
            min_transaksi_miliar=min_trx,
            min_vol_ratio=min_vol,
            max_rsi=max_rsi,
            hanya_uptrend=hanya_uptrend,
            custom_issi_set=custom_set
        )
        st.session_state["hasil_scan"] = df_hasil
        st.session_state["mode_sesi"] = mode_sesi

# ================= TAMPILAN HASIL & CHART =================
if "hasil_scan" in st.session_state:
    df = st.session_state["hasil_scan"]
    
    if df.empty:
        st.warning("Belum ada saham ISSI yang memenuhi kriteria saat ini. Coba pilih mode **KOREKSI (-7% s/d -18%)** atau longgarkan filter RSI/Transaksi.")
    else:
        st.success(f"Ditemukan **{len(df)} kandidat** saham ISSI yang lolos saringan!")
        
        kolom_tampil = [
            "Kode", "Harga", "Change (%)", "Transaksi (M)", "RSI", 
            "Jarak BB (%)", "Tren", "Stop Loss", "Risiko (%)", 
            "TP 1", "Profit 1 (%)", "TP 2", "Profit 2 (%)", "R:R"
        ]
        st.dataframe(df[kolom_tampil], use_container_width=True, hide_index=True)

        col1, col2 = st.columns([1.2, 1])
        
        with col1:
            st.subheader("📈 Grafik Interaktif TradingView")
            kode_terpilih = st.selectbox("Pilih saham untuk melihat grafik:", df["Kode"].tolist())
            
            tv_widget = f"""
            <div class="tradingview-widget-container">
              <div id="tradingview_chart"></div>
              <script type="text/javascript" src="https://tradingview.com"></script>
              <script type="text/javascript">
              new TradingView.widget({{
                "width": "100%",
                "height": 420,
                "symbol": "IDX:{kode_terpilih}",
                "interval": "15",
                "timezone": "Asia/Jakarta",
                "theme": "dark",
                "style": "1",
                "locale": "id",
                "toolbar_bg": "#f1f3f6",
                "enable_publishing": false,
                "studies": ["BB@tv-basicstudies", "RSI@tv-basicstudies", "MACD@tv-basicstudies"],
                "container_id": "tradingview_chart"
              }});
              </script>
            </div>
            """
            components.html(tv_widget, height=430)

        with col2:
            st.subheader("🤖 Analisa Strategi & Berita oleh AI")
            if api_key_input:
                with st.spinner("AI sedang membaca berita terbaru & mengevaluasi rasio Risk/Reward..."):
                    analisa = generate_analisa_ai(df, st.session_state["mode_sesi"], api_key_input)
                    st.markdown(analisa)
            else:
                st.info("Masukkan **Gemini API Key** di sidebar kiri untuk mengaktifkan evaluasi berita & strategi otomatis oleh AI.")
            
            with st.expander("📰 Lihat Berita Mentah Emiten"):
                for _, r in df.iterrows():
                    st.markdown(f"**{r['Kode']}**")
                    st.text(r["Berita"])
