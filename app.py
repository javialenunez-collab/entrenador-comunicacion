import json
import os
import random
import sqlite3
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "entrenador.db")
PROMPTS_PATH = os.path.join(BASE_DIR, "prompts.json")

AI_PROVIDER = os.environ.get("AI_PROVIDER", "groq")  # "groq" (gratis) o "anthropic" (de pago)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

app = Flask(__name__)

with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
    PROMPTS = json.load(f)

CATEGORIA_NOMBRES = {
    "contar": "Contar algo que pasó",
    "explicar": "Explicar una idea",
    "opinar": "Dar tu opinión",
    "describir": "Describir",
    "responder": "Responder rápido",
}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ejercicios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            categoria TEXT NOT NULL,
            consigna TEXT NOT NULL,
            modo TEXT NOT NULL,
            texto_usuario TEXT NOT NULL,
            feedback_json TEXT NOT NULL,
            creado_en TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


SYSTEM_PROMPT = """Sos un coach de comunicación, cálido y paciente. Tu alumno habla español \
rioplatense/paraguayo, usa "vos", y está tratando de mejorar cómo se expresa (hablando y \
escribiendo). A veces el texto que te llega es una transcripción imperfecta de audio (puede \
tener errores de reconocimiento de voz), tené eso en cuenta y no lo juzgues como error de él.

Tu tarea: leer lo que escribió/dijo en respuesta a una consigna, y devolver SOLO un JSON \
válido (sin texto antes ni después, sin bloques de código markdown) con esta forma exacta:

{
  "resumen_breve": "una frase corta y alentadora sobre lo que logró comunicar bien",
  "muletillas": ["lista de muletillas o repeticiones que notaste, puede estar vacía"],
  "palabras_repetidas": ["palabras que repitió mucho y podría variar, puede estar vacía"],
  "reescritura_sugerida": "una versión más clara del mismo mensaje, manteniendo su idea e intención, sin sonar robótica ni demasiado formal",
  "palabras_nuevas": [
    {"en_vez_de": "palabra o frase que usó", "podrias_decir": "alternativa más precisa", "por_que": "explicación breve de 1 línea"}
  ],
  "consejo_practica": "un solo consejo concreto y accionable para la próxima vez"
}

Reglas:
- Máximo 3 elementos en "palabras_nuevas", elegí los más útiles.
- Tono: alentador, nunca condescendiente ni duro. Esto es para alguien que se está animando a practicar.
- Si el texto ya está claro y bien dicho, decilo con sinceridad en "resumen_breve" y dejá "palabras_nuevas" corto o vacío.
- Nunca inventes que dijo algo que no dijo.
"""


def pedir_feedback_ia(consigna, texto_usuario):
    user_content = f"Consigna: {consigna}\n\nRespuesta del alumno:\n{texto_usuario}"

    if AI_PROVIDER == "anthropic":
        texto_respuesta = _llamar_anthropic(user_content)
    else:
        texto_respuesta = _llamar_groq(user_content)

    if texto_respuesta.startswith("```"):
        texto_respuesta = texto_respuesta.strip("`")
        if texto_respuesta.startswith("json"):
            texto_respuesta = texto_respuesta[4:].strip()

    try:
        return json.loads(texto_respuesta)
    except json.JSONDecodeError:
        return {
            "resumen_breve": "No pude leer bien la respuesta de la IA, pero acá está tal cual llegó.",
            "muletillas": [],
            "palabras_repetidas": [],
            "reescritura_sugerida": texto_respuesta,
            "palabras_nuevas": [],
            "consejo_practica": "",
        }


def _llamar_anthropic(user_content):
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "Falta configurar ANTHROPIC_API_KEY en el servidor. Pedile a Javier que la cargue."
        )

    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_content}],
    }

    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "user-agent": "entrenador-comunicacion/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Error de la API de Claude ({e.code}): {detalle}")

    return data["content"][0]["text"].strip()


def _llamar_groq(user_content):
    if not GROQ_API_KEY:
        raise RuntimeError(
            "Falta configurar GROQ_API_KEY en el servidor. Pedile a Javier que la cargue."
        )

    payload = {
        "model": GROQ_MODEL,
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }

    req = urllib.request.Request(
        GROQ_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {GROQ_API_KEY}",
            "user-agent": "entrenador-comunicacion/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Error de la API de Groq ({e.code}): {detalle}")

    return data["choices"][0]["message"]["content"].strip()


@app.route("/")
def index():
    return render_template("index.html", categorias=CATEGORIA_NOMBRES)


@app.route("/api/consigna")
def api_consigna():
    categoria = request.args.get("categoria", "")
    if categoria not in PROMPTS:
        categoria = random.choice(list(PROMPTS.keys()))
    consigna = random.choice(PROMPTS[categoria])
    return jsonify({"categoria": categoria, "consigna": consigna})


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    body = request.get_json(force=True)
    categoria = body.get("categoria", "")
    consigna = body.get("consigna", "")
    texto_usuario = (body.get("texto") or "").strip()
    modo = body.get("modo", "texto")

    if not texto_usuario:
        return jsonify({"error": "No llegó ningún texto para corregir."}), 400

    try:
        feedback = pedir_feedback_ia(consigna, texto_usuario)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    db = get_db()
    ahora = datetime.now().isoformat()
    db.execute(
        """INSERT INTO ejercicios (fecha, categoria, consigna, modo, texto_usuario, feedback_json, creado_en)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            date.today().isoformat(),
            categoria,
            consigna,
            modo,
            texto_usuario,
            json.dumps(feedback, ensure_ascii=False),
            ahora,
        ),
    )
    db.commit()

    return jsonify({"feedback": feedback, "racha": calcular_racha(db)})


@app.route("/api/historial")
def api_historial():
    db = get_db()
    filas = db.execute(
        "SELECT * FROM ejercicios ORDER BY id DESC LIMIT 50"
    ).fetchall()
    resultado = []
    for fila in filas:
        resultado.append(
            {
                "id": fila["id"],
                "fecha": fila["fecha"],
                "categoria": fila["categoria"],
                "consigna": fila["consigna"],
                "modo": fila["modo"],
                "texto_usuario": fila["texto_usuario"],
                "feedback": json.loads(fila["feedback_json"]),
            }
        )
    return jsonify(resultado)


@app.route("/api/racha")
def api_racha():
    db = get_db()
    return jsonify({"racha": calcular_racha(db)})


def calcular_racha(db):
    filas = db.execute(
        "SELECT DISTINCT fecha FROM ejercicios ORDER BY fecha DESC"
    ).fetchall()
    fechas = {fila["fecha"] for fila in filas}
    if not fechas:
        return 0

    racha = 0
    cursor = date.today()
    if cursor.isoformat() not in fechas:
        cursor = cursor - timedelta(days=1)
        if cursor.isoformat() not in fechas:
            return 0

    while cursor.isoformat() in fechas:
        racha += 1
        cursor = cursor - timedelta(days=1)

    return racha


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
