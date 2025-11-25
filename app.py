from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import requests
import json
import base64
import time
from groq import Groq
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import texttospeech_v1 as texttospeech
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

GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
GOOGLE_CLIENT_EMAIL = os.getenv("GOOGLE_CLIENT_EMAIL")
GOOGLE_PRIVATE_KEY = os.getenv("GOOGLE_PRIVATE_KEY")


def get_google_credentials():
    """Construye credenciales de servicio de Google a partir de variables de entorno."""
    if not (GOOGLE_PROJECT_ID and GOOGLE_CLIENT_EMAIL and GOOGLE_PRIVATE_KEY):
        print("⚠️ Faltan variables de entorno de Google Cloud (GOOGLE_PROJECT_ID / GOOGLE_CLIENT_EMAIL / GOOGLE_PRIVATE_KEY)")
        return None

    try:
        info = {
            "type": "service_account",
            "project_id": GOOGLE_PROJECT_ID,
            "client_email": GOOGLE_CLIENT_EMAIL,
            # Las keys suelen venir con \n escapados en env vars
            "private_key": GOOGLE_PRIVATE_KEY.replace("\\n", "\n"),
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        return service_account.Credentials.from_service_account_info(info)
    except Exception as e:
        print("Error construyendo credenciales de Google:", e)
        return None

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
    - Convierte la respuesta a audio con Google TTS
    - Devuelve texto + audio (base64)
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

    # 3️⃣ TTS
    tts_audio = call_minimax_tts(llm_text)
    audio_base64 = base64.b64encode(tts_audio).decode('utf-8') if tts_audio else None

    # 4️⃣ Respuesta
    return jsonify({
        "stt_text": stt_text,
        "llm_response": llm_text,
        "action": action,
        "audio_base64": audio_base64
    })


# --------------------------
# Función: STT con Google Cloud
# --------------------------
def call_minimax_stt(audio_file):
    """Compatibilidad de nombre: ahora usa Google Speech-to-Text.

    - Recibe el archivo de audio (WAV/MP3) desde Flask.
    - Llama a Google Speech-to-Text.
    - Devuelve el texto transcrito o None en caso de error.
    """
    creds = get_google_credentials()
    if creds is None:
        return None

    client = speech.SpeechClient(credentials=creds)

    try:
        audio_bytes = audio_file.read()
        audio = speech.RecognitionAudio(content=audio_bytes)

        # Usamos ENCODING_UNSPECIFIED para que Google intente detectar el formato.
        config = speech.RecognitionConfig(
            language_code="es-PE",  # Ajusta si prefieres "es-ES" u otro dialecto.
            encoding=speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,
        )

        response = client.recognize(config=config, audio=audio)
        if not response.results:
            return ""

        return response.results[0].alternatives[0].transcript
    except Exception as e:
        print("Error en Google STT:", e)
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
# Función: TTS con Google Cloud
# --------------------------
def call_minimax_tts(text):
    """Compatibilidad de nombre: ahora usa Google Text-to-Speech.

    - Recibe texto en español.
    - Llama a Google TTS y devuelve bytes MP3.
    """
    creds = get_google_credentials()
    if creds is None:
        return None

    client = texttospeech.TextToSpeechClient(credentials=creds)

    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice_params = texttospeech.VoiceSelectionParams(
        language_code="es-PE",  # Cambia a "es-ES" u otro si lo prefieres.
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
    )

    try:
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice_params,
            audio_config=audio_config,
        )
        return response.audio_content
    except Exception as e:
        print("Error en Google TTS:", e)
        return None


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

    # (Opcional) convertir respuesta a audio
    tts_audio = call_minimax_tts(llm_text)
    audio_base64 = base64.b64encode(tts_audio).decode("utf-8") if tts_audio else None

    return jsonify({
        "text_response": llm_text,
        "audio_base64": audio_base64
    })

# --------------------------
# Ejecutar servidor
# --------------------------
if __name__ == '__main__':
    load_dotenv()
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
