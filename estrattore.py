import os
import json
import subprocess
import sys

# Auto-installazione della trivella social
try:
    import yt_dlp
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"])
    import yt_dlp

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import io

def main():
    # 1. Autenticazione Sicura
    creds_json = json.loads(os.environ['GOOGLE_CREDENTIALS'])
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials = Credentials.from_service_account_info(creds_json, scopes=scopes)
    
    gc = gspread.authorize(credentials)
    drive_service = build('drive', 'v3', credentials=credentials)
    
    spreadsheet_id = "19m1cStsqyCvzz3-AYFJKPnrLPNaDuCXEKM8Fka76-Hc"
    target_folder_id = "1SpmiG8PJgvJDl2Ac5dptgPZqYi-xl3n2"
    
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
    except ValueError as e:
        print(f"❌ Errore: Colonne mancanti. Assicurati di avere Foto_Bot_1, Foto_Bot_2... scritte bene nella riga 1.")
        print(f"Colonne rilevate: {headers}")
        return

    print("📸 Bot Fotografo in modalità Social-Slayer attivo!")

    # 2. Scansione Righe
    for i in range(1, len(dati)):
        riga = dati[i]
        
        # 🔥 TRUCCO MAGICO: Se Google ha "tagliato" la riga perché le celle erano vuote, noi la allunghiamo!
        while len(riga) <= max(idx_link, idx_nome_video, idx_foto5):
            riga.append("")
            
        url_social = str(riga[idx_link]).strip()
        nome_video_atteso = str(riga[idx_nome_video]).strip()
        foto1_attuale = str(riga[idx_foto1]).strip()
        
        # Si attiva se c'è un link e manca la prima foto
        if url_social.startswith('http') and not foto1_attuale:
            print(f"\n🕵️‍♂️ Riga {i+1}: Rilevato link social: {url_social}")
            
            if not nome_video_atteso or not nome_video_atteso.endswith('.mp4'):
                nome_video_atteso = f"Video_Riga_{str(i+1).zfill(3)}.mp4"

            video_temporaneo = "video_social.mp4"
            if os.path.exists(video_temporaneo): os.remove(video_temporaneo)
            
            # --- FASE A: DOWNLOAD DA FACEBOOK ---
            print(f"📥 Estrazione del video dal social in corso...")
            ydl_opts = {
                'format': 'best',
                'outtmpl': video_temporaneo,
                'quiet': True,
                'no_warnings': True
            }
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url_social])
                print("🟩 Video scaricato con successo dal social!")
            except Exception as e:
                print(f"⚠️ Impossibile estrarre il video (potrebbe essere privato o rimosso). Errore: {e}")
                continue

            if not os.path.exists(video_temporaneo):
                print("❌ Errore: Video non generato sul server.")
                continue

            # --- FASE B: SALVATAGGIO IN DRIVE ---
            print(f"📤 Salvo il video su Drive come: {nome_video_atteso}")
            video_metadata = {
                'name': nome_video_atteso,
                'parents': [target_folder_id]
            }
            media_video = MediaFileUpload(video_temporaneo, mimeType='video/mp4')
            drive_service.files().create(body=video_metadata, media_body=media_video, fields='id').execute()

            # --- FASE C: SERVIZIO FOTOGRAFICO (5 FOTO) ---
            timestamps = ['00:00:02', '00:00:05', '00:00:08', '00:00:11', '00:00:14']
            formule_foto = []
            
            print("📸 Scatto 5 fotogrammi sequenziali...")
            for idx, ts in enumerate(timestamps):
                nome_foto_jpg = f"anteprima_{idx+1}.jpg"
                if os.path.exists(nome_foto_jpg): os.remove(nome_foto_jpg)
                
                subprocess.run([
                    'ffmpeg', '-ss', ts, '-i', video_temporaneo,
                    '-vframes', '1', '-q:v', '2', nome_foto_jpg
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if os.path.exists(nome_foto_jpg):
                    metadata_foto = {
                        'name': f'Copertina_{idx+1}_{nome_video_atteso.split(".")[0]}.jpg',
                        'parents': [target_folder_id]
                    }
                    media_foto = MediaFileUpload(nome_foto_jpg, mimeType='image/jpeg')
                    file_caricato = drive_service.files().create(body=metadata_foto, media_body=media_foto, fields='id').execute()
                    id_foto = file_caricato.get('id')
                    
                    drive_service.permissions().create(fileId=id_foto, body={'type': 'anyone', 'role': 'reader'}).execute()
                    
                    link_foto = f'https://docs.google.com/uc?export=download&id={id_foto}'
                    formule_foto.append(f'=IMAGE("{link_foto}")')
                    os.remove(nome_foto_jpg)
                else:
                    formule_foto.append("")

            # --- FASE D: SCRITTURA SUL FOGLIO ---
            indices_colonne = [idx_foto1, idx_foto2, idx_foto3, idx_foto4, idx_foto5]
            for pos, formula in enumerate(formule_foto):
                if formula:
                    sheet.update_cell(i + 1, indices_colonne[pos] + 1, formula)
            
            if not str(riga[idx_nome_video]).strip():
                sheet.update_cell(i + 1, idx_nome_video + 1, nome_video_atteso)

            print(f"✅ Riga {i+1} completata! Trasloco e book fotografico terminati.")
            
            if os.path.exists(video_temporaneo): os.remove(video_temporaneo)

if __name__ == '__main__':
    main()
