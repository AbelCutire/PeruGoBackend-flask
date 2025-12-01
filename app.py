from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import requests
import base64
from groq import Groq

load_dotenv()
app = Flask(__name__)
CORS(app)

# Blueprint si lo usas
try:
    from generate_rdf import rdf_bp
    app.register_blueprint(rdf_bp)
except:
    pass

SPEECH_API_KEY = os.getenv("SPEECH_API_KEY")

@app.route("/")
def home():
    return jsonify({"message": "Servidor backend operativo."})


# =========================================================
# FUNCIÓN STT POR BYTES BASE64 (SEGURA Y ROBUSTA)
# =========================================================
def google_stt_raw_bytes(audio_bytes: bytes):
    header = audio_bytes[:12]
    
    # Detección de encoding basada en cabeceras de archivo (Magic Bytes)
    if header.startswith(b'RIFF') and b'WAVE' in header:
        # Formato WAV (Viene de iOS)
        encoding = "LINEAR16"
    elif header.startswith(b'#!AMR-WB'):
        # Formato AMR Wideband (Viene de Android)
        encoding = "AMR_WB"
    elif header.startswith(b'\x1A\x45\xDF\xA3'):
        # Formato WebM (Viene de Web)
        encoding = "WEBM_OPUS"
    else:
        # Fallback (Aunque es probable que falle si no es uno de los anteriores)
        print("⚠️ Formato no reconocido, intentando MP3 por defecto.")
        encoding = "MP3"

    print("📊 Encoding detectado:", encoding)
    print("📏 Tamaño recibido:", len(audio_bytes))

    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    payload = {
        "config": {
            "encoding": encoding,
            "sampleRateHertz": 16000, # Importante forzar el sampleRate
            "languageCode": "es-PE",
            "enableAutomaticPunctuation": True,
        },
        "audio": {
            "content": audio_b64
        }
    }

    url = f"https://speech.googleapis.com/v1/speech:recognize?key={SPEECH_API_KEY}"

# =========================================================
# RUTA STT BASE64
# =========================================================
@app.route("/stt_base64", methods=["POST"])
def stt_base64():
    data = request.get_json()

    if not data or "audio_base64" not in data:
        return jsonify({"error": "audio_base64 no proporcionado"}), 400

    audio_bytes = base64.b64decode(data["audio_base64"])
    text = google_stt_raw_bytes(audio_bytes)

    if text is None:
        return jsonify({"error": "Error en STT"}), 500

    return jsonify({"stt_text": text})


# =========================================================
# RUTA STS (AUDIO → TEXTO → LLM)
# =========================================================
def call_groq_llm(user_text):
    try:
        client = Groq()
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente turístico de PerúGo. "
                        "Responde siempre en español en texto plano."
                    )
                },
                {"role": "user", "content": user_text}
            ],
            temperature=0.5
        )
        return completion.choices[0].message.content.strip()

    except Exception as e:
        print("Error Groq:", e)
        return "Error con LLM"


@app.route("/process", methods=["POST"])
def process_text():
    data = request.get_json(silent=True) or {}
    user_text = (data.get("text") or "").strip()

    if not user_text:
        return jsonify({"text_response": "Texto vacío"}), 400

    llm_text = call_groq_llm(user_text)

    return jsonify({
        "text_response": {
            "reply": llm_text
        }
    })


@app.route("/sts", methods=["POST"])
def sts():
    # Intentar leer JSON de forma silenciosa (para evitar 415 si no es application/json)
    data = request.get_json(silent=True)

    audio_bytes = None

    # Caso 1: JSON con audio_base64
    if data and "audio_base64" in data:
        audio_bytes = base64.b64decode(data["audio_base64"])

    # Caso 2: multipart/form-data con archivo 'audio'
    elif "audio" in request.files:
        audio_file = request.files["audio"]
        audio_bytes = audio_file.read()

    if audio_bytes is None:
        return jsonify({"error": "audio o audio_base64 requerido"}), 400

    stt_text = google_stt_raw_bytes(audio_bytes)

    if stt_text is None:
        return jsonify({"error": "Fallo en STT"}), 500

    llm_text = call_groq_llm(stt_text)

    return jsonify({
        "stt_text": stt_text,
        "llm_response": llm_text,
        "action": "none"
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
