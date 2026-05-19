import os
import json
import subprocess
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import io

def main():
    # 1. Autenticazione Sicura con i Server Google
    creds_json = json.loads(os.environ['GOOGLE_CREDENTIALS'])
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials = Credentials.from_service_account_info(creds_json, scopes=scopes)
    
    gc = gspread.authorize(credentials)
    drive_service = build('drive', 'v3', credentials=credentials)
    
    # coordinate blindate: Foglio Sorgente e Cartella Drive Centralizzata
    spreadsheet_id = "19m1cStsqyCvzz3-AYFJKPnrLPNaDuCXEKM8Fka76-Hc"
    target_folder_id = "1SpmiG8PJgvJDl2Ac5dptgPZqYi-xl3n2"
    
    sheet = gc.open_by_key(spreadsheet_id).worksheet('Foglio1')
    
    dati = sheet.get_all_values()
    if len(dati) <= 1:
        print("Database vuoto.")
        return

    # Mappatura Colonne: Cerca esattamente le tue intestazioni!
    headers = [h.strip().lower() for h in dati[0]]
    try:
        idx_copertina = headers.index('copertina_bot') # 👈 ORA CERCA LA TUA COLONNA ESATTA
        idx_nome_video = headers.index('nome_file_video')
    except ValueError:
        print("Errore: Colonna 'Copertina_Bot' o 'Nome_File_Video' non trovata nella prima riga del foglio.")
        print(f"Colonne trovate: {headers}")
        return

    # 2. Scansione delle Righe del Foglio
    for i in range(1, len(dati)):
        riga = dati[i]
        copertina_attuale = riga[idx_copertina].strip() if idx_copertina < len(riga) else ""
        nome_video = riga[idx_nome_video].strip() if idx_nome_video < len(riga) else ""
        
        # Il bot si attiva se c'è il nome del file video ma manca la formula dell'immagine
        if not copertina_attuale and nome_video and nome_video.endswith('.mp4'):
            print(f"🕵️‍♂️ Riga {i+1}: Cerco '{nome_video}' nella cartella centralizzata...")
            
            # Cerca il file ESCLUSIVAMENTE nella cartella Drive indicata
            query = f"'{target_folder_id}' in parents and name='{nome_video}' and mimeType='video/mp4' and trashed=false"
            results = drive_service.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])
            
            if not files:
                print(f"⚠️ File {nome_video} non trovato nella cartella specificata.")
                continue
                
            video_id = files[0]['id']
            print(f"🎥 File trovato! Avvio il download temporaneo di: {nome_video}")
            
            # Download del video nel server di GitHub
            request = drive_service.files().get_media(fileId=video_id)
            fh = io.FileIO('video_temporaneo.mp4', 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.close()
            
            # 3. Estrazione del fotogramma al secondo 3
            print("📸 Scatto la fotografia con FFmpeg...")
            output_image = 'anteprima.jpg'
            if os.path.exists(output_image): os.remove(output_image)
            
            subprocess.run([
                'ffmpeg', '-ss', '00:00:03', '-i', 'video_temporaneo.mp4',
                '-vframes', '1', '-q:v', '2', output_image
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if not os.path.exists(output_image):
                print("❌ Errore durante la generazione dello screenshot.")
                continue
                
            # 4. Upload della copertina nella stessa cartella dei video
            print("📤 Carico lo screenshot nella cartella Drive...")
            file_metadata = {
                'name': f'Copertina_{nome_video.split(".")[0]}.jpg',
                'parents': [target_folder_id]
            }

            media = MediaFileUpload(output_image, mimeType='image/jpeg')
            foto_caricata = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            foto_id = foto_caricata.get('id')
            
            # Rende il file visibile pubblicamente via URL per la WebApp
            permission = {'type': 'anyone', 'role': 'reader'}
            drive_service.permissions().create(fileId=foto_id, body=permission).execute()
            
            # 5. Scrittura della formula IMAGE sul foglio
            link_diretto_foto = f'https://docs.google.com/uc?export=download&id={foto_id}'
            formula_immagine = f'=IMAGE("{link_diretto_foto}")'
            
            sheet.update_cell(i + 1, idx_copertina + 1, formula_immagine)
            print(f"✅ Riga {i+1} aggiornata sul database con la nuova anteprima!")
            
            # Pulizia file temporanei
            if os.path.exists('video_temporaneo.mp4'): os.remove('video_temporaneo.mp4')
            if os.path.exists('anteprima.jpg'): os.remove('anteprima.jpg')

if __name__ == '__main__':
    main()
