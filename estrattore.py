import os
import json
import subprocess
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
    
    # ID del foglio
    spreadsheet_id = "1s68pw0WEUcV0ZqltiahAqCp_r5rsycSjxKNh0VZQq_g"
    sheet = gc.open_by_key(spreadsheet_id).worksheet('DATABASE_IMMOBILI')
    
    dati = sheet.get_all_values()
    if len(dati) <= 1:
        print("Database vuoto.")
        return

    # Mappatura Colonne
    headers = [h.strip().lower() for h in dati[0]]
    try:
        # Cerca la nuova colonna Copertina_Bot e il Nome File
        idx_copertina = headers.index('copertina_bot')
        idx_nome_video = headers.index('nome_file_video')
    except ValueError:
        print("Errore: Colonna 'Copertina_Bot' o 'Nome_File_Video' non trovata nel foglio.")
        return

    # 2. Scansione Righe
    for i in range(1, len(dati)):
        riga = dati[i]
        copertina_attuale = riga[idx_copertina].strip() if idx_copertina < len(riga) else ""
        nome_video = riga[idx_nome_video].strip() if idx_nome_video < len(riga) else ""
        
        # Se c'è un file MP4 ma manca la copertina, il bot si attiva!
        if not copertina_attuale and nome_video and nome_video.endswith('.mp4'):
            print(f"🕵️‍♂️ Trovato immobile senza copertina. Cerco in Drive il file: {nome_video}")
            
            # Radar: Cerca il file in tutto il tuo Google Drive!
            query = f"name='{nome_video}' and mimeType='video/mp4' and trashed=false"
            results = drive_service.files().list(q=query, fields="files(id, name, parents)").execute()
            files = results.get('files', [])
            
            if not files:
                print(f"⚠️ File {nome_video} non trovato in Drive.")
                continue
                
            video_id = files[0]['id']
            # Trova la cartella in cui si trova il video per salvare lì anche la foto
            folder_id = files[0].get('parents', [''])[0]
            print(f"🎥 Trovato! Scarico il video temporaneamente...")
            
            request = drive_service.files().get_media(fileId=video_id)
            fh = io.FileIO('video_temporaneo.mp4', 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.close()
            
            # 3. Estrazione fotogramma
            print("📸 Scatto la fotografia al secondo 3...")
            output_image = 'anteprima.jpg'
            if os.path.exists(output_image): os.remove(output_image)
            
            subprocess.run([
                'ffmpeg', '-ss', '00:00:03', '-i', 'video_temporaneo.mp4',
                '-vframes', '1', '-q:v', '2', output_image
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if not os.path.exists(output_image):
                print("❌ Errore durante lo scatto.")
                continue
                
            # 4. Upload della foto su Google Drive
            print("📤 Carico lo screenshot...")
            file_metadata = {
                'name': f'Copertina_{nome_video.split(".")[0]}.jpg',
            }
            if folder_id:
                file_metadata['parents'] = [folder_id]

            media = MediaFileUpload(output_image, mimeType='image/jpeg')
            foto_caricata = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            foto_id = foto_caricata.get('id')
            
            permission = {'type': 'anyone', 'role': 'reader'}
            drive_service.permissions().create(fileId=foto_id, body=permission).execute()
            
            # 5. Scrittura nella nuova colonna Z
            link_diretto_foto = f'https://docs.google.com/uc?export=download&id={foto_id}'
            formula_immagine = f'=IMAGE("{link_diretto_foto}")'
            
            sheet.update_cell(i + 1, idx_copertina + 1, formula_immagine)
            print(f"✅ Riga {i+1} completata e aggiornata!")
            
            if os.path.exists('video_temporaneo.mp4'): os.remove('video_temporaneo.mp4')
            if os.path.exists('anteprima.jpg'): os.remove('anteprima.jpg')

if __name__ == '__main__':
    main()
