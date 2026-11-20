import os
import math
import urllib.parse
from datetime import datetime, timezone, timedelta
import feedparser
import requests
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
    atr = atr_14 if (pd.notna(atr_14) and atr_14 > 0) else (harga_entry * 0.03)
    jarak_sl = min(atr * 1.0, harga_entry * 0.035)
    sl = bulatkan_fraksi_bei(harga_entry - jarak_sl, "bawah")
    
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

# ================= 3. DETEKSI SESI & MUAT DAFTAR ISSI =================
def get_sesi_wib():
    wib = timezone(timedelta(hours=7))
    return "PAGI" if datetime.now(wib).hour < 12 else "SORE"

def muat_daftar_issi(custom_set=None):
    if custom_set and len(custom_set) > 0:
        return custom_set
    if os.path.exists("daftar_issi.csv"):
        df_issi = pd.read_csv("daftar_issi.csv")
        kode_set = set()
        for c in df_issi.columns:
            for val in df_issi[c].dropna():
                t = str(val).strip().upper().replace("IDX:", "")
                if len(t) == 4 and t.isalpha():
                    kode_set.add(t)
        if len(kode_set) > 0:
            return kode_set
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

# Fungsi berita yang sudah diamankan dengan requests + try/except
def ambil_berita_emiten(kode_saham):
    try:
        kode_bersih = "".join(c for c in kode_saham if c.isalnum())
        query = urllib.parse.quote(f"saham {kode_bersih} IDX")
        rss_url = f"https://google.com{query}&hl=id&gl=ID&ceid=ID:id"
        resp = requests.get(rss_url, timeout=5)
        feed = feedparser.parse(resp.content)
        berita = [f"- {e.title}" for e in feed.entries[:3] if hasattr(e, "title")]
        return "\n".join(berita) if berita else "- Tidak ada berita besar."
    except Exception:
        return "- Berita tidak dapat dimuat saat ini."

# ================= 4. MESIN PEMINDAI TRADINGVIEW =================
def jalankan_pemindaian(
    sesi="KOREKSI",
    min_transaksi_miliar=1.0,
    min_vol_ratio=0.9,
    max_rsi=45,
    hanya_uptrend=False,
    custom_issi_set=None
):
    daftar_issi = muat_daftar_issi(custom_issi_set)
    min_idr = min_transaksi_miliar * 1_000_000_000

    kolom = [
        'name', 'close', 'change', 'volume', 'average_volume_10d_calc',
        'Value.Traded', 'RSI', 'EMA200', 'BB.lower', 'MACD.macd', 'MACD.signal', 'ATR'
    ]

    _, df = (
        Query()
        .set_markets('indonesia')
        .select(*kolom)
        .where(
            col('close') >= 50,
            col('Value.Traded') >= min_idr
        )
        .order_by('change', ascending=True)
        .limit(1000)
        .get_scanner_data()
    )

    if df is None or df.empty:
        return pd.DataFrame()

    hasil = []
    for _, row in df.iterrows():
        kode = str(row['name']).strip().upper().replace("IDX:", "")
        if kode not in daftar_issi:
            continue

        change = row.get('change', 0)
        rsi = row.get('RSI', 50)
        vol = row.get('volume', 0)
        avg_vol = row.get('average_volume_10d_calc', 0)

        if sesi == "SORE":
            if pd.isna(change) or change > -15.0:
                continue
        elif sesi == "KOREKSI":
            if pd.isna(change) or change > -5.0:
                continue
        else:
            if pd.isna(change) or change < 0.5:
                continue

        if pd.notna(rsi) and rsi > max_rsi:
            continue

        if pd.notna(avg_vol) and avg_vol > 0 and vol < (avg_vol * min_vol_ratio):
            continue

        ema200 = row.get('EMA200')
        tren = "Uptrend" if (pd.notna(ema200) and row['close'] > ema200) else "Downtrend"
        if hanya_uptrend and tren != "Uptrend":
            continue

        rm = hitung_risk_management(row['close'], row.get('ATR'))
        bb_lower = row.get('BB.lower', 0)
        jarak_bb = round(((row['close'] - bb_lower) / bb_lower * 100), 2) if (pd.notna(bb_lower) and bb_lower > 0) else 0
        macd_val = row.get('MACD.macd', 0) if pd.notna(row.get('MACD.macd')) else 0
        macd_sig = row.get('MACD.signal', 0) if pd.notna(row.get('MACD.signal')) else 0
        macd_hist = round(macd_val - macd_sig, 2)

        hasil.append({
            "Kode": kode,
            "Harga": rm["Entry"],
            "Change (%)": round(change, 2),
            "Transaksi (M)": round(row['Value.Traded'] / 1e9, 2),
            "RSI": round(rsi, 1) if pd.notna(rsi) else 0,
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

    df_out = pd.DataFrame(hasil)
    if not df_out.empty:
        df_out = df_out.sort_values(by="Change (%)", ascending=(sesi != "PAGI"))
    return df_out

# ================= 5. ANALISIS AI (GEMINI) =================
def generate_analisa_ai(df_kandidat, sesi, api_key):
    if not api_key or df_kandidat.empty:
        return "API Key Gemini belum diatur atau kandidat kosong."

    try:
        client = genai.Client(api_key=api_key.strip())
        df_top = df_kandidat.head(8)
        ringkasan = ""
        for _, r in df_top.iterrows():
            ringkasan += (
                f"- {r['Kode']} | Entry: {r['Harga']} ({r['Change (%)']}%) | Transaksi: Rp{r['Transaksi (M)']}M | "
                f"RSI: {r['RSI']} | BB Lower: {r['Jarak BB (%)']}% | MACD Hist: {r['MACD Hist']} | Tren: {r['Tren']}\n"
                f"  Plan ATR -> SL: {r['Stop Loss']} (-{r['Risiko (%)']}%) | TP1: {r['TP 1']} (+{r['Profit 1 (%)']}%) | TP2: {r['TP 2']} (+{r['Profit 2 (%)']}%)\n"
                f"  Berita:\n{r['Berita']}\n\n"
            )

        prompt = f"""
        Kamu adalah analis kuantitatif saham syariah (ISSI) BEI spesialis strategi ARB Hunter & 2-Day Rebound.
        Mode Pemindaian: {sesi}. Data kandidat beserta level Risk Management berbasis ATR:

        {ringkasan}

        Tugasmu:
        1. Pilih maksimal 2 saham dengan probabilitas rebound terbaik.
        2. Validasi sentimen berita: pastikan bukan karena suspensi, PKPU, atau gagal bayar.
        3. Berikan eksekusi singkat mengacu pada angka Entry, SL, TP1, dan TP2 yang sudah dihitung di atas.
        Gunakan bahasa Indonesia yang padat dan langsung ke inti (maksimal 220 kata).
        """
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return resp.text
    except Exception as e:
        return f"Gagal memuat analisa AI: {e}"
