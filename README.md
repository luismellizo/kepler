 
 # Kepler - Asistente de Voz de Escritorio

Kepler es un asistente de voz personalizable diseñado para ejecutarse en tu escritorio. Te permite interactuar con potentes modelos de lenguaje (LLMs) y servicios de Google como Gmail y Google Tasks, todo a través de comandos de voz.

Este proyecto está diseñado para ser un punto de partida robusto y una demostración de cómo integrar múltiples APIs y tecnologías de voz en una sola aplicación Python.

 <!-- TODO: Reemplazar con un GIF de demostración real -->

## ✨ Características

- **Conversación Fluida**: Mantén conversaciones generales con un LLM de tu elección.
- **Integración con Gmail**: Pide resúmenes de tus correos electrónicos recientes con filtros complejos en lenguaje natural (ej: "búscame los correos de claudia sobre el reporte de la semana pasada").
- **Gestión de Google Tasks**: Crea y consulta tus tareas pendientes directamente con la voz (ej: "recuérdame llamar al banco mañana" o "qué tareas tengo pendientes").
- **Activación por Tecla Rápida**: Usa `Ctrl+R` (configurable) para grabar tu voz, sin necesidad de tener una ventana en foco.
- **Voz y Transcripción de Alta Calidad**: Utiliza los servicios de Google Cloud para síntesis de voz (Text-to-Speech) y transcripción (Speech-to-Text).
- **Configurable y Extensible**: Cambia fácilmente los modelos de IA, las personalidades (prompts), la voz y más, a través de un archivo de configuración centralizado.
- **Seguro**: Mantiene tus claves de API y tokens de autenticación fuera del código fuente, utilizando un archivo `.env`.

## 🛠️ Tecnologías Utilizadas

- **Lenguaje**: Python 3.9+
- **Modelos de IA**:
  - Compatible con cualquier modelo accesible a través de una API compatible con OpenAI (se usa OpenRouter por defecto para acceder a modelos como Mixtral y Gemini).
- **APIs de Google Cloud**:
  - **Speech-to-Text**: Para transcripción de voz.
  - **Text-to-Speech**: Para generar la voz del asistente.
- **APIs de Google Workspace**:
  - **Gmail API**: Para leer y resumir correos.
  - **Google Tasks API**: Para gestionar tareas.
- **Librerías Principales**:
  - `sounddevice` & `soundfile`: Para grabación de audio.
  - `pynput`: Para la escucha global de la tecla de activación.
  - `openai`: Cliente para interactuar con la API de LLMs.
  - `google-api-python-client`, `google-auth-oauthlib`: Para la autenticación y uso de las APIs de Google.
  - `python-dotenv`: Para la gestión de variables de entorno (claves de API).

## 🚀 Instalación y Configuración

Sigue estos pasos para poner a Kepler en funcionamiento en tu sistema (probado en Linux).

### 1. Prerrequisitos

- Python 3.9 o superior.
- `pip` y `venv` para la gestión de paquetes y entornos virtuales.
- `portaudio` para la grabación de audio. En sistemas Debian/Ubuntu, instálalo con:
  ```bash
  sudo apt-get update
  sudo apt-get install portaudio19-dev
  ```
- `aplay` para la reproducción de audio. Viene incluido en el paquete `alsa-utils`:
  ```bash
  sudo apt-get install alsa-utils
  ```

### 2. Clonar el Repositorio

```bash
git clone https://github.com/tu-usuario/kepler-asistente.git
cd kepler-asistente
```

### 3. Configurar las Credenciales de Google

Kepler necesita dos tipos de credenciales de Google: una **Cuenta de Servicio** (para STT/TTS) y un **ID de Cliente OAuth 2.0** (para Gmail/Tasks).

1.  **Crea un proyecto en Google Cloud Console**: Si no tienes uno, crea un nuevo proyecto aquí.
2.  **Habilita las APIs**: En tu proyecto, habilita las siguientes APIs:
    - `Google Cloud Speech-to-Text API`
    - `Google Cloud Text-to-Speech API`
    - `Gmail API`
    - `Google Tasks API`
3.  **Crea una Cuenta de Servicio**:
    - Ve a "IAM y Administración" > "Cuentas de servicio".
    - Crea una nueva cuenta de servicio. Dale un nombre (ej: `kepler-assistant`).
    - Descarga la clave en formato JSON.
    - **Crea un directorio `credentials`** dentro del proyecto y mueve el archivo JSON descargado a `credentials/service_account.json`.
4.  **Crea Credenciales OAuth 2.0**:
    - Ve a "APIs y Servicios" > "Credenciales".
    - Haz clic en "Crear credenciales" > "ID de cliente de OAuth".
    - Selecciona "Aplicación de escritorio" como tipo de aplicación.
    - Descarga el archivo JSON.
    - **Mueve el archivo JSON descargado a `credentials/oauth_client_secret.json`**.

### 4. Configurar la Clave de API del LLM

1.  Crea un archivo `.env` en la raíz del proyecto, copiando el ejemplo:
    ```bash
    cp .env.example .env
    ```
2.  Abre el archivo `.env` y pega tu clave de API. Por defecto, se usa OpenRouter, que te da acceso a muchos modelos. Puedes obtener una clave en openrouter.ai.
    ```
    OPENAI_API_KEY="sk-or-v1-tu-clave-aqui"
    ```

### 5. Instalar Dependencias

Crea y activa un entorno virtual, y luego instala las librerías necesarias.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## ▶️ Cómo Usarlo

1.  **Ejecuta el script principal**:
    ```bash
    python main.py
    ```
2.  La primera vez que lo ejecutes, se abrirá una ventana en tu navegador para que autorices el acceso a tu cuenta de Google (Gmail y Tasks). Inicia sesión y concede los permisos. Se creará un archivo `token.pickle` en la carpeta `credentials` para no tener que volver a autenticarte.
3.  El script te pedirá que selecciones un micrófono si no encuentra el preferido.
4.  Una vez que veas el mensaje `Sistema en línea.`, ¡Kepler está listo!
5.  **Mantén presionada la tecla `Ctrl+R`** para hablar. Suelta la tecla para que el asistente procese tu petición.

### Ejemplos de Comandos

- **Conversación**: "cuéntame un dato curioso sobre el espacio"
- **Gmail**: "búscame los correos de facturación de la última semana que no sean de Amazon"
- **Crear Tarea**: "recuérdame comprar leche mañana a las 9 de la mañana"
- **Consultar Tareas**: "qué tareas tengo para hoy"

## 💡 Integración con Polybar

Para un acceso rápido, puedes añadir un módulo a tu barra de estado como Polybar.

1.  Crea un script de lanzamiento, por ejemplo `launch_kepler.sh`:
    ```bash
    #!/bin/bash
    # Ruta a tu entorno virtual y al script
    VENV_PATH="/ruta/completa/a/tu/proyecto/kepler-asistente/venv/bin/activate"
    SCRIPT_PATH="/ruta/completa/a/tu/proyecto/kepler-asistente/main.py"
    # Activa el entorno y ejecuta el script en una nueva terminal
    source "$VENV_PATH"
    gnome-terminal -- python "$SCRIPT_PATH"
    ```
    Asegúrate de darle permisos de ejecución: `chmod +x launch_kepler.sh`.

2.  Añade un módulo a tu `config.ini` de Polybar:
    ```ini
    [module/kepler]
    type = custom/script
    exec = /ruta/completa/a/tu/proyecto/kepler-asistente/launch_kepler.sh
    label = 🤖
    click-left = %exec%
    ```

Ahora, al hacer clic en el ícono 🤖 en tu Polybar, se lanzará el asistente.

## 📜 Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo `LICENSE` para más detalles.
