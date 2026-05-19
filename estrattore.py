import os
import json
import subprocess
import sys

# Auto-installazione yt-dlp
try:
    import yt_dlp
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"])
    import yt_dlp

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def main():
    # 1. Autenticazione
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

    # 2. Verifica accesso alla cartella Drive (debug utile)
    try:
        folder_info = drive_service.files().get(
            fileId=target_folder_id,
            fields='id, name, driveId',
            supportsAllDrives=True
        ).execute()
        is_shared_drive = 'driveId' in folder_info
        print(f"📁 Cartella trovata: '{folder_info.get('name')}' | Shared Drive: {is_shared_drive}")
    except Exception as e:
        print(f"❌ ERRORE: Impossibile accedere alla cartella Drive.")
        print(f"   → Assicurati di aver condiviso la cartella col Service Account come Editor.")
        print(f"   → Email SA: {creds_json.get('client_email', 'N/A')}")
        print(f"   → Dettaglio errore: {e}")
        return

    sheet = gc.open_by_key(spreadsheet_id).worksheet('Foglio1')
    dati = sheet.get_all_values()

    if len(dati) <= 1:
        print("Database vuoto.")
        return

    # 3. Mappatura colonne
    headers = [h.strip().lower() for h in dati[0]]

    try:
        idx_link       = headers.index('link')
        idx_nome_video = headers.index('nome_file_video')
        idx_foto1      = headers.index('foto_bot_1')
        idx_foto2      = headers.index('foto_bot_2')
        idx_foto3      = headers.index('foto_bot_3')
        idx_foto4      = headers.index('foto_bot_4')
        idx_foto5      = headers.index('foto_bot_5')
    except ValueError as e:
        print(f"❌ Errore: Colonna mancante → {e}")
        print("   Controlla che la riga 1 del foglio abbia: link, nome_file_video, foto_bot_1 ... foto_bot_5")
        return

    print("📸 Bot Fotografo attivo!")
    print(f"   Service Account: {creds_json.get('client_email', 'N/A')}")

    # 4. Scansione righe
    for i in range(1, len(dati)):
        riga = list(dati[i])  # copia mutabile

        # Padding sicuro
        col_max = max(idx_link, idx_nome_video, idx_foto5)
        while len(riga) <= col_max:
            riga.append("")

        url_social      = riga[idx_link].strip()
        nome_video_att  = riga[idx_nome_video].strip()
        foto1_attuale   = riga[idx_foto1].strip()

        # Salta se non c'è link o foto già presente
        if not url_social.startswith('http'):
            continue
        if foto1_attuale:
            print(f"⏭️  Riga {i+1}: già processata, skip.")
            continue

        print(f"\n🕵️‍♂️ Riga {i+1}: {url_social}")

        if not nome_video_att or not nome_video_att.endswith('.mp4'):
            nome_video_att = f"Video_Riga_{str(i+1).zfill(3)}.mp4"

        video_temporaneo = "video_social.mp4"
        if os.path.exists(video_temporaneo):
            os.remove(video_temporaneo)

        # 5. Download video
        print("📥 Download video in corso...")
        ydl_opts = {
            'format': 'best',
            'outtmpl': video_temporaneo,
            'quiet': True,
            'no_warnings': True
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url_social])
        except Exception as e:
            print(f"⚠️ Download fallito: {e}")
            continue

        if not os.path.exists(video_temporaneo):
            print("❌ File video non trovato dopo il download.")
            continue

        print("🟩 Video scaricato!")

        # 6. Estrazione 5 fotogrammi
        timestamps   = ['00:00:02', '00:00:05', '00:00:08', '00:00:11', '00:00:14']
        formule_foto = []
        nome_base    = nome_video_att.replace('.mp4', '')

        print("📸 Estrazione fotogrammi e upload su Drive...")

        for idx, ts in enumerate(timestamps):
            nome_foto = f"anteprima_{idx+1}.jpg"
            if os.path.exists(nome_foto):
                os.remove(nome_foto)

            subprocess.run([
                'ffmpeg', '-ss', ts, '-i', video_temporaneo,
                '-vframes', '1', '-q:v', '2', nome_foto
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if not os.path.exists(nome_foto):
                print(f"   ⚠️ Fotogramma {idx+1} non estratto (video troppo corto?)")
                formule_foto.append("")
                continue

            # Upload su Drive
            try:
                metadata_foto = {
                    'name': f'Copertina_{idx+1}_{nome_base}.jpg',
                    'parents': [target_folder_id]
                }
                media_foto = MediaFileUpload(nome_foto, mimetype='image/jpeg')

                # FIX PRINCIPALE: supportsAllDrives=True
                file_caricato = drive_service.files().create(
                    body=metadata_foto,
                    media_body=media_foto,
                    fields='id',
                    supportsAllDrives=True      # ← FIX: funziona sia con Drive normale condiviso che Shared Drive
                ).execute()

                id_foto = file_caricato.get('id')

                # Permesso pubblico
                drive_service.permissions().create(
                    fileId=id_foto,
                    body={'type': 'anyone', 'role': 'reader'},
                    supportsAllDrives=True      # ← FIX
                ).execute()

                link_foto = f'https://drive.google.com/uc?export=view&id={id_foto}'

                # Prima foto → hyperlink al video originale
                if idx == 0 and url_social:
                    formula = f'=HYPERLINK("{url_social}"; IMAGE("{link_foto}"))'
                else:
                    formula = f'=IMAGE("{link_foto}")'

                formule_foto.append(formula)
                print(f"   ✅ Foto {idx+1} caricata → {link_foto}")

            except Exception as e:
                print(f"   ❌ Errore upload foto {idx+1}: {e}")
                formule_foto.append("")
            finally:
                if os.path.exists(nome_foto):
                    os.remove(nome_foto)

        # 7. Scrittura sul foglio
        indices_colonne = [idx_foto1, idx_foto2, idx_foto3, idx_foto4, idx_foto5]
        for pos, formula in enumerate(formule_foto):
            if formula:
                sheet.update_cell(i + 1, indices_colonne[pos] + 1, formula)

        # Scrivi nome video se mancante
        if not riga[idx_nome_video].strip():
            sheet.update_cell(i + 1, idx_nome_video + 1, nome_video_att)

        print(f"✅ Riga {i+1} completata!")

        # Pulizia video temporaneo
        if os.path.exists(video_temporaneo):
            os.remove(video_temporaneo)

    print("\n🏁 Bot completato.")

if __name__ == '__main__':
    main()
