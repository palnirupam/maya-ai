import os
import sys

sys.path.append("c:\\maya-ai\\backend")
from database.connection import SessionLocal
from database.models import UserPreferences
from database.crypto import crypto_manager
from google import genai

db = SessionLocal()
pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_KEY").first()
db.close()

if not pref or not pref.value:
    print("API Key not set in DB!")
    sys.exit(1)

api_key = crypto_manager.decrypt(pref.value)
client = genai.Client(api_key=api_key)

models_to_test = [
    'gemini-embedding-2',
    'models/gemini-embedding-2',
    'gemini-embedding-2-preview',
    'models/gemini-embedding-2-preview',
    'gemini-embedding-001',
    'models/gemini-embedding-001'
]

for model in models_to_test:
    try:
        print(f"Testing model: {model}")
        response = client.models.embed_content(
            model=model,
            contents="Hello World"
        )
        print("SUCCESS with", model)
        if hasattr(response, 'embedding') and response.embedding:
            print("Embedding values length:", len(response.embedding.values))
            print("Snippet:", response.embedding.values[:5])
        elif hasattr(response, 'embeddings') and response.embeddings:
            print("Embeddings length:", len(response.embeddings))
            print("Embedding 0 values length:", len(response.embeddings[0].values))
            print("Snippet:", response.embeddings[0].values[:5])
        break
    except Exception as e:
        print(f"FAILED with {model}: {e}")
