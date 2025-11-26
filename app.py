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

    if header.startswith(b'RIFF') and b'WAVE' in header:
        encoding = "LINEAR16"
    elif header[4:8] == b'ftyp':
        encoding = "MP3"
    elif header.startswith(b'\xff\xfb') or header.startswith(b'ID3'):
        encoding = "MP3"
    elif header.startswith(b'\x1A\x45\xDF\xA3'):
        encoding = "WEBM_OPUS"
    else:
        encoding = "MP3"

    print("📊 Encoding detectado:", encoding)
    print("📏 Tamaño recibido:", len(audio_bytes))

    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    payload = {
        "config": {
            "encoding": encoding,
            "languageCode": "es-PE",
            "enableAutomaticPunctuation": True,
        },
        "audio": {
            "content": audio_b64
        }
    }

    url = f"https://speech.googleapis.com/v1/speech:recognize?key={SPEECH_API_KEY}"

    resp = requests.post(url, json=payload, timeout=30)

    if resp.status_code != 200:
        print("❌ Error STT:", resp.text[:500])
        return None

    data = resp.json()
    results = data.get("results", [])

    if not results:
        print("⚠️ STT vacío")
        return ""

    transcript = results[0]["alternatives"][0]["transcript"]
    print("✅ Texto:", transcript)
    return transcript


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


@app.route("/sts", methods=["POST"])
def sts():
    data = request.get_json()

    if not data or "audio_base64" not in data:
        return jsonify({"error": "audio_base64 requerido"}), 400

    audio_bytes = base64.b64decode(data["audio_base64"])
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
