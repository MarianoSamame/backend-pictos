import os
import json
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware  # <--- IMPORTANTE
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from google.genai import types

# --- CONFIGURACIÓN ---
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

# Permitimos que arranque sin key localmente, pero fallará si intentas usarlo
if not api_key:
    print("⚠️ ADVERTENCIA: No se encontró GOOGLE_API_KEY. Asegúrate de configurarla en Render.")

# Cliente actualizado
client = genai.Client(api_key=api_key)

app = FastAPI(title="API Pictogramas para Hija")

# --- CONFIGURACIÓN DE CORS (CRÍTICO PARA V0 Y WEB APPS) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # "*" significa "Todos". En el futuro pondremos solo tu dominio.
    allow_credentials=True,
    allow_methods=["*"],  # Permitir POST, GET, OPTIONS, etc.
    allow_headers=["*"],
)


class FraseRequest(BaseModel):
    texto: str


# --- LÓGICA ---
def buscar_pictograma_arasaac(termino):
    url = f"https://api.arasaac.org/api/pictograms/es/bestsearch/{termino}"
    try:
        res = requests.get(url, timeout=3)
        if res.status_code == 200 and res.json():
            id_picto = res.json()[0]['_id']
            return f"https://static.arasaac.org/pictograms/{id_picto}/{id_picto}_500.png"
    except Exception:
        pass
    return None


def inteligencia_artificial(frase):
    prompt = f"""
    Eres un experto en SAAC. Traduce la frase coloquial a conceptos visuales simples para ARASAAC.
    FRASE: "{frase}"
    REGLAS:
    1. Simplifica gramática. Verbos en INFINITIVO.
    2. CONTEXTO ARGENTINO: "Jardín"->buscar "escuela". "Seño"->buscar "profesora". "Rico"->buscar "gustar".
    3. Elimina artículos/preposiciones inútiles.

    SALIDA JSON: [ {{"original": "palabra", "busqueda_arasaac": "termino"}} ]
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Error IA: {e}")
        return []


@app.post("/traducir")
async def traducir_frase(request: FraseRequest):
    print(f"📩 Recibido: {request.texto}")
    conceptos = inteligencia_artificial(request.texto)

    resultado_final = []
    lista_conceptos = conceptos if isinstance(conceptos, list) else list(conceptos.values())[0]

    for item in lista_conceptos:
        termino = item.get('busqueda_arasaac', item.get('original'))
        url = buscar_pictograma_arasaac(termino)
        if url:
            resultado_final.append({
                "palabra": item.get('original'),
                "imagen": url
            })

    return {"status": "ok", "data": resultado_final}