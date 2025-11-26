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

# API key para Google Speech-to-Text (REST)
SPEECH_API_KEY = os.getenv("SPEECH_API_KEY")

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
# Función: STT con Google Cloud (API REST + SPEECH_API_KEY)
# --------------------------
def call_minimax_stt(audio_file):
    """Transcribe audio usando Google Speech-to-Text REST API.
    
    Corregido para soportar múltiples formatos de audio desde React Native.
    """
    
    if not SPEECH_API_KEY:
        print("⚠️ Falta SPEECH_API_KEY en variables de entorno")
        return None

    try:
        # Leer contenido del archivo
        audio_bytes = audio_file.read()
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        
        # Obtener el nombre del archivo para detectar formato
        filename = audio_file.filename.lower() if audio_file.filename else ""
        
        # Determinar encoding basado en extensión
        encoding = "LINEAR16"  # Default para WAV
        sample_rate = 44100    # Default común
        
        if filename.endswith('.mp3'):
            encoding = "MP3"
        elif filename.endswith('.m4a') or filename.endswith('.aac'):
            encoding = "AMR_WB"  # O usar MP3 como fallback
        elif filename.endswith('.wav'):
            encoding = "LINEAR16"
        elif filename.endswith('.webm'):
            encoding = "WEBM_OPUS"
        else:
            # Intentar detectar por los primeros bytes (magic numbers)
            if audio_bytes.startswith(b'RIFF'):
                encoding = "LINEAR16"  # WAV
            elif audio_bytes.startswith(b'\xff\xfb') or audio_bytes.startswith(b'ID3'):
                encoding = "MP3"
            else:
                # Fallback: intentar LINEAR16
                encoding = "LINEAR16"
        
        print(f"🎤 Procesando audio: {filename or 'sin-nombre'}")
        print(f"📊 Encoding detectado: {encoding}")
        print(f"📏 Tamaño: {len(audio_bytes)} bytes")

        url = f"https://speech.googleapis.com/v1/speech:recognize?key={SPEECH_API_KEY}"

        payload = {
            "config": {
                "encoding": encoding,
                "sampleRateHertz": sample_rate,
                "languageCode": "es-PE",
                "enableAutomaticPunctuation": True,
                "model": "default",  # o "command_and_search" para mejor reconocimiento
            },
            "audio": {
                "content": audio_base64,
            },
        }

        resp = requests.post(url, json=payload, timeout=30)
        
        if resp.status_code != 200:
            print(f"❌ Error STT HTTP {resp.status_code}")
            print(f"📄 Response: {resp.text[:500]}")
            
            # Si falla, intentar sin especificar sample rate
            if "sampleRateHertz" in payload["config"]:
                print("🔄 Reintentando sin sampleRateHertz...")
                del payload["config"]["sampleRateHertz"]
                resp = requests.post(url, json=payload, timeout=30)
                
                if resp.status_code != 200:
                    print(f"❌ Error en reintento: {resp.status_code} - {resp.text[:300]}")
                    return None

        data = resp.json()
        results = data.get("results", [])
        
        if not results:
            print("⚠️ Sin resultados de transcripción (audio vacío o inaudible)")
            return ""

        transcript = results[0].get("alternatives", [{}])[0].get("transcript", "")
        confidence = results[0].get("alternatives", [{}])[0].get("confidence", 0)
        
        print(f"✅ Transcrito: '{transcript}' (confianza: {confidence:.2f})")
        return transcript
        
    except requests.exceptions.Timeout:
        print("⏱️ Timeout en Google STT - el audio puede ser muy largo")
        return None
    except Exception as e:
        print(f"❌ Error en Google STT: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
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
