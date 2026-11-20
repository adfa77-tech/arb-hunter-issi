import os
import streamlit as st
import streamlit.components.v1 as components
from screener_core import jalankan_pemindaian, generate_analisa_ai

st.set_page_config(page_title="ARB Hunter ISSI Screener", page_icon="🕌", layout="wide")

st.title("🕌 AI Screener: ARB Hunter & Rebound (Khusus Saham ISSI)")
st.caption("Terhubung ke TradingView Screener • Dilengkapi Kalkulator Risk Management ATR & Analisa Sentimen AI")

# ================= SIDEBAR PENGATURAN FILTER =================
with st.sidebar:
    st.header("⚙️ Parameter Saringan")
    sesi_pilihan = st.radio("Mode Pemindaian:", ["SORE (Saham ARB Hari Ini)", "PAGI (Morning Rebound)"])
    mode_sesi = "SORE" if "SORE" in sesi_pilihan else "PAGI"
    
    min_trx = st.slider("Minimal Transaksi (Miliar Rp)", 1.0, 50.0, 5.0, step=1.0)
    min_vol = st.slider("Minimal Lonjakan Volume (x Rata-rata)", 1.0, 5.0, 1.5, step=0.1)
    max_rsi = st.slider("Maksimal RSI (14)", 15, 45, 32)
    hanya_uptrend = st.checkbox("Hanya Saham Uptrend (> EMA200)", value=False)
    
    st.divider()
    api_key_input = st.text_input("Gemini API Key (Opsional jika belum di Secrets)", type="password", value=os.environ.get("GEMINI_API_KEY", ""))
    tombol_scan = st.button("🔍 Mulai Pindai Pasar Sekarang", type="primary", use_container_width=True)

# ================= EKSEKUSI PEMINDAIAN =================
if tombol_scan:
    with st.spinner("Memindai ratusan saham ISSI dari TradingView & menghitung level ATR..."):
        df_hasil = jalankan_pemindaian(
            sesi=mode_sesi,
            min_transaksi_miliar=min_trx,
            min_vol_ratio=min_vol,
            max_rsi=max_rsi,
            hanya_uptrend=hanya_uptrend
        )
        st.session_state["hasil_scan"] = df_hasil
        st.session_state["mode_sesi"] = mode_sesi

# ================= TAMPILAN HASIL & CHART =================
if "hasil_scan" in st.session_state:
    df = st.session_state["hasil_scan"]
    
    if df.empty:
        st.warning("Belum ada saham ISSI yang memenuhi kriteria ketat saat ini. Coba longgarkan batas transaksi atau RSI di panel kiri.")
    else:
        st.success(f"Ditemukan **{len(df)} kandidat** saham ISSI yang lolos saringan ketat!")
        
        # Tabel Utama + Risk Management ATR
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
            
            # Widget Chart Resmi TradingView (Gratis)
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
