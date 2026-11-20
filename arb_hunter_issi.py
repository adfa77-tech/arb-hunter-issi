import os
import requests
from screener_core import get_sesi_wib, jalankan_pemindaian, generate_analisa_ai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def kirim_telegram(pesan):
    url = f"https://telegram.org{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": pesan,
        "parse_mode": "Markdown"
    })

if __name__ == "__main__":
    sesi = get_sesi_wib()
    df = jalankan_pemindaian(sesi=sesi)

    if df.empty:
        print(f"Tidak ada saham ISSI lolos saringan pada sesi {sesi}.")
    else:
        analisa = generate_analisa_ai(df, sesi, GEMINI_API_KEY)
        
        # Susun rincian trading plan berbasis ATR untuk setiap kandidat
        rincian_rm = ""
        for _, r in df.iterrows():
            rincian_rm += (
                f"📌 *{r['Kode']}* ({r['Change (%)']}% | Transaksi: Rp{r['Transaksi (M)']}M)\n"
                f"   • Entry: `{r['Harga']}` | SL: `{r['Stop Loss']}` (-{r['Risiko (%)']}%)\n"
                f"   • TP1: `{r['TP 1']}` (+{r['Profit 1 (%)']}%) | TP2: `{r['TP 2']}` (+{r['Profit 2 (%)']}%) | R:R `{r['R:R']}`\n\n"
            )

        judul = "🌅 *MORNING BOUNCE ISSI (09.15 WIB)*" if sesi == "PAGI" else "🌆 *ARB HUNTER SORE ISSI (15.30 WIB)*"
        pesan = f"{judul}\n\n{rincian_rm}*Analisa AI & Berita:*\n{analisa}"
        
        kirim_telegram(pesan)
        print("Alert dan Risk Management berhasil dikirim ke Telegram!")