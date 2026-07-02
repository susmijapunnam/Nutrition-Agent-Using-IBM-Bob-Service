"""
app.py — IBM Watsonx.ai Nutrition Agent  (Flask backend)
=========================================================
Run locally:
    pip install -r requirements.txt
    python app.py

Production:
    gunicorn -w 2 -b 0.0.0.0:5000 app:app
"""
from __future__ import annotations
import os, json, traceback
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv

# ── local modules ──────────────────────────────────────────────────────────
from modules.agent_config import build_system_prompt, AGENT_NAME
from modules.nutrition_tools import (
    calculate_bmi,
    calculate_tdee,
    family_calorie_guide,
    estimate_calories,
    ACTIVITY_LABELS,
)

# ── env ────────────────────────────────────────────────────────────────────
load_dotenv()

IBM_API_KEY      = os.getenv("IBM_API_KEY", "")
IBM_WATSONX_URL  = os.getenv("IBM_WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
IBM_PROJECT_ID   = os.getenv("IBM_PROJECT_ID", "")
WATSONX_MODEL_ID = os.getenv("WATSONX_MODEL_ID", "ibm/granite-3-1-8b-base")
FLASK_SECRET     = os.getenv("FLASK_SECRET_KEY", "nutrition-agent-secret")
FLASK_PORT       = int(os.getenv("FLASK_PORT", 5000))

# ── Flask app ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = FLASK_SECRET
CORS(app)

# ── Watsonx client (lazy init) ─────────────────────────────────────────────
_wx_model = None

def get_watsonx_model():
    """Lazily initialise the Watsonx model client using the chat API."""
    global _wx_model
    if _wx_model is not None:
        return _wx_model

    if not IBM_API_KEY or IBM_API_KEY == "your_ibm_cloud_api_key_here":
        return None   # demo mode

    try:
        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference

        credentials = Credentials(
            url     = IBM_WATSONX_URL,
            api_key = IBM_API_KEY,
        )
        _wx_model = ModelInference(
            model_id    = WATSONX_MODEL_ID,
            credentials = credentials,
            project_id  = IBM_PROJECT_ID,
        )
        print(f"[Watsonx] Model ready: {WATSONX_MODEL_ID}")
        return _wx_model
    except Exception as exc:
        print(f"[Watsonx] Init error: {exc}")
        return None


def call_watsonx(user_message: str, user_profile: dict | None = None) -> str:
    """Send a message to Watsonx using the modern chat API."""
    model = get_watsonx_model()
    system_prompt = build_system_prompt(user_profile)

    if model is None:
        return (
            f"👋 Hi! I'm **{AGENT_NAME}** — your AI Nutrition Agent powered by **IBM Watsonx.ai**.\n\n"
            "⚠️ Running in **demo mode** — API key not configured.\n\n"
            f"You asked: *\"{user_message}\"*\n\n"
            "Set `IBM_API_KEY` and `IBM_PROJECT_ID` in `.env` and restart with `python app.py`."
        )

    try:
        # Use the modern chat completions API (replaces deprecated generate_text)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ]
        response = model.chat(
            messages    = messages,
            params      = {
                "max_tokens" : 900,
                "temperature": 0.7,
                "top_p"      : 0.9,
            },
        )
        # Extract text from chat response
        result = response["choices"][0]["message"]["content"]
        return result.strip() if result else "I could not generate a response. Please try again."
    except Exception as exc:
        err_str = str(exc)
        traceback.print_exc()
        if "Inactive" in err_str or "inactive" in err_str:
            return "⚠️ **WML service is Inactive.** Go to cloud.ibm.com → Resources → Reactivate Watson Machine Learning."
        if "401" in err_str or "Unauthorized" in err_str:
            return "⚠️ **Authentication failed.** Check your `IBM_API_KEY` in `.env`."
        if "404" in err_str or "Not Found" in err_str:
            return "⚠️ **Project not found.** Check your `IBM_PROJECT_ID` in `.env`."
        return f"⚠️ Watsonx error: {err_str[:300]}"


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES — Pages
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html", agent_name=AGENT_NAME)


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", agent_name=AGENT_NAME)


@app.route("/meal-planner")
def meal_planner():
    return render_template("meal_planner.html", agent_name=AGENT_NAME)


@app.route("/bmi-calculator")
def bmi_calculator():
    return render_template("bmi_calculator.html", agent_name=AGENT_NAME,
                           activity_labels=ACTIVITY_LABELS)


@app.route("/family-profiles")
def family_profiles():
    return render_template("family_profiles.html", agent_name=AGENT_NAME)


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES — API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Main chat endpoint — proxies to Watsonx."""
    data         = request.get_json(force=True)
    user_message = data.get("message", "").strip()
    user_profile = data.get("profile")   # optional dict from frontend

    if not user_message:
        return jsonify({"error": "Message cannot be empty."}), 400

    # Persist conversation in session (simple turn-based history, last 10)
    history = session.get("chat_history", [])
    history.append({"role": "user", "content": user_message})

    ai_reply = call_watsonx(user_message, user_profile)

    history.append({"role": "assistant", "content": ai_reply})
    session["chat_history"] = history[-20:]   # keep last 20 turns

    return jsonify({"reply": ai_reply, "history": session["chat_history"]})


@app.route("/api/bmi", methods=["POST"])
def api_bmi():
    """Calculate BMI + TDEE."""
    data = request.get_json(force=True)
    try:
        weight = float(data["weight_kg"])
        height = float(data["height_cm"])
        age    = int(data.get("age", 30))
        gender = data.get("gender", "male")
        activity = data.get("activity", "moderately_active")
        goal     = data.get("goal", "maintain")

        bmi_result  = calculate_bmi(weight, height)
        tdee_result = calculate_tdee(weight, height, age, gender, activity, goal)

        return jsonify({"bmi": bmi_result, "tdee": tdee_result})
    except (KeyError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/meal-plan", methods=["POST"])
def api_meal_plan():
    """Generate AI meal plan for a given profile & preferences."""
    data = request.get_json(force=True)
    profile  = data.get("profile", {})
    duration = data.get("duration", "1-day")   # "1-day" or "7-day"
    diet     = data.get("diet_type", "vegetarian")

    prompt = (
        f"Create a detailed {duration} Indian-style {diet} meal plan "
        f"for someone with the following profile: {json.dumps(profile)}. "
        "Include breakfast, lunch, dinner, and 2 snacks for each day. "
        "Provide calorie estimates and brief preparation notes. "
        "Format with clear headings."
    )
    reply = call_watsonx(prompt, profile)
    return jsonify({"meal_plan": reply})


@app.route("/api/family", methods=["POST"])
def api_family():
    """Process family member profiles and return BMI + TDEE for each."""
    data    = request.get_json(force=True)
    members = data.get("members", [])

    if not members:
        return jsonify({"error": "No family members provided."}), 400

    results = family_calorie_guide(members)

    # Also ask AI for a family diet tip
    summary = ", ".join(
        f"{m.get('name','Member')} aged {m.get('age','?')}"
        for m in members
    )
    prompt = (
        f"Our family has these members: {summary}. "
        "Suggest a unified Indian meal plan that suits everyone, "
        "noting any special considerations per age group."
    )
    ai_tip  = call_watsonx(prompt)
    return jsonify({"results": results, "ai_tip": ai_tip})


@app.route("/api/calorie-estimate", methods=["POST"])
def api_calorie_estimate():
    """Quick calorie lookup for a food item."""
    data = request.get_json(force=True)
    food = data.get("food", "")
    qty  = float(data.get("quantity_g", 100))

    local = estimate_calories(food, qty)
    if "error" in local:
        # Fall back to AI
        prompt = (
            f"Estimate the calories and main macros (protein, carbs, fat) "
            f"in {qty}g of {food}. Be concise and use a bullet list."
        )
        ai_reply = call_watsonx(prompt)
        return jsonify({"source": "ai", "estimate": ai_reply})

    return jsonify({"source": "local", "estimate": local})


@app.route("/api/clear-history", methods=["POST"])
def api_clear_history():
    session.pop("chat_history", None)
    return jsonify({"status": "cleared"})


@app.route("/api/status")
def api_status():
    model_ready = (
        bool(IBM_API_KEY) and IBM_API_KEY != "your_ibm_cloud_api_key_here"
    )
    return jsonify({
        "model_id":    WATSONX_MODEL_ID,
        "model_ready": model_ready,
        "demo_mode":   not model_ready,
        "agent_name":  AGENT_NAME,
    })


# ── Entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  {AGENT_NAME} — IBM Watsonx.ai Nutrition Agent")
    print(f"  Model   : {WATSONX_MODEL_ID}")
    print(f"  Mode    : {'LIVE' if (IBM_API_KEY and IBM_API_KEY != 'your_ibm_cloud_api_key_here') else 'DEMO (no API key)'}")
    print(f"  URL     : http://localhost:{FLASK_PORT}")
    print(f"{'='*60}\n")
    app.run(debug=(os.getenv("FLASK_DEBUG", "True") == "True"),
            host="0.0.0.0", port=FLASK_PORT)
