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
    print("⚠️ ADVERTENCIA: No se encontró GOOGLE_API_KEY.")

# CLIENTE GLOBAL (IA) - Este es el "client" original
client = genai.Client(api_key=api_key)

app = FastAPI(title="API Pictogramas Muna con Memoria")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- GESTIÓN DE MEMORIA ---
ARCHIVO_MEMORIA = "memoria_correcciones.json"


def cargar_memoria():
    if not os.path.exists(ARCHIVO_MEMORIA):
        return {}
    try:
        with open(ARCHIVO_MEMORIA, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def guardar_en_memoria(palabra_original, termino_arasaac):
    memoria = cargar_memoria()
    memoria[palabra_original.lower().strip()] = termino_arasaac.strip()
    with open(ARCHIVO_MEMORIA, "w", encoding="utf-8") as f:
        json.dump(memoria, f, ensure_ascii=False, indent=2)
    print(f"🧠 APRENDIDO: '{palabra_original}' -> '{termino_arasaac}'")


# --- MODELOS ---
class FraseRequest(BaseModel):
    texto: str


class RegenerarRequest(BaseModel):
    original: str
    aclaracion: str


# --- LÓGICA DE BÚSQUEDA ---
async def buscar_pictograma_async(http_client_instance, termino):
    url = f"https://api.arasaac.org/api/pictograms/es/bestsearch/{termino}"
    try:
        response = await http_client_instance.get(url, timeout=4)
        if response.status_code == 200 and response.json():
            data = response.json()
            if data:
                id_picto = data[0]['_id']
                return f"https://static.arasaac.org/pictograms/{id_picto}/{id_picto}_500.png"
    except Exception:
        pass
    return None


# --- IA PRINCIPAL ---
def inteligencia_artificial(frase):
    memoria = cargar_memoria()
    texto_memoria = ""
    if memoria:
        texto_memoria = "REGLAS APRENDIDAS (PRIORIDAD ABSOLUTA):\n"
        for original, termino in memoria.items():
            texto_memoria += f"- '{original}' -> BUSCAR: '{termino}'\n"

    prompt = f"""
    Eres un experto en SAAC. Traduce la frase a conceptos visuales para ARASAAC.
    FRASE: "{frase}"

    {texto_memoria}

    REGLAS GENERALES:
    1. Simplifica gramática. Verbos en INFINITIVO.
    2. CONTEXTO ARGENTINO: "Jardín"->"escuela infantil", "Seño"->"profesora".

    SALIDA JSON: [ {{"original": "palabra", "busqueda_arasaac": "termino"}} ]
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Error IA: {e}")
        return []


# --- ENDPOINTS ---

@app.post("/traducir")
async def traducir_frase(request: FraseRequest):
    print(f"📩 Traduciendo: {request.texto}")
    conceptos = inteligencia_artificial(request.texto)
    lista_conceptos = conceptos if isinstance(conceptos, list) else list(conceptos.values())[0]

    async with httpx.AsyncClient() as http_client:
        tareas = [buscar_pictograma_async(http_client, item.get('busqueda_arasaac', item.get('original'))) for item in
                  lista_conceptos]
        urls = await asyncio.gather(*tareas)

    resultado = []
    for i, item in enumerate(lista_conceptos):
        if urls[i]:
            resultado.append({"palabra": item.get('original'), "imagen": urls[i]})

    return {"status": "ok", "data": resultado}


@app.post("/regenerar")
async def regenerar_picto(request: RegenerarRequest):
    print(f"🔄 Corrigiendo: '{request.original}' con nota: '{request.aclaracion}'")

    prompt = f"""
    Usuario corrige pictograma.
    Original: "{request.original}"
    Aclaración: "{request.aclaracion}"
    Dame SOLO el término de búsqueda exacto para ARASAAC en JSON: {{ "busqueda_arasaac": "termino" }}
    """

    try:
        # Aquí usamos el cliente GLOBAL 'client' sin problemas
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        data_ia = json.loads(response.text)
        nuevo_termino = data_ia.get("busqueda_arasaac", request.aclaracion)

        guardar_en_memoria(request.original, nuevo_termino)

        # CORRECCIÓN AQUÍ: Renombramos 'client' a 'http_client' para no chocar
        async with httpx.AsyncClient() as http_client:
            nuevo_url = await buscar_pictograma_async(http_client, nuevo_termino)

        return {"status": "ok", "nuevo_url": nuevo_url, "termino_usado": nuevo_termino}

    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)