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
    
    # Coordinate fisse
    spreadsheet_id = "19m1cStsqyCvzz3-AYFJKPnrLPNaDuCXEKM8Fka76-Hc"
    target_folder_id = "1SpmiG8PJgvJDl2Ac5dptgPZqYi-xl3n2"
    
    sheet = gc.open_by_key(spreadsheet_id).worksheet('Foglio1')
    dati = sheet.get_all_values()
    
    if len(dati) <= 1:
        print("Database vuoto.")
        return

    # 🎯 FIX DEFINITIVO: Usiamo indici numerici fissi
    # Colonna J è l'indice 9 (partendo da 0) -> Copertina
    # Colonna L è l'indice 11 (partendo da 0) -> Nome_File_Video
    idx_copertina = 9
    idx_nome_video = 11

    # 2. Scansione delle Righe
    for i in range(1, len(dati)):
        riga = dati[i]
        
        # Evita errori se la riga è troppo corta
        if len(riga) <= idx_nome_video:
            continue
            
        copertina_attuale = str(riga[idx_copertina]).strip() if len(riga) > idx_copertina else ""
        nome_video = str(riga[idx_nome_video]).strip()
        
        if not copertina_attuale and nome_video and nome_video.endswith('.mp4'):
            print(f"🕵️‍♂️ Riga {i+1}: Avvio procedura per {nome_video}")
            
            # Controlla se il video è già nella cartella centralizzata
            check_query = f"'{target_folder_id}' in parents and name='{nome_video}' and mimeType='video/mp4' and trashed=false"
            check_results = drive_service.files().list(q=check_query, fields="files(id)").execute()
            check_files = check_results.get('files', [])
            
            video_id = None
            
            if check_files:
                print(f"✨ Il video {nome_video} è già nella cartella centralizzata.")
                video_id = check_files[0]['id']
            else:
                print(f"🔍 Cerco il file originale {nome_video} nel Drive...")
                search_query = f"name='{nome_video}' and mimeType='video/mp4' and trashed=false"
                search_results = drive_service.files().list(q=search_query, fields="files(id, name)").execute()
                search_files = search_results.get('files', [])
                
                if not search_files:
                    print(f"⚠️ Impossibile trovare {nome_video} su tutto il Drive.")
                    continue
                
                sorgente_id = search_files[0]['id']
                print(f"📥 Scarico e sposto il video...")
                
                request = drive_service.files().get_media(fileId=sorgente_id)
                fh = io.FileIO('video_temporaneo.mp4', 'wb')
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                fh.close()
                
                print(f"📤 Salvo la copia centralizzata...")
                video_metadata = {
                    'name': nome_video,
                    'parents': [target_folder_id]
                }
                media_video = MediaFileUpload('video_temporaneo.mp4', mimeType='video/mp4')
                nuovo_video = drive_service.files().create(body=video_metadata, media_body=media_video, fields='id').execute()
                video_id = nuovo_video.get('id')
            
            if not os.path.exists('video_temporaneo.mp4') and video_id:
                request = drive_service.files().get_media(fileId=video_id)
                fh = io.FileIO('video_temporaneo.mp4', 'wb')
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                fh.close()

            print("📸 Scatto la fotografia al secondo 3...")
            output_image = 'anteprima.jpg'
            if os.path.exists(output_image): os.remove(output_image)
            
            subprocess.run([
                'ffmpeg', '-ss', '00:00:03', '-i', 'video_temporaneo.mp4',
                '-vframes', '1', '-q:v', '2', output_image
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if not os.path.exists(output_image):
                print("❌ Errore FFmpeg durante lo scatto.")
                continue
                
            print("📤 Carico la copertina su Drive...")
            file_metadata = {
                'name': f'Copertina_{nome_video.split(".")[0]}.jpg',
                'parents': [target_folder_id]
            }
            media_foto = MediaFileUpload(output_image, mimeType='image/jpeg')
            foto_caricata = drive_service.files().create(body=file_metadata, media_body=media_foto, fields='id').execute()
            foto_id = foto_caricata.get('id')
            
            permission = {'type': 'anyone', 'role': 'reader'}
            drive_service.permissions().create(fileId=foto_id, body=permission).execute()
            
            link_diretto_foto = f'https://docs.google.com/uc?export=download&id={foto_id}'
            formula_immagine = f'=IMAGE("{link_diretto_foto}")'
            
            # Scrittura forzata nella colonna J (indice 10 su gspread)
            sheet.update_cell(i + 1, 10, formula_immagine)
            print(f"✅ Riga {i+1} completata con successo.")
            
            if os.path.exists('video_temporaneo.mp4'): os.remove('video_temporaneo.mp4')
            if os.path.exists('anteprima.jpg'): os.remove('anteprima.jpg')

if __name__ == '__main__':
    main()
