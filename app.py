import os, re, json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic

app = Flask(__name__)
CORS(app)
KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip().strip("'\"")
client = anthropic.Anthropic(api_key=KEY or None)

HERE = os.path.dirname(os.path.abspath(__file__))

@app.get("/")
def home():
    return send_from_directory(HERE, "index.html")

@app.get("/health")
def health():
    if not KEY:
        return "JARVIS backend is running | API key: MISSING (add ANTHROPIC_API_KEY in Render Environment)"
    ok = "looks right" if KEY.startswith("sk-ant-") else "WRONG FORMAT (should start with sk-ant-)"
    return "JARVIS backend is running | API key: found, " + ok + ", length " + str(len(KEY))

@app.post("/chat")
def chat():
    data = request.get_json(force=True)
    msgs = data.get("messages", [])[-10:]
    memory = "; ".join(data.get("memory", [])) or "none"
    system = ("You are JARVIS, a concise, witty voice assistant. "
              "Reply in 1-3 short sentences. Known facts about the user: " + memory)
    try:
        r = client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=300,
            system=system,
            messages=msgs,
        )
        return jsonify(text=r.content[0].text)
    except Exception as e:
        return jsonify(error="Server error: " + str(e)), 500

@app.post("/app")
def app_lookup():
    name = str((request.get_json(force=True) or {}).get("name", ""))[:60]
    try:
        r = client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=120,
            system='You map app names to Android package names. Reply ONLY with JSON like {"package":"com.x.y","web":"https://example.com"}. If unsure, reply {"package":"","web":""}. No other text.',
            messages=[{"role": "user", "content": name}],
        )
        txt = r.content[0].text
        d = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
        pk = d.get("package", "")
        if not re.fullmatch(r"[A-Za-z]\w*(\.\w+)+", pk or ""):
            pk = ""
        web = d.get("web", "")
        if not str(web).startswith("https://"):
            web = ""
        return jsonify(package=pk, web=web)
    except Exception as e:
        return jsonify(package="", web="", error=str(e))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    
