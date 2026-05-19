import os
import json
import subprocess
import sys
import requests

# Auto-installazione della trivella social
try:
    import yt_dlp
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"])
    import yt_dlp

import gspread
from google.oauth2.service_account import Credentials

def upload_image_to_cloud(file_path):
    """Carica l'immagine su un cloud per sviluppatori esterno, aggirando il blocco di Google Drive"""
    url = "https://catbox.moe/user/api.php"
    data = {"reqtype": "fileupload"}
    try:
        with open(file_path, "rb") as f:
            files = {"fileToUpload": f}
            response = requests.post(url, data=data, files=files)
        if response.status_code == 200:
            return response.text.strip() # Restituisce il link diretto all'immagine (es. https://files.catbox.moe/xyz.jpg)
    except Exception as e:
        print(f"Errore caricamento cloud esterno: {e}")
    return None

def main():
    # 1. Autenticazione (solo per leggere/scrivere il Foglio, niente Drive!)
    creds_json = json.loads(os.environ['GOOGLE_CREDENTIALS'])
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    credentials = Credentials.from_service_account_info(creds_json, scopes=scopes)
    
    gc = gspread.authorize(credentials)
    
    spreadsheet_id = "19m1cStsqyCvzz3-AYFJKPnrLPNaDuCXEKM8Fka76-Hc"
    
    sheet = gc.open_by_key(spreadsheet_id).worksheet('Foglio1')
    dati = sheet.get_all_values()
    
    if len(dati) <= 1:
        print("Database vuoto.")
        return

    # Mappatura Colonne
    headers = [h.strip().lower() for h in dati[0]]
    
    try:
        idx_link = headers.index('link')
        idx_nome_video = headers.index('nome_file_video')
        idx_foto1 = headers.index('foto_bot_1')
        idx_foto2 = headers.index('foto_bot_2')
        idx_foto3 = headers.index('foto_bot_3')
        idx_foto4 = headers.index('foto_bot_4')
        idx_foto5 = headers.index('foto_bot_5')
    except ValueError:
        print("❌ Errore: Colonne mancanti. Assicurati di avere Foto_Bot_1... scritte bene nella riga 1.")
        return

    print("📸 Bot Fotografo - Versione 'Cloud Esterno' Anti-Blocco attivo!")

    # 2. Scansione Righe
    for i in range(1, len(dati)):
        riga = dati[i]
        
        while len(riga) <= max(idx_link, idx_nome_video, idx_foto5):
            riga.append("")
            
        url_social = str(riga[idx_link]).strip()
        nome_video_atteso = str(riga[idx_nome_video]).strip()
        foto1_attuale = str(riga[idx_foto1]).strip()
        
        if url_social.startswith('http') and not foto1_attuale:
            print(f"\n🕵️‍♂️ Riga {i+1}: Rilevato link social: {url_social}")
            
            video_temporaneo = "video_social.mp4"
            if os.path.exists(video_temporaneo): os.remove(video_temporaneo)
            
            print("📥 Estrazione del video in corso...")
            ydl_opts = {
                'format': 'best',
                'outtmpl': video_temporaneo,
                'quiet': True,
                'no_warnings': True
            }
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url_social])
                print("🟩 Video scaricato in memoria locale!")
            except Exception as e:
                print(f"⚠️ Impossibile estrarre il video. Errore: {e}")
                continue

            if not os.path.exists(video_temporaneo):
                print("❌ Errore: Video non generato sul server.")
                continue

            # --- SERVIZIO FOTOGRAFICO (5 FOTO) ---
            timestamps = ['00:00:02', '00:00:05', '00:00:08', '00:00:11', '00:00:14']
            formule_foto = []
            
            print("📸 Scatto le 5 foto e le carico sul cloud indipendente...")
            for idx, ts in enumerate(timestamps):
                nome_foto_jpg = f"anteprima_{idx+1}.jpg"
                if os.path.exists(nome_foto_jpg): os.remove(nome_foto_jpg)
                
                subprocess.run([
                    'ffmpeg', '-ss', ts, '-i', video_temporaneo,
                    '-vframes', '1', '-q:v', '2', nome_foto_jpg
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if os.path.exists(nome_foto_jpg):
                    # Invia la foto al cloud per sviluppatori e ottiene il link
                    link_foto = upload_image_to_cloud(nome_foto_jpg)
                    
                    if link_foto:
                        if idx == 0 and url_social:
                            formule_foto.append(f'=HYPERLINK("{url_social}"; IMAGE("{link_foto}"))')
                        else:
                            formule_foto.append(f'=IMAGE("{link_foto}")')
                    else:
                        formule_foto.append("")
                        
                    os.remove(nome_foto_jpg)
                else:
                    formule_foto.append("")

            # --- SCRITTURA SUL FOGLIO ---
            indices_colonne = [idx_foto1, idx_foto2, idx_foto3, idx_foto4, idx_foto5]
            for pos, formula in enumerate(formule_foto):
                if formula:
                    sheet.update_cell(i + 1, indices_colonne[pos] + 1, formula)
            
            # Se la colonna del nome video era vuota, le diamo un nome standard
            if not nome_video_atteso:
                sheet.update_cell(i + 1, idx_nome_video + 1, f"Video_Riga_{str(i+1).zfill(3)}.mp4")

            print(f"✅ Riga {i+1} completata! Book fotografico terminato.")
            
            if os.path.exists(video_temporaneo): os.remove(video_temporaneo)

if __name__ == '__main__':
    main()
