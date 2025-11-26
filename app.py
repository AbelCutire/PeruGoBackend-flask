from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import requests
import json
import base64
import time
from groq import Groq
from google.cloud import speech_v1 as speech
from google.oauth2 import service_account

# --------------------------
# Configuración base
# --------------------------
load_dotenv()
app = Flask(__name__)
CORS(app)

# ✅ Importamos el blueprint RDF
from generate_rdf import rdf_bp
app.register_blueprint(rdf_bp)

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")

# Credenciales para Google Speech-to-Text (service account)
GOOGLE_STT_PROJECT_ID = os.getenv("GOOGLE_STT_PROJECT_ID")
GOOGLE_STT_CLIENT_EMAIL = os.getenv("GOOGLE_STT_CLIENT_EMAIL")
GOOGLE_STT_PRIVATE_KEY = os.getenv("GOOGLE_STT_PRIVATE_KEY")

# --------------------------
# Home simple
# --------------------------
@app.route('/')
def home():
    return jsonify({"message": "Servidor backend operativo."})


# --------------------------
# 1️⃣ Ruta STT pura: solo transcripción con Google
# --------------------------
@app.route('/stt', methods=['POST'])
def speech_to_text_only():
    """Recibe audio y devuelve solo el texto transcrito usando Google STT."""
    if 'audio' not in request.files:
        return jsonify({"error": "No se envió archivo de audio"}), 400

    audio_file = request.files['audio']
    stt_text = call_minimax_stt(audio_file)

    # None = error duro, "" = transcripción vacía pero válida
    if stt_text is None:
        return jsonify({"error": "Fallo en transcripción"}), 500

    return jsonify({
        "stt_text": stt_text
    })


# --------------------------
# 2️⃣ Ruta STS: recibe audio → LLM → audio respuesta
# --------------------------
@app.route('/sts', methods=['POST'])
def speech_to_speech():
    """
    Flujo completo STS:
    - Recibe archivo de audio (.wav o .mp3)
    - Convierte a texto con Google STT
    - Procesa el texto con Groq (LLM)
    - Devuelve texto de entrada + respuesta del LLM.
    """
    if 'audio' not in request.files:
        return jsonify({"error": "No se envió archivo de audio"}), 400

    audio_file = request.files['audio']

    # 1️⃣ STT
    stt_text = call_minimax_stt(audio_file)
    if stt_text is None:
        return jsonify({"error": "Fallo en transcripción"}), 500

    # 2️⃣ LLM
    llm_text = call_groq_llm(stt_text)
    action = "none"  # Reservado por si luego quieres devolver acciones estructuradas

    # 3️⃣ Respuesta (solo texto, sin TTS)
    return jsonify({
        "stt_text": stt_text,
        "llm_response": llm_text,
        "action": action
    })


# --------------------------
# Función: STT con Google Cloud (service account)
# --------------------------
def call_minimax_stt(audio_file):
    """Compatibilidad de nombre: ahora usa Google Speech-to-Text con cuenta de servicio.

    - Recibe el archivo de audio (WAV/MP3) desde Flask.
    - Usa las variables GOOGLE_STT_PROJECT_ID, GOOGLE_STT_CLIENT_EMAIL y
      GOOGLE_STT_PRIVATE_KEY para autenticarse.
    - Devuelve el texto transcrito o None en caso de error.
    """

    if not (GOOGLE_STT_PROJECT_ID and GOOGLE_STT_CLIENT_EMAIL and GOOGLE_STT_PRIVATE_KEY):
        print("⚠️ Faltan variables de entorno de Google Cloud para STT")
        return None

    try:
        audio_bytes = audio_file.read()

        # Construimos las credenciales desde las variables de entorno.
        info = {
            "type": "service_account",
            "project_id": GOOGLE_STT_PROJECT_ID,
            "client_email": GOOGLE_STT_CLIENT_EMAIL,
            "private_key": GOOGLE_STT_PRIVATE_KEY.replace("\\n", "\n"),
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        creds = service_account.Credentials.from_service_account_info(info)

        client = speech.SpeechClient(credentials=creds)

        audio = speech.RecognitionAudio(content=audio_bytes)
        # No especificamos encoding para que Google lo detecte automáticamente.
        config = speech.RecognitionConfig(
            language_code="es-PE",
            enable_automatic_punctuation=True,
        )

        response = client.recognize(config=config, audio=audio)
        if not response.results:
            return ""

        return response.results[0].alternatives[0].transcript
    except Exception as e:
        print("Error en Google STT (service account):", e)
        return None


# --------------------------
# Función: LLM (Mistral)
# --------------------------
def call_groq_llm(user_text):
    """
    Envía el texto del usuario a Groq (modelo LLaMA 3.3) y devuelve
    solo una respuesta breve en español, sin formato JSON.
    """
    try:
        from groq import Groq
        client = Groq()

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente turístico de PerúGo. "
                        "Responde siempre en español de forma breve, amable y natural. "
                        "No uses JSON ni estructuras, solo texto plano."
                    )
                },
                {"role": "user", "content": user_text}
            ],
            temperature=0.5
        )

        return completion.choices[0].message.content.strip()

    except Exception as e:
        print("Error en Groq:", e)
        return "Error procesando solicitud con Groq."

    


# --------------------------
# 2️⃣ Ruta: /process - texto plano → LLM → TTS
# --------------------------
@app.route('/process', methods=['POST'])
def process_text():
    data = request.get_json()
    user_text = data.get("text", "").strip()

    if not user_text:
        return jsonify({"error": "No se recibió texto"}), 400

    llm_text = call_groq_llm(user_text)

    # Devolvemos solo el texto generado por el LLM (sin TTS)
    return jsonify({
        "text_response": llm_text
    })

# --------------------------
# Ejecutar servidor
# --------------------------
if __name__ == '__main__':
    load_dotenv()
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
