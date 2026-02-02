import os
import json
import asyncio
import httpx  # <--- La nueva librería turbo
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from google.genai import types

# --- CONFIGURACIÓN ---
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    print("⚠️ ADVERTENCIA: No se encontró GOOGLE_API_KEY.")

client = genai.Client(api_key=api_key)

app = FastAPI(title="API Pictogramas Turbo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FraseRequest(BaseModel):
    texto: str


# --- FUNCIONES DE LÓGICA ---

# Versión ASÍNCRONA de la búsqueda (La clave de la velocidad)
async def buscar_pictograma_async(client_http, termino):
    url = f"https://api.arasaac.org/api/pictograms/es/bestsearch/{termino}"
    try:
        response = await client_http.get(url, timeout=3)  # No bloquea, espera en paralelo
        if response.status_code == 200 and response.json():
            data = response.json()
            if data:
                id_picto = data[0]['_id']
                return f"https://static.arasaac.org/pictograms/{id_picto}/{id_picto}_500.png"
    except Exception as e:
        print(f"Error buscando {termino}: {e}")
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

    # 1. IA (Esto sigue siendo secuencial, pero es rápido)
    conceptos = inteligencia_artificial(request.texto)

    # Normalización
    lista_conceptos = conceptos if isinstance(conceptos, list) else list(conceptos.values())[0]

    # 2. BÚSQUEDA PARALELA 🚀
    # Creamos un cliente asíncrono y lanzamos todas las peticiones a la vez
    async with httpx.AsyncClient() as http_client:
        tareas = []
        for item in lista_conceptos:
            termino = item.get('busqueda_arasaac', item.get('original'))
            # Encolamos la tarea, no la ejecutamos todavía
            tareas.append(buscar_pictograma_async(http_client, termino))

        # ¡FUEGO! Ejecutamos todas juntas y esperamos
        urls_imagenes = await asyncio.gather(*tareas)

    # 3. Reconstruir el resultado
    resultado_final = []
    for i, item in enumerate(lista_conceptos):
        url = urls_imagenes[i]
        if url:
            resultado_final.append({
                "palabra": item.get('original'),
                "imagen": url
            })

    return {"status": "ok", "data": resultado_final}git add .