import firebase_admin
from firebase_admin import credentials, firestore
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SERVICE_ACCOUNT_PATH = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
if SERVICE_ACCOUNT_PATH:
    SERVICE_ACCOUNT_PATH = str(Path(SERVICE_ACCOUNT_PATH).expanduser())
    if not Path(SERVICE_ACCOUNT_PATH).is_file():
        SERVICE_ACCOUNT_PATH = None

if not SERVICE_ACCOUNT_PATH:
    local_key = BASE_DIR / 'serviceAccountKey.json'
    SERVICE_ACCOUNT_PATH = str(local_key) if local_key.exists() else str(BASE_DIR / 'serviceAccountKey.json')

if not firebase_admin._apps:
    if Path(SERVICE_ACCOUNT_PATH).is_file():
        cred = credentials.Certificate(str(SERVICE_ACCOUNT_PATH))
        firebase_admin.initialize_app(cred)
    else:
        firebase_admin.initialize_app()

db = firestore.client()

