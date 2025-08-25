import os
import sys
import subprocess
import sounddevice as sd
from openai import OpenAI
import soundfile as sf
import threading
from pynput import keyboard
import queue
from google.cloud import speech
from google.cloud import texttospeech
from google.oauth2 import service_account
import time
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from datetime import datetime, timedelta
import json

# --- CONFIGURACIÓN PRINCIPAL ---
OPENAI_API_KEY = "ingresa aquí tu clave de OpenRouter"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# --- NOMBRES DE ARCHIVOS DE CREDENCIALES ---
GOOGLE_SERVICE_ACCOUNT_FILE = os.path.join(SCRIPT_DIR, "nombre.json")
GOOGLE_OAUTH_CLIENT_SECRET_FILE = os.path.join(SCRIPT_DIR, "credentials.json")

# --- SELECCIÓN DE MODELOS DE IA ---
BRAIN_MODEL = "mistralai/ministral-8b" 
GENERAL_MODEL = "google/gemini-2.5-flash-lite"

# --- DEFINICIÓN DE PERSONALIDADES (SYSTEM PROMPTS) ---
GENERAL_SYSTEM_PROMPT = (
    "Eres un consultor experto llamado Kepler. Responde siempre en español de manera clara, corta, concisa. "
    "Está estrictamente prohibido usar cualquier tipo de formato Markdown. Todas tus respuestas deben ser solo texto plano."
)
GMAIL_SUMMARY_SYSTEM_PROMPT = (
    "Eres un asistente de correo que solo resume información. Eres extremadamente conciso. "
    "Ve al grano. No uses frases introductorias. Resume cada correo en una sola frase corta y directa. "
    "Tu respuesta total no debe exceder las dos o tres frases. No ofrezcas ayuda adicional ni hagas comentarios."
)

GOOGLE_VOICE_NAME = "es-US-Neural2-B"
SAMPLE_RATE = 48000
CHANNELS = 1
RECORD_KEY = keyboard.Key.ctrl_r
TEMP_WAV_FILE = "temp_recording.wav"

# --- CONFIGURACIÓN DEL HISTORIAL ---
MAX_HISTORIAL = 20
historial_conversacion = []
contador_interacciones = 0

# --- CONFIGURACIÓN DE APIS DE GOOGLE ---
GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/tasks'
]
TOKEN_PICKLE = os.path.join(SCRIPT_DIR, "token.pickle")

# --- INICIALIZACIÓN DE COMPONENTES ---
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENAI_API_KEY)
credentials = service_account.Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE)
stt_client = speech.SpeechClient(credentials=credentials)
tts_client = texttospeech.TextToSpeechClient(credentials=credentials)
print("✅ Clientes de Google inicializados.")

# --- BANDERAS DE ESTADO ---
is_recording = False
is_processing = False
id_microfono = 0
audio_queue = queue.Queue()

# --- FUNCIONES DE AUDIO ---
def seleccionar_microfono():
    nombre_microfono_preferido = "USB Audio Device Estéreo analógico"
    print("\n🎤 Buscando micrófonos...")
    dispositivos = sd.query_devices()
    mics = [(i, disp['name']) for i, disp in enumerate(dispositivos) if disp['max_input_channels'] > 0]
    if not mics:
        print("❌ No se encontraron micrófonos. Saliendo.")
        sys.exit(1)
    for i, name in mics:
        if nombre_microfono_preferido in name:
            print(f"✅ Micrófono preferido encontrado: '{name}'")
            print(f"Seleccionado automáticamente.\n")
            return i
    print(f"⚠️ No se encontró el micrófono '{nombre_microfono_preferido}'.")
    print("Por favor, selecciona uno de la lista:")
    for i, name in mics:
        print(f"  {i}: {name}")
    while True:
        try:
            choice = int(input(f"Selecciona el número de tu micrófono [0-{len(dispositivos)-1}]: "))
            if any(mic[0] == choice for mic in mics):
                print(f"Seleccionaste: {dispositivos[choice]['name']}\n")
                return choice
            else:
                print("Número de dispositivo inválido.")
        except (ValueError, IndexError):
            print("Por favor, introduce un número válido de la lista.")

def hablar_google(texto):
    if not texto: return
    try:
        print(f"🤖 kepler: {texto}")
        synthesis_input = texttospeech.SynthesisInput(text=texto)
        voice = texttospeech.VoiceSelectionParams(language_code="es-US", name=GOOGLE_VOICE_NAME)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16, sample_rate_hertz=24000)
        response = tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        time.sleep(0.5)
        aplay_command = ["aplay", "-r", "24000", "-f", "S16_LE", "-t", "raw", "-"]
        aplay_process = subprocess.Popen(aplay_command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        aplay_process.communicate(input=response.audio_content)
    except Exception as e:
        print(f"\n❌ Error durante la síntesis de voz con Google: {e}")

def transcribir_con_google(audio_filename):
    try:
        with open(audio_filename, "rb") as audio_file:
            content = audio_file.read()
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=SAMPLE_RATE,
            language_code="es-CO",
            model="latest_long"
        )
        print("🗣️  Transcribiendo con Google Cloud...")
        response = stt_client.recognize(config=config, audio=audio)
        return response.results[0].alternatives[0].transcript if response.results else ""
    except Exception as e:
        print(f"❌ Error en la transcripción con Google: {e}")
        return ""

# --- LÓGICA DE AUTENTICACIÓN Y APIS DE GOOGLE ---
def autenticar_google():
    creds = None
    if os.path.exists(TOKEN_PICKLE):
        with open(TOKEN_PICKLE, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_OAUTH_CLIENT_SECRET_FILE, GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PICKLE, 'wb') as token:
            pickle.dump(creds, token)
    return creds

# --- MÓDULO DE GMAIL ---
def crear_query_gmail_con_ia(texto_usuario, model):
    # Formato de fecha para la IA (YYYY/MM/DD)
    fecha_hoy = datetime.now().strftime("%Y/%m/%d")

    # Calcula fechas relativas para los ejemplos
    fecha_ayer = (datetime.now() - timedelta(days=1)).strftime("%Y/%m/%d")
    fecha_hace_una_semana = (datetime.now() - timedelta(days=7)).strftime("%Y/%m/%d")

    # El nuevo y mejorado System Prompt
    system_prompt = f"""
# ROL Y OBJETIVO
Eres un asistente experto cuya única función es convertir peticiones en lenguaje natural a consultas de búsqueda precisas para la API de Gmail.
Debes responder ÚNICAMENTE con un objeto JSON que contenga una sola clave: "query". No agregues explicaciones ni texto adicional.

# FECHA ACTUAL DE REFERENCIA
- La fecha de hoy es: {fecha_hoy}
- Usa esta fecha para resolver peticiones con fechas relativas (ej: "ayer", "la semana pasada", "los últimos 3 días").

# INSTRUCCIONES
1.  **Analiza la petición**: Identifica elementos clave como remitente (`from:`), asunto (`subject:`), palabras clave y rangos de fechas (`after:`, `before:`).
2.  **Construye la consulta**: Usa los operadores de búsqueda de Gmail de forma lógica.
3.  **Incluye siempre `category:primary`**: Para buscar solo en la bandeja de entrada principal.
4.  **Maneja las exclusiones**: Usa el operador `-` para excluir términos (ej: `-from:marketing`).
5.  **Formato estricto**: Tu única salida debe ser un JSON bien formado. Ej: {{"query": "from:ejemplo after:2023/10/26"}}

# EJEMPLOS CLAVE
---
Petición Usuario: "búscame los correos de claudia sobre el reporte trimestral"
Tu Respuesta:
{{"query": "from:claudia subject:(reporte trimestral) category:primary"}}
---
Petición Usuario: "muéstrame los correos que recibí ayer"
Tu Respuesta:
{{"query": "after:{(datetime.now() - timedelta(days=2)).strftime('%Y/%m/%d')} before:{fecha_hoy} category:primary"}}
---
Petición Usuario: "emails de soporte de google de la última semana"
Tu Respuesta:
{{"query": "from:(soporte de google) after:{fecha_hace_una_semana} category:primary"}}
---
Petición Usuario: "correos de facturación que no sean de Amazon"
Tu Respuesta:
{{"query": "subject:(factura OR facturación) -from:amazon category:primary"}}
---
"""
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": texto_usuario}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        respuesta_json = json.loads(completion.choices[0].message.content)
        query = respuesta_json.get("query", "")
        print(f"⚙️ Consulta de Gmail generada por IA: '{query}'")
        return query
    except Exception as e:
        print(f"❌ Error al generar la consulta de Gmail con la IA: {e}")
        # En caso de error, devuelve una consulta simple para no fallar por completo.
        return f"category:primary {texto_usuario}"
def manejar_comando_gmail(query_generada):
    try:
        creds = autenticar_google()
        service = build('gmail', 'v1', credentials=creds)
        resultados = service.users().messages().list(userId='me', q=query_generada.strip(), maxResults=5).execute()
        mensajes = resultados.get('messages', [])
        if not mensajes:
            return None
        lista_correos = []
        for msg in mensajes:
            mensaje = service.users().messages().get(userId='me', id=msg['id']).execute()
            headers = mensaje['payload']['headers']
            asunto = next((h['value'] for h in headers if h['name'] == 'Subject'), "(sin asunto)")
            remitente = next((h['value'] for h in headers if h['name'] == 'From'), "(remitente desconocido)")
            remitente_limpio = remitente.split('<')[0].strip().replace('"', '')
            lista_correos.append(f"De: {remitente_limpio}, Asunto: {asunto}")
        return lista_correos
    except Exception as e:
        print(f"❌ Ocurrió un error consultando Gmail: {e}")
        return None

# --- MÓDULO DE GOOGLE TASKS ---
def crear_tarea_con_ia(texto_usuario, model):
    fecha_hoy = (datetime.now() - timedelta(hours=5)).strftime('%Y-%m-%d')
    system_prompt = f"""
    Tu única función es analizar una petición para crear una tarea. La fecha de hoy es {fecha_hoy}.
    Extrae el título de la tarea.
    Si el usuario especifica una fecha (como "mañana", "el viernes", "el 15 de marzo"), inclúyela.
    Responde ÚNICAMENTE con un objeto JSON con la clave "title" (string) y, opcionalmente, "due_date" (string en formato YYYY-MM-DD).
    Si el usuario NO especifica una fecha, OMITE por completo la clave 'due_date' en tu respuesta.

    Ejemplo 1 (con fecha):
    Usuario: "recuérdame comprar leche mañana"
    Respuesta: {{"title": "Comprar leche", "due_date": "{(datetime.now() - timedelta(hours=5) + timedelta(days=1)).strftime('%Y-%m-%d')}"}}

    Ejemplo 2 (sin fecha):
    Usuario: "anota que debo radicar el sitio de manzanares"
    Respuesta: {{"title": "Radicar el sitio de Manzanares"}}
    """
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": texto_usuario}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        detalles = json.loads(completion.choices[0].message.content)
        print(f"⚙️ Tarea interpretada por IA: {detalles}")
        return detalles
    except Exception as e:
        print(f"❌ Error al interpretar la tarea con la IA: {e}")
        return None

# --- MÓDULO DE GOOGLE TASKS ---

def manejar_consulta_tasks():
    """Consulta y devuelve una lista de tareas pendientes de Google Tasks."""
    try:
        creds = autenticar_google()
        service = build('tasks', 'v1', credentials=creds)
        
        # Pide a la API la lista de tareas que NO están completadas
        resultados = service.tasks().list(tasklist='@default', showCompleted=False).execute()
        items = resultados.get('items', [])

        if not items:
            return None # Devuelve None si no hay tareas

        # Formatea las tareas en una lista de strings
        lista_tareas = [f"- {item['title']}" for item in items]
        print(f"✅ Tareas encontradas: {len(lista_tareas)}")
        return lista_tareas

    except Exception as e:
        print(f"❌ Ocurrió un error consultando Google Tasks: {e}")
        return None

# (Aquí va el resto de tus funciones de tasks: crear_tarea_con_ia, etc.)

def ejecutar_crear_tarea(detalles_tarea):
    try:
        creds = autenticar_google()
        service = build('tasks', 'v1', credentials=creds)
        task = {
            'title': detalles_tarea.get('title', 'Tarea sin título'),
            'notes': 'Tarea creada por Kepler.'
        }
        if 'due_date' in detalles_tarea and detalles_tarea['due_date']:
            task['due'] = f"{detalles_tarea['due_date']}T09:00:00-05:00"
        result = service.tasks().insert(tasklist='@default', body=task).execute()
        print(f"✅ Tarea creada: {result.get('title')}")
        return True
    except Exception as e:
        print(f"❌ Error al crear la tarea en Google Tasks: {e}")
        return False

# --- LÓGICA PRINCIPAL ---
def procesar_comando(audio_filename):
    global historial_conversacion, contador_interacciones, is_processing
    try:
        texto = transcribir_con_google(audio_filename)
        print(f"👤 Tú: {texto}")

        if not texto: return
        if any(palabra in texto.lower() for palabra in ["adiós", "terminar", "salir"]):
            hablar_google("¡Hasta luego!")
            os._exit(0)

        es_comando_gmail = any(palabra in texto.lower() for palabra in ["correo", "gmail", "email", "bandeja"])
        es_comando_crear_tarea = any(palabra in texto.lower() for palabra in [
            "recuérdame", "anota que", "recuerdo que", "añade a mis tareas", "crear tarea"
        ])
        es_comando_consultar_tareas = any(palabra in texto.lower() for palabra in [
            "qué tareas", "cuáles tareas", "mis tareas", "tareas pendientes", "ver tareas", "lista de tareas", "tareas que tengo"
        ])

        if es_comando_gmail:
            print(f"🧠 Usando {BRAIN_MODEL} para la tarea de Gmail...")
            query_precisa = crear_query_gmail_con_ia(texto, model=BRAIN_MODEL)
            correos_encontrados = manejar_comando_gmail(query_precisa)
            if not correos_encontrados:
                hablar_google("No encontré correos que coincidan con tu búsqueda.")
            else:
                contexto_correos = "\n".join(correos_encontrados)
                prompt_resumen = (
                    f"Pregunta del usuario: '{texto}'.\n"
                    f"Correos encontrados:\n{contexto_correos}\n\n"
                    "Resume la información para responder la pregunta."
                )
                historial_temporal = [{"role": "user", "content": prompt_resumen}]
                print(f"🧠 Usando {BRAIN_MODEL} con personalidad concisa para generar el resumen...")
                respuesta_stream = preguntar_a_ia_stream(
                    historial_temporal,
                    model=BRAIN_MODEL,
                    system_prompt=GMAIL_SUMMARY_SYSTEM_PROMPT
                )
                full_response = "".join(chunk.choices[0].delta.content or "" for chunk in respuesta_stream)
                hablar_google(full_response)
            return
        
        elif es_comando_consultar_tareas:
            print("🧠 Consultando tus tareas pendientes...")
            tareas_encontradas = manejar_consulta_tasks()
            if not tareas_encontradas:
                hablar_google("No tienes tareas pendientes. ¡Buen trabajo!")
            else:
                cantidad = len(tareas_encontradas)
                if cantidad == 1:
                    respuesta = f"Tienes una tarea pendiente: {tareas_encontradas[0].replace('- ', '')}"
                else:
                    respuesta = f"Tienes {cantidad} tareas pendientes: " + ", ".join([tarea.replace('- ', '') for tarea in tareas_encontradas])
                hablar_google(respuesta)
            return

        elif es_comando_crear_tarea:
            print(f"🧠 Usando {BRAIN_MODEL} para analizar la tarea...")
            detalles = crear_tarea_con_ia(texto, model=BRAIN_MODEL)
            if detalles and detalles.get("title"):
                if ejecutar_crear_tarea(detalles):
                    hablar_google(f"Anotado: {detalles.get('title')}.")
                else:
                    hablar_google("Lo siento, no pude crear la tarea. Hubo un error.")
            else:
                hablar_google("No entendí bien la tarea. ¿Puedes intentarlo de nuevo?")
            return

        # Si no es un comando específico, procede con la conversación general
        contador_interacciones += 1
        print(f"🗣️  Conversación general usando {GENERAL_MODEL}...")
        if contador_interacciones > MAX_HISTORIAL:
            hablar_google("He olvidado nuestra conversación anterior, empecemos de nuevo.")
            historial_conversacion = []
            contador_interacciones = 1
        historial_conversacion.append({"role": "user", "content": texto})
        respuesta_stream = preguntar_a_ia_stream(
            historial_conversacion,
            model=GENERAL_MODEL,
            system_prompt=GENERAL_SYSTEM_PROMPT
        )
        full_response = "".join(chunk.choices[0].delta.content or "" for chunk in respuesta_stream)
        if full_response:
            historial_conversacion.append({"role": "assistant", "content": full_response})
        hablar_google(full_response)
        
    except Exception as e:
        print(f"❌ Error en el procesamiento: {e}")
    finally:
        is_processing = False
        print(f"\n>> Presiona y mantén la tecla {str(RECORD_KEY).split('.')[-1].upper()} para hablar <<")

def preguntar_a_ia_stream(historial: list, model: str, system_prompt: str):
    try:
        mensajes_para_api = [{"role": "system", "content": system_prompt}] + historial
        stream = client.chat.completions.create(
            model=model,
            messages=mensajes_para_api,
            temperature=0.5,
            stream=True
        )
        yield from stream
    except Exception as e:
        print(f"❌ Error conectando con la API de OpenRouter ({model}): {e}")

# --- MANEJO DE AUDIO Y TECLADO ---
def record_audio_to_file():
    global is_recording, audio_queue
    audio_queue = queue.Queue()
    def audio_callback(indata, frames, time, status):
        if status: print(status, file=sys.stderr)
        audio_queue.put(indata.copy())
    with sf.SoundFile(TEMP_WAV_FILE, mode='w', samplerate=SAMPLE_RATE, channels=CHANNELS) as file:
        with sd.InputStream(samplerate=SAMPLE_RATE, device=id_microfono, channels=CHANNELS, callback=audio_callback):
            while is_recording:
                file.write(audio_queue.get())

def on_press(key):
    global is_recording, is_processing
    if key == RECORD_KEY and not is_recording and not is_processing:
        is_recording = True
        print("🎤 Grabando... (suelta la tecla para detener)", end='\r', flush=True)
        threading.Thread(target=record_audio_to_file, daemon=True).start()

def on_release(key):
    global is_recording, is_processing
    if key == RECORD_KEY and is_recording:
        is_recording = False
        is_processing = True
        print("\n🗣️ Grabación finalizada. Procesando...")
        threading.Thread(target=procesar_comando, args=(TEMP_WAV_FILE,)).start()

# --- BLOQUE PRINCIPAL ---
if __name__ == "__main__":
    id_microfono = seleccionar_microfono()
    hablar_google("Sistema en línea.")
    print(f"\n>> Presiona y mantén la tecla {str(RECORD_KEY).split('.')[-1].upper()} para hablar <<")

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
