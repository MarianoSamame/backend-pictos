import os
import json
import asyncio
import httpx
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
    print("⚠️ ADVERTENCIA: No se encontró GOOGLE_API_KEY. Asegúrate de configurarla en Render.")

# Cliente de Google Gemini
client = genai.Client(api_key=api_key)

# App FastAPI
app = FastAPI(title="API Pictogramas Muna")

# Configuración de CORS (Permite que la Web App hable con el servidor)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- MODELOS DE DATOS ---

class FraseRequest(BaseModel):
    texto: str


class RegenerarRequest(BaseModel):
    original: str  # La palabra que falló (ej: "papá")
    aclaracion: str  # Tu corrección (ej: "padre de familia hombre")


# --- LÓGICA DE BÚSQUEDA (ASÍNCRONA) ---

async def buscar_pictograma_async(client_http, termino):
    """Busca en ARASAAC de forma asíncrona (no bloquea el servidor)."""
    url = f"https://api.arasaac.org/api/pictograms/es/bestsearch/{termino}"
    try:
        response = await client_http.get(url, timeout=4)
        if response.status_code == 200 and response.json():
            data = response.json()
            if data:
                id_picto = data[0]['_id']
                return f"https://static.arasaac.org/pictograms/{id_picto}/{id_picto}_500.png"
    except Exception as e:
        print(f"Error buscando '{termino}': {e}")
    return None


# --- LÓGICA DE IA (TRADUCCIÓN PRINCIPAL) ---

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


# --- ENDPOINTS ---

@app.post("/traducir")
async def traducir_frase(request: FraseRequest):
    print(f"📩 Recibido para traducir: {request.texto}")

    # 1. Procesar con IA (Obtener los términos de búsqueda)
    conceptos = inteligencia_artificial(request.texto)

    # Normalización si la IA devuelve un diccionario envuelto
    lista_conceptos = conceptos if isinstance(conceptos, list) else list(conceptos.values())[0]

    # 2. Búsqueda Paralela (Turbo) 🚀
    async with httpx.AsyncClient() as http_client:
        tareas = []
        for item in lista_conceptos:
            termino = item.get('busqueda_arasaac', item.get('original'))
            tareas.append(buscar_pictograma_async(http_client, termino))

        # Ejecutar todas las búsquedas a la vez
        urls_imagenes = await asyncio.gather(*tareas)

    # 3. Armar respuesta final
    resultado_final = []
    for i, item in enumerate(lista_conceptos):
        url = urls_imagenes[i]
        if url:
            resultado_final.append({
                "palabra": item.get('original'),
                "imagen": url
            })

    return {"status": "ok", "data": resultado_final}


@app.post("/regenerar")
async def regenerar_picto(request: RegenerarRequest):
    print(f"🔄 Regenerando '{request.original}' con nota: {request.aclaracion}")

    # 1. Usamos la IA para entender la corrección del usuario
    prompt = f"""
    El usuario quiere cambiar un pictograma incorrecto.
    Palabra original: "{request.original}"
    Aclaración del usuario: "{request.aclaracion}"

    Tu tarea: Basado en la aclaración, dame UN ÚNICO término de búsqueda para ARASAAC.
    Ejemplo: Si original es "papá" y aclaración es "padre de familia", tu respuesta es: "padre".
    Ejemplo: Si original es "banco" y aclaración es "para sentarse", tu respuesta es: "banco parque".

    Responde SOLAMENTE un JSON: {{ "busqueda_arasaac": "termino" }}
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        data_ia = json.loads(response.text)
        # Obtenemos el término limpio o usamos la aclaración si falla algo
        termino_nuevo = data_ia.get("busqueda_arasaac", request.aclaracion)

        # 2. Buscamos la nueva imagen
        async with httpx.AsyncClient() as http_client:
            nuevo_url = await buscar_pictograma_async(http_client, termino_nuevo)

        return {
            "status": "ok",
            "nuevo_url": nuevo_url,
            "termino_usado": termino_nuevo
        }

    except Exception as e:
        print(f"Error regenerando: {e}")
        return {"status": "error", "message": str(e)}


# Si se ejecuta directo para pruebas locales
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)