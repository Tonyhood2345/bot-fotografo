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
    
    # ID del foglio sorgente e della cartella di destinazione finale
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
        idx_copertina = headers.index('copertina_bot')
        idx_nome_video = headers.index('nome_file_video')
    except ValueError:
        print("Errore: Colonna 'Copertina_Bot' o 'Nome_File_Video' non trovata.")
        return

    # 2. Scansione delle Righe
    for i in range(1, len(dati)):
        riga = dati[i]
        copertina_attuale = riga[idx_copertina].strip() if idx_copertina < len(riga) else ""
        nome_video = riga[idx_nome_video].strip() if idx_nome_video < len(riga) else ""
        
        if not copertina_attuale and nome_video and nome_video.endswith('.mp4'):
            print(f"🕵️‍♂️ Riga {i+1}: Avvio procedura per {nome_video}")
            
            # Controlla se il video è già presente nella cartella centralizzata
            check_query = f"'{target_folder_id}' in parents and name='{nome_video}' and mimeType='video/mp4' and trashed=false"
            check_results = drive_service.files().list(q=check_query, fields="files(id)").execute()
            check_files = check_results.get('files', [])
            
            video_id = None
            
            if check_files:
                print(f"✨ Il video {nome_video} è già nella cartella centralizzata.")
                video_id = check_files[0]['id']
            else:
                # Se non è nella cartella centralizzata, lo cerca ovunque su Drive
                print(f"🔍 Cerco il file originale {nome_video} nel Drive...")
                search_query = f"name='{nome_video}' and mimeType='video/mp4' and trashed=false"
                search_results = drive_service.files().list(q=search_query, fields="files(id, name)").execute()
                search_files = search_results.get('files', [])
                
                if not search_files:
                    print(f"⚠️ Impossibile trovare il file sorgente {nome_video} su tutto il Drive.")
                    continue
                
                sorgente_id = search_files[0]['id']
                print(f"📥 Scarico il video originale...")
                
                # Download temporaneo su GitHub
                request = drive_service.files().get_media(fileId=sorgente_id)
                fh = io.FileIO('video_temporaneo.mp4', 'wb')
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                fh.close()
                
                # Copia il video nella cartella centralizzata
                print(f"📤 Salvo una copia del video nella cartella centralizzata...")
                video_metadata = {
                    'name': nome_video,
                    'parents': [target_folder_id]
                }
                media_video = MediaFileUpload('video_temporaneo.mp4', mimeType='video/mp4')
                nuovo_video = drive_service.files().create(body=video_metadata, media_body=media_video, fields='id').execute()
                video_id = nuevo_video.get('id')
            
            # Se il video temporaneo non è stato scaricato nello step precedente, lo scarica ora per la foto
            if not os.path.exists('video_temporaneo.mp4') and video_id:
                request = drive_service.files().get_media(fileId=video_id)
                fh = io.FileIO('video_temporaneo.mp4', 'wb')
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                fh.close()

            # 3. Estrazione fotogramma
            print("📸 Scatto la fotografia di copertina...")
            output_image = 'anteprima.jpg'
            if os.path.exists(output_image): os.remove(output_image)
            
            subprocess.run([
                'ffmpeg', '-ss', '00:00:03', '-i', 'video_temporaneo.mp4',
                '-vframes', '1', '-q:v', '2', output_image
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if not os.path.exists(output_image):
                print("❌ Errore durante lo scatto.")
                continue
                
            # 4. Upload della copertina nella cartella centralizzata
            print("📤 Carico la copertina nella cartella...")
            file_metadata = {
                'name': f'Copertina_{nome_video.split(".")[0]}.jpg',
                'parents': [target_folder_id]
            }
            media_foto = MediaFileUpload(output_image, mimeType='image/jpeg')
            foto_caricata = drive_service.files().create(body=file_metadata, media_body=media_foto, fields='id').execute()
            foto_id = foto_caricata.get('id')
            
            permission = {'type': 'anyone', 'role': 'reader'}
            drive_service.permissions().create(fileId=foto_id, body=permission).execute()
            
            # 5. Scrittura sul foglio
            link_diretto_foto = f'https://docs.google.com/uc?export=download&id={foto_id}'
            formula_immagine = f'=IMAGE("{link_diretto_foto}")'
            
            sheet.update_cell(i + 1, idx_copertina + 1, formula_immagine)
            print(f"✅ Riga {i+1} completata! Video e foto salvati nella cartella.")
            
            if os.path.exists('video_temporaneo.mp4'): os.remove('video_temporaneo.mp4')
            if os.path.exists('anteprima.jpg'): os.remove('anteprima.jpg')

if __name__ == '__main__':
    main()
