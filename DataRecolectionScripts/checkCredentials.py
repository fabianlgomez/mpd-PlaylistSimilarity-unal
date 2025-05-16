import os
from dotenv import load_dotenv

load_dotenv()                     # carga .env si existe
print("CLIENT_ID:", os.getenv("SPOTIPY_CLIENT_ID"))
print("CLIENT_SECRET:", os.getenv("SPOTIPY_CLIENT_SECRET"))
print("REDIRECT_URI:", os.getenv("SPOTIPY_REDIRECT_URI"))
print("SCOPE:", os.getenv("SPOTIPY_SCOPE"))
print("USERNAME:", os.getenv("SPOTIPY_USERNAME"))