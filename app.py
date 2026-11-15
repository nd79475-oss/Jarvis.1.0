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

MODEL = "claude-sonnet-5-5"


def ask(msgs, system, web):
    kw = dict(model=MODEL, max_tokens=700 if web else 300, system=system, messages=msgs)
    if web:
        kw["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]
    r = None
    for _ in range(3):
        r = client.messages.create(**kw)
        if getattr(r, "stop_reason", "") == "pause_turn":
            kw["messages"] = kw["messages"] + [{"role": "assistant", "content": r.content}]
            continue
        break
    return r


def parse(r):
    parts = []
    for b in r.content:
        if getattr(b, "type", "") == "web_search_tool_result":
            parts = []  # drop the "let me search" filler before the results
        elif getattr(b, "type", "") == "text":
            parts.append(b.text)
    text = " ".join(parts).strip()
    src, seen = [], set()
    for b in r.content:
        if getattr(b, "type", "") == "web_search_tool_result" and isinstance(getattr(b, "content", None), list):
            for it in b.content:
                u = getattr(it, "url", "") or ""
                if u.startswith("http") and u not in seen and len(src) < 4:
                    seen.add(u)
                    src.append({"title": getattr(it, "title", u), "url": u})
    return text, src


@app.post("/chat")
def chat():
    data = request.get_json(force=True)
    msgs = data.get("messages", [])[-10:]
    memory = "; ".join(data.get("memory", [])) or "none"
    web = bool(data.get("web"))
    system = ("You are JARVIS, a concise, witty voice assistant. "
              "Reply in 1-3 short sentences. Known facts about the user: " + memory)
    try:
        if web:
            try:
                r = ask(msgs, system + " Use web search for current facts. Answer in 2-4 short sentences and name your sources.", True)
                text, src = parse(r)
                if text:
                    return jsonify(text=text, sources=src)
            except Exception:
                r = ask(msgs, system, False)
                note = "(Live web search isn't available right now, so this is from my own knowledge.) "
                return jsonify(text=note + parse(r)[0], sources=[])
        r = ask(msgs, system, False)
        return jsonify(text=parse(r)[0], sources=[])
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
    
