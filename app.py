from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import requests
import json
import base64
import time
from groq import Groq

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
#MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

MINIMAX_BASE = "https://api.minimax.io/v1/text/chatcompletion_v2"
#MISTRAL_BASE = "https://api.mistral.ai/v1"

# --------------------------
# Home simple
# --------------------------
@app.route('/')
def home():
    return jsonify({"message": "Servidor backend operativo."})


# --------------------------
# 1️⃣ Ruta STS: recibe audio → LLM → audio respuesta
# --------------------------
@app.route('/sts', methods=['POST'])
def speech_to_speech():
    """
    Flujo completo STS:
    - Recibe archivo de audio (.wav o .mp3)
    - Llama a MiniMax STT para convertirlo en texto
    - Procesa el texto con Mistral (LLM francés)
    - Llama a MiniMax TTS para convertir respuesta a audio
    - Devuelve texto + audio (base64 o URL)
    """
    if 'audio' not in request.files:
        return jsonify({"error": "No se envió archivo de audio"}), 400

    audio_file = request.files['audio']

    # 1️⃣ STT
    stt_text = call_minimax_stt(audio_file)
    if not stt_text:
        return jsonify({"error": "Fallo en transcripción"}), 500

    # 2️⃣ LLM
    llm_output = call_groq_llm(stt_text)
    if isinstance(llm_output, dict):
        llm_text = llm_output.get("reply", str(llm_output))
    else:
        llm_text = str(llm_output)
    action = llm_output.get("action", "none")

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
# Función: MiniMax STT
# --------------------------
def call_minimax_stt(audio_file):
    url = f"{MINIMAX_BASE}/speech:transcribe"
    headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}"}
    files = {"file": (audio_file.filename, audio_file, audio_file.mimetype)}

    try:
        r = requests.post(url, headers=headers, files=files)
        r.raise_for_status()
        result = r.json()
        return result.get("text", "")
    except Exception as e:
        print("Error en STT:", e)
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
# Función: MiniMax TTS
# --------------------------
def call_minimax_tts(text):
    api_key = MINIMAX_API_KEY
    if not api_key:
        print("⚠️ No se encontró MINIMAX_API_KEY en .env")
        return None

    create_url = "https://api.minimax.io/v1/t2a_async_v2"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "speech-2.6-hd",
        "text": text,
        "language_boost": "auto",
        "voice_setting": {
            "voice_id": "English_expressive_narrator",
            "speed": 1,
            "vol": 10,
            "pitch": 1
        },
        "audio_setting": {
            "audio_sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 2
        }
    }

    try:
        r = requests.post(create_url, headers=headers, json=payload)
        r.raise_for_status()
        result = r.json()
        task_id = result.get("task_id")
        if not task_id:
            print("⚠️ No se recibió task_id de MiniMax.")
            return None

        status_url = f"https://api.minimax.io/v1/query/t2a_async_query_v2?task_id={task_id}"

        for _ in range(10):
            time.sleep(1)
            s = requests.get(status_url, headers=headers)
            s.raise_for_status()
            status_data = s.json()

            if status_data.get("status") == "Success":
                file_id = status_data.get("file_id")
                if not file_id:
                    print("⚠️ No se obtuvo file_id del resultado.")
                    return None

                file_url = f"https://api.minimax.io/v1/files/retrieve_content?file_id={file_id}"
                audio_res = requests.get(file_url, headers=headers)
                audio_res.raise_for_status()
                return audio_res.content

            elif status_data.get("status") in ["Running", "Pending"]:
                continue
            else:
                print("⚠️ Estado inesperado:", status_data)
                return None

        print("⏰ Timeout: la tarea de TTS tardó demasiado.")
        return None

    except Exception as e:
        print("Error en TTS:", e)
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
