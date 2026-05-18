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
    
    # ID del tuo foglio principale
    spreadsheet_id = "1s68pw0WEUcV0ZqltiahAqCp_r5rsycSjxKNh0VZQq_g"
sheet = gc.open_by_key(spreadsheet_id).worksheet('DATABASE_IMMOBILI')    
    dati = sheet.get_all_values()
    if len(dati) <= 1:
        print("Database vuoto.")
        return

    # Mappatura colonne dinamica
    headers = [h.strip().lower() for h in dati[0]]
    try:
        idx_anteprima = headers.index('anteprima')
        # Cerca la colonna indipendentemente da come è indicizzata (indice 20 o nome)
        idx_drive = headers.index('cartella drive') if 'cartella drive' in headers else 20
    except ValueError:
        print("Errore: Colonne 'Anteprima' o 'Cartella Drive' non trovate nel foglio.")
        return

    # 2. Scansione Righe alla ricerca di video da fotografare
    for i in range(1, len(dati)):
        riga = dati[i]
        anteprima_attuale = riga[idx_anteprima].strip() if idx_anteprima < len(riga) else ""
        folder_id = riga[idx_drive].strip() if idx_drive < len(riga) else ""
        
        # Se non c'è l'anteprima ma abbiamo l'ID della cartella Drive, il bot si attiva
        if not anteprima_attuale and folder_id and len(folder_id) > 10:
            print(f"🕵️‍♂️ Trovato immobile riga {i+1}. Cerco file video nella cartella: {folder_id}")
            
            # Cerca file .mp4 nella cartella dell'immobile
            query = f"'{folder_id}' in parents and mimeType='video/mp4' and trashed=false"
            results = drive_service.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])
            
            if not files:
                print(f"⚠️ Nessun file .mp4 trovato nella cartella {folder_id}")
                continue
                
            video_id = files[0]['id']
            video_name = files[0]['name']
            print(f"🎥 Scarico il video: {video_name} ({video_id})")
            
            # Download del video nel server temporaneo di GitHub
            request = drive_service.files().get_media(fileId=video_id)
            fh = io.FileIO('video_temporaneo.mp4', 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.close()
            
            # 3. Estrazione fotogramma con FFmpeg al secondo 3
            print("📸 Scatto la fotografia...")
            output_image = 'anteprima.jpg'
            if os.path.exists(output_image): os.remove(output_image)
            
            subprocess.run([
                'ffmpeg', '-ss', '00:00:03', '-i', 'video_temporaneo.mp4',
                '-vframes', '1', '-q:v', '2', output_image
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if not os.path.exists(output_image):
                print("❌ Errore durante lo scatto della foto con FFmpeg.")
                continue
                
            # 4. Upload della foto su Google Drive nella stessa cartella
            print("📤 Carico lo screenshot su Google Drive...")
            file_metadata = {
                'name': f'Copertina_{video_name.split(".")[0]}.jpg',
                'parents': [folder_id]
            }
            media = MediaFileUpload(output_image, mimeType='image/jpeg')
            foto_caricata = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            foto_id = foto_caricata.get('id')
            
            # Rendiamo la foto pubblica leggibile dal browser della WebApp
            permission = {'type': 'anyone', 'role': 'reader'}
            drive_service.permissions().create(fileId=foto_id, body=permission).execute()
            
            # 5. Scrittura del link sul Foglio Google (Formato formula =IMAGE per vederla subito)
            link_diretto_foto = f'https://docs.google.com/uc?export=download&id={foto_id}'
            formula_immagine = f'=IMAGE("{link_diretto_foto}")'
            
            sheet.update_cell(i + 1, idx_anteprima + 1, formula_immagine)
            print(f"✅ Riga {i+1} aggiornata con successo nel Database!")
            
            # Pulizia file temporanei
            if os.path.exists('video_temporaneo.mp4'): os.remove('video_temporaneo.mp4')
            if os.path.exists('anteprima.jpg'): os.remove('anteprima.jpg')

if __name__ == '__main__':
    main()
