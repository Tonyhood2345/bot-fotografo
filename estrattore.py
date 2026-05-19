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
    
    # Configurazione rigida per Foglio Sorgente e Cartella Destinazione
    spreadsheet_id = "19m1cStsqyCvzz3-AYFJKPnrLPNaDuCXEKM8Fka76-Hc"
    target_folder_id = "1SpmiG8PJgvJDl2Ac5dptgPZqYi-xl3n2"
    
    sheet = gc.open_by_key(spreadsheet_id).worksheet('Foglio1')
    dati = sheet.get_all_values()
    
    if len(dati) <= 1:
        print("Database vuoto.")
        return

    # Mappatura rigida sulle colonne native del sistema attuale
    # Colonna J (Indice 9) -> Link (Ospiterà l'immagine cliccabile)
    # Colonna K (Indice 10) -> Nome_File_Video
    idx_link = 9
    idx_nome_video = 10

    print("🤖 Bot Fotografo integrato nel sistema esistente. Analizzo i video...")

    # 2. Scansione delle Righe del Foglio
    for i in range(1, len(dati)):
        riga = dati[i]
        
        if len(riga) <= idx_nome_video:
            continue
            
        contenuto_link = str(riga[idx_link]).strip()
        nome_video = str(riga[idx_nome_video]).strip()
        
        # Il bot si attiva SOLO se c'è il nome del file video .mp4
        # E se la colonna Link contiene ancora un link normale (non è già stata convertita in formula IMAGE)
        if nome_video and nome_video.endswith('.mp4') and not contenuto_link.startswith('='):
            print(f"🕵️‍♂️ Riga {i+1}: Trovato video '{nome_video}'.")
            
            # Salva il link originale (Facebook/Instagram) per renderlo cliccabile dopo
            link_originale = contenuto_link if contenuto_link.startswith('http') else ""
            
            # Cerca il file nella cartella centralizzata
            check_query = f"'{target_folder_id}' in parents and name='{nome_video}' and mimeType='video/mp4' and trashed=false"
            check_results = drive_service.files().list(q=check_query, fields="files(id)").execute()
            check_files = check_results.get('files', [])
            
            video_id = None
            
            if check_files:
                print(f"✨ Il video {nome_video} è già nella cartella centralizzata.")
                video_id = check_files[0]['id']
            else:
                # Se non c'è, scansione totale del Drive per recuperarlo
                print(f"🔍 File non centralizzato. Lo cerco in tutto il Google Drive...")
                search_query = f"name='{nome_video}' and mimeType='video/mp4' and trashed=false"
                search_results = drive_service.files().list(q=search_query, fields="files(id)").execute()
                search_files = search_results.get('files', [])
                
                if not search_files:
                    print(f"⚠️ Impossibile trovare il file sorgente {nome_video} nel cloud.")
                    continue
                
                sorgente_id = search_files[0]['id']
                print(f"📥 Download del video originale in corso...")
                
                request = drive_service.files().get_media(fileId=sorgente_id)
                fh = io.FileIO('video_temporaneo.mp4', 'wb')
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                fh.close()
                
                print(f"📤 Salvo una copia nella cartella dei video centralizzati...")
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

            # 3. Estrazione fotogramma
            print("📸 Genero la copertina con FFmpeg...")
            output_image = 'anteprima.jpg'
            if os.path.exists(output_image): os.remove(output_image)
            
            subprocess.run([
                'ffmpeg', '-ss', '00:00:03', '-i', 'video_temporaneo.mp4',
                '-vframes', '1', '-q:v', '2', output_image
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if not os.path.exists(output_image):
                print("❌ Errore durante lo scatto del fotogramma.")
                continue
                
            # 4. Upload della copertina su Drive
            print("📤 Carico lo screenshot...")
            file_metadata = {
                'name': f'Copertina_{nome_video.split(".")[0]}.jpg',
                'parents': [target_folder_id]
            }
            media_foto = MediaFileUpload(output_image, mimeType='image/jpeg')
            foto_caricata = drive_service.files().create(body=file_metadata, media_body=media_foto, fields='id').execute()
            foto_id = foto_caricata.get('id')
            
            permission = {'type': 'anyone', 'role': 'reader'}
            drive_service.permissions().create(fileId=foto_id, body=permission).execute()
            
            # 5. Generazione formula ibrida (Foto + Link cliccabile)
            link_diretto_foto = f'https://docs.google.com/uc?export=download&id={foto_id}'
            
            if link_originale:
                # Se c'era un link social, crea l'immagine cliccabile
                formula_finale = f'=HYPERLINK("{link_originale}"; IMAGE("{link_diretto_foto}"))'
            else:
                # Altrimenti mette solo l'immagine semplice
                formula_finale = f'=IMAGE("{link_diretto_foto}")'
            
            # Aggiorna la colonna J (colonna 10 su gspread) senza spostare nient'altro!
            sheet.update_cell(i + 1, 10, formula_finale)
            print(f"✅ Riga {i+1} completata con successo!")
            
            if os.path.exists('video_temporaneo.mp4'): os.remove('video_temporaneo.mp4')
            if os.path.exists('anteprima.jpg'): os.remove('anteprima.jpg')

if __name__ == '__main__':
    main()
