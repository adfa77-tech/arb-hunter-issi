import os
import math
import urllib.parse
from datetime import datetime, timezone, timedelta
import feedparser
import pandas as pd
from tradingview_screener import Query, col
from google import genai

# ================= 1. PEMBULATAN FRAKSI HARGA BEI =================
def bulatkan_fraksi_bei(harga, arah="terdekat"):
    if harga < 200:
        fraksi = 1
    elif harga < 500:
        fraksi = 2
    elif harga < 2000:
        fraksi = 5
    elif harga < 5000:
        fraksi = 10
    else:
        fraksi = 25

    if arah == "atas":
        return int(math.ceil(harga / fraksi) * fraksi)
    elif arah == "bawah":
        return int(math.floor(harga / fraksi) * fraksi)
    return int(round(harga / fraksi) * fraksi)

# ================= 2. KALKULATOR RISK MANAGEMENT (ATR) =================
def hitung_risk_management(harga_entry, atr_14):
    # Jika ATR tidak terbaca, gunakan estimasi 3% dari harga
    atr = atr_14 if (pd.notna(atr_14) and atr_14 > 0) else (harga_entry * 0.03)
    
    # Batasi risiko Stop Loss maksimal 3.5% dari harga entry
    jarak_sl = min(atr * 1.0, harga_entry * 0.035)
    sl = bulatkan_fraksi_bei(harga_entry - jarak_sl, "bawah")
    
    # Pastikan SL minimal 1 fraksi di bawah entry
    if sl >= harga_entry:
        sl = bulatkan_fraksi_bei(harga_entry * 0.98, "bawah")

    tp1 = bulatkan_fraksi_bei(harga_entry + (atr * 1.2), "atas")
    tp2 = bulatkan_fraksi_bei(harga_entry + (atr * 2.0), "atas")

    risiko_persen = round(((harga_entry - sl) / harga_entry) * 100, 2)
    reward1_persen = round(((tp1 - harga_entry) / harga_entry) * 100, 2)
    reward2_persen = round(((tp2 - harga_entry) / harga_entry) * 100, 2)
    rr_ratio = round(reward2_persen / risiko_persen, 2) if risiko_persen > 0 else 0

    return {
        "Entry": int(harga_entry),
        "Stop Loss": sl,
        "Risiko (%)": risiko_persen,
        "TP 1": tp1,
        "Profit 1 (%)": reward1_persen,
        "TP 2": tp2,
        "Profit 2 (%)": reward2_persen,
        "R:R Ratio": f"1 : {rr_ratio}"
    }

# ================= 3. DETEKSI SESI & VALIDASI ARB =================
def get_sesi_wib():
    wib = timezone(timedelta(hours=7))
    return "PAGI" if datetime.now(wib).hour < 12 else "SORE"

def muat_daftar_issi():
    if os.path.exists("daftar_issi.csv"):
        df_issi = pd.read_csv("daftar_issi.csv")
        return set(df_issi["Kode"].dropna().str.strip().str.upper())
    return {
        "ADRO", "AKRA", "AMMN", "ANTM", "ASII", "AUTO", "AVIA", "BRIS", "BRMS",
        "BRPT", "BSDE", "BTPS", "CPIN", "CTRA", "DEWA", "DOID", "DSNG", "ELSA",
        "EMTK", "ENRG", "ERAA", "EXCL", "FILM", "GOTO", "HEAL", "HRUM", "ICBP",
        "INCO", "INDF", "INDY", "INKP", "INTP", "ISAT", "ITMG", "JPFA", "JSMR",
        "KLBF", "KPIG", "LSIP", "MAPI", "MBMA", "MDKA", "MEDC", "MIKA", "MNCN",
        "MTEL", "MYOR", "NCKL", "PGAS", "PGEO", "PTBA", "PTPP", "PWON", "RAJA",
        "SCMA", "SIDO", "SILO", "SMGR", "SMRA", "SSIA", "TAPG", "TINS", "TKIM",
        "TLKM", "TOWR", "TPIA", "UNTR", "UNVR", "WIFI", "WIKA"
    }

def is_valid_arb(harga, change):
    if 50 <= harga <= 200 and change <= -33.5:
        return True
    elif 200 < harga <= 5000 and change <= -23.5:
        return True
    elif harga > 5000 and change <= -18.5:
        return True
    return False

def ambil_berita_emiten(kode_saham):
    query = urllib.parse.quote(f"saham {kode_saham} IDX")
    rss_url = f"https://google.com{query}&hl=id&gl=ID&ceid=ID:id"
    feed = feedparser.parse(rss_url)
    berita = [f"- {e.title}" for e in feed.entries[:3]]
    return "\n".join(berita) if berita else "- Tidak ada berita besar."

# ================= 4. MESIN PEMINDAI TRADINGVIEW =================
def jalankan_pemindaian(sesi="SORE", min_transaksi_miliar=5.0, min_vol_ratio=1.5, max_rsi=32, hanya_uptrend=False):
    daftar_issi = muat_daftar_issi()
    min_idr = min_transaksi_miliar * 1_000_000_000

    kolom = [
        'name', 'close', 'high', 'change', 'volume', 'average_volume_10d_calc',
        'Value.Traded', 'RSI', 'EMA200', 'BB.lower', 'MACD.macd', 'MACD.signal', 'ATR'
    ]

    if sesi == "SORE":
        kondisi = [
            col('close') >= 50,
            col('change') <= -18.5,
            col('Value.Traded') >= min_idr,
            col('volume') > col('average_volume_10d_calc') * min_vol_ratio,
            col('RSI') < max_rsi,
            col('close') <= col('BB.lower') * 1.01
        ]
    else:
        kondisi = [
            col('close') >= 50,
            col('change') >= 1.0,
            col('Value.Traded') >= (min_idr * 0.2), # 20% target harian di 15 menit awal pembukaan
            col('RSI') < max_rsi,
            col('close') <= col('BB.lower') * 1.05
        ]

    _, df = (
        Query()
        .set_markets('indonesia')
        .select(*kolom)
        .where(*kondisi)
        .order_by('Value.Traded', ascending=False)
        .limit(100)
        .get_scanner_data()
    )

    hasil = []
    for _, row in df.iterrows():
        kode = row['name'].strip().upper()
        if kode not in daftar_issi:
            continue
        if sesi == "SORE" and not is_valid_arb(row['close'], row['change']):
            continue

        ema200 = row.get('EMA200')
        tren = "Uptrend" if (pd.notna(ema200) and row['close'] > ema200) else "Downtrend"
        if hanya_uptrend and tren != "Uptrend":
            continue

        rm = hitung_risk_management(row['close'], row.get('ATR'))
        bb_lower = row.get('BB.lower', 0)
        jarak_bb = round(((row['close'] - bb_lower) / bb_lower * 100), 2) if bb_lower else 0
        macd_hist = round(row.get('MACD.macd', 0) - row.get('MACD.signal', 0), 2)

        hasil.append({
            "Kode": kode,
            "Harga": rm["Entry"],
            "Change (%)": round(row['change'], 2),
            "Transaksi (M)": round(row['Value.Traded'] / 1e9, 2),
            "RSI": round(row['RSI'], 1),
            "Jarak BB (%)": jarak_bb,
            "MACD Hist": macd_hist,
            "Tren": tren,
            "Stop Loss": rm["Stop Loss"],
            "Risiko (%)": rm["Risiko (%)"],
            "TP 1": rm["TP 1"],
            "Profit 1 (%)": rm["Profit 1 (%)"],
            "TP 2": rm["TP 2"],
            "Profit 2 (%)": rm["Profit 2 (%)"],
            "R:R": rm["R:R Ratio"],
            "Berita": ambil_berita_emiten(kode)
        })

    return pd.DataFrame(hasil)

# ================= 5. ANALISIS AI (GEMINI) =================
def generate_analisa_ai(df_kandidat, sesi, api_key):
    if not api_key or df_kandidat.empty:
        return "API Key Gemini belum diatur atau kandidat kosong."

    client = genai.Client(api_key=api_key)
    ringkasan = ""
    for _, r in df_kandidat.iterrows():
        ringkasan += (
            f"- {r['Kode']} | Entry: {r['Harga']} ({r['Change (%)']}%) | Transaksi: Rp{r['Transaksi (M)']}M | "
            f"RSI: {r['RSI']} | BB Lower: {r['Jarak BB (%)']}% | MACD Hist: {r['MACD Hist']} | Tren: {r['Tren']}\n"
            f"  Plan ATR -> SL: {r['Stop Loss']} (-{r['Risiko (%)']}%) | TP1: {r['TP 1']} (+{r['Profit 1 (%)']}%) | TP2: {r['TP 2']} (+{r['Profit 2 (%)']}%)\n"
            f"  Berita:\n{r['Berita']}\n\n"
        )

    prompt = f"""
    Kamu adalah analis kuantitatif saham syariah (ISSI) BEI spesialis strategi ARB Hunter & 2-Day Rebound.
    Sesi: {sesi}. Data kandidat beserta level Risk Management berbasis ATR:

    {ringkasan}

    Tugasmu:
    1. Pilih maksimal 2 saham dengan probabilitas rebound terbaik.
    2. Validasi sentimen berita: pastikan bukan karena suspensi, PKPU, atau gagal bayar.
    3. Berikan eksekusi singkat mengacu pada angka Entry, SL, TP1, dan TP2 yang sudah dihitung di atas.
    Gunakan bahasa Indonesia yang padat dan langsung ke inti (maksimal 220 kata).
    """
    resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return resp.text
