import google.generativeai as genai
import os
from dotenv import load_dotenv

# Cargar las variables de entorno (.env)
load_dotenv()

# Configurar la API Key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

print("--- MODELOS DISPONIBLES PARA GENERAR TEXTO ---")
found = False
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"✅ {m.name}")
        found = True

if not found:
    print("❌ No se encontraron modelos. Revisa tu API Key o conexión.")