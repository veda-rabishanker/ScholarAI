from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import logging
import os
import json
import re
import datetime as dt
from collections import Counter
from typing import Any, Dict, List

import openai
from flask import Flask, jsonify, render_template, request, session
from flask_session import Session

from services.youtube import search_videos


app = Flask(__name__)

# --------------------- Configuration ---------------------

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


app.logger.setLevel(logging.DEBUG)


# put api key here 
openai.api_key = os.getenv("OPENAI_API_KEY")
# --------------------- Helper Functions ---------------------

_STOP = {
    "the","and","of","to","in","a","for","on","is","are","with","that",
    "this","an","as","at","by","be","from","has","have","it","its","was",
    "were","can","could","will","would","should","into","their","they",
    "them","but","or","if","also","than"
}

def _keyword_fallback(summary: str, max_q: int = 3) -> list[str]:
    """
    Very simple keyword extractor → returns up to *max_q* short
    search queries when the LLM gives us nothing.
    """
    words  = re.findall(r"[A-Za-z]{4,}", summary.lower())
    counts = Counter(w for w in words if w not in _STOP)
    top    = [w for w, _ in counts.most_common(6)]           
    if not top:
        return []
    # Turn keywords into “explain <keyword>” queries
    queries = [f"explain {w}" for w in top[:max_q]]
    return queries


def _read_prompt_template(template_path: str) -> str:
    """
    Read a prompt template file, guaranteeing the directory exists.
    """
    os.makedirs(os.path.dirname(template_path), exist_ok=True)
    if not os.path.exists(template_path):
        # create an empty template stub so devs notice
        with open(template_path, "w") as f:
            f.write("# prompt template placeholder\n")
    with open(template_path, "r") as f:
        return f.read()


def _safe_json_loads(text: str):
    """
    Attempt to parse a JSON string, returning None if it fails.
    """
    try:
        return json.loads(text)
    except Exception:
        return None


def _parse_queries_from_text(text: str) -> list[str]:
    """
    Strip a plain‑text GPT reply down to distinct search phrases.

    • Removes code‑fences, brackets, quotes, bullets, numbers, commas.
    • Keeps first five unique, non‑blank lines (case‑insensitive).
    """
    text = re.sub(r"```.*?```", "", text, flags=re.S)            # drop ```…```
    text = re.sub(r"[\[\]\"]", "", text)                         # drop [] and "
    raw  = [re.sub(r"^[\s•\-\d\)\.]*", "", ln).strip(" ,")
            for ln in text.splitlines()]
    seen, queries = set(), []
    for ln in raw:
        low = ln.lower()
        if ln and low not in seen:
            seen.add(low)
            queries.append(ln)
        if len(queries) == 5:
            break
    return queries


def _strip_code_fence(text: str) -> str:
    return re.sub(r"^\s*```[\w-]*\s*|\s*```\s*$", "", text, flags=re.S)

def _normalize_quotes(text: str) -> str:
    for bad, good in {"“":'"', "”":'"', "‘":'"', "’":'"'}.items():
        text = text.replace(bad, good)
    return text
# --------------------- Routes ---------------------


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/diagnostic")
def diagnostic():
    # Renders the page where users can generate and answer a 10-question diagnostic
    return render_template("diagnostic.html")


@app.route("/results")
def results():
    # Diagnostic results
    diagnostic_analysis = session.get("latest_diagnostic_analysis", "")
    test_questions = session.get("latest_diagnostic_test", "")
    test_answers = session.get("latest_test_answers", {})

    # Learning style results
    learning_style_scores = session.get("learning_style_scores", {})
    learning_interpretation = session.get("learning_style_interpretation", "")
    primary_style = session.get("primary_learning_style", "")

    return render_template(
        "results.html",
        diagnostic_analysis=diagnostic_analysis,
        test_questions=test_questions,
        test_answers=test_answers,
        learning_scores=learning_style_scores,
        learning_interpretation=learning_interpretation,
        primary_style=primary_style,
    )


@app.route("/check_diagnostic_status", methods=["GET"])
def check_diagnostic_status():
    """Check if user has completed a diagnostic test"""
    has_diagnostic = "latest_test_answers" in session and session["latest_test_answers"]
    return jsonify({"has_diagnostic": bool(has_diagnostic)})


@app.route("/check_learning_style_status", methods=["GET"])
def check_learning_style_status():
    """Check if user has completed the learning style assessment"""
    has_learning_style = (
        "primary_learning_style" in session and session["primary_learning_style"]
    )
    learning_style = session.get("primary_learning_style", "")
    return jsonify(
        {"has_learning_style": bool(has_learning_style), "learning_style": learning_style}
    )


@app.route("/get_user_profile", methods=["GET"])
def get_user_profile():
    """
    Provide the front‑end with a lightweight learner profile
    consisting of diagnostic summary and primary learning style.
    """
    diagnostic_summary = session.get("latest_diagnostic_analysis", "")
    learning_style = session.get("primary_learning_style", "")
    return jsonify(
        {
            "diagnostic_summary": diagnostic_summary,
            "learning_style": learning_style,
        }
    )


@app.route("/submit_learning_style", methods=["POST"])
def submit_learning_style():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data received"}), 400

    try:
        # Store raw scores
        session["learning_style_scores"] = {
            "visual": data.get("visual", 0),
            "auditory": data.get("auditory", 0),
            "reading_writing": data.get("reading_writing", 0),
            "kinesthetic": data.get("kinesthetic", 0),
        }

        # Determine primary learning style
        max_score = max(session["learning_style_scores"].values())
        primary_style = [
            k for k, v in session["learning_style_scores"].items() if v == max_score
        ][0]

        # Generate a detailed interpretation
        interpretation_prompt = (
            f"Student's learning style scores:\n"
            f"Visual: {session['learning_style_scores']['visual']}\n"
            f"Auditory: {session['learning_style_scores']['auditory']}\n"
            f"Reading/Writing: {session['learning_style_scores']['reading_writing']}\n"
            f"Kinesthetic: {session['learning_style_scores']['kinesthetic']}\n\n"
            f"The primary learning style is {primary_style}.\n"
            "Provide a 3-4 paragraph interpretation of these results, including:\n"
            "1. What this learning style means\n"
            "2. Study strategies that would be effective\n"
            "3. Potential challenges and how to overcome them\n"
            "Use simple, clear language suitable for students."
        )

        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": interpretation_prompt}],
            temperature=0.7,
            max_tokens=500,
        )

        if response.choices:
            session["learning_style_interpretation"] = (
                response.choices[0].message.content
            )
            session["primary_learning_style"] = primary_style
        else:
            session["learning_style_interpretation"] = "Interpretation unavailable"

        return jsonify(
            {
                "status": "success",
                "primary_style": primary_style,
                "interpretation": session["learning_style_interpretation"],
            }
        )

    except Exception as e:
        app.logger.error(f"Error processing learning style: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/chatbot")
def chatbot_page():
    # Renders the chatbot page where users can ask questions
    return render_template("chatbot.html")


@app.route("/learning_style")
def learning_style():
    # Renders the page for the VARK learning style assessment
    return render_template("learning_styles.html")


@app.route("/schedule")
def schedule():
    # Renders the weekly schedule/planner
    return render_template("schedule.html")


# ---------------- Study Planner (AI calendar) endpoints -----------------

@app.route("/generate_study_plan", methods=["POST"])
def generate_study_plan():
    """
    Wizard payload → GPT‑4o → strict JSON study plan.
    Returns { "study_plan": [ …session objects… ] }.
    """
    data = request.get_json(silent=True) or {}

    # ---------- 1) Context pulled from session + payload -------------
    subject      = session.get("latest_diagnostic_subject", "General Studies")
    topic        = session.get("latest_diagnostic_topic",   subject)
    grade_level  = session.get("latest_diagnostic_grade",   "Unknown")
    diagnostic_test_text = session.get("latest_diagnostic_test", "")
    test_answers = session.get("latest_test_answers", {})
    diagnostic_summary = data.get("diagnostic_summary") \
        or session.get("latest_diagnostic_analysis", "")
    learning_style = data.get("learning_style") \
        or session.get("primary_learning_style", "")
    today = dt.date.today().isoformat()

    # ---------- 2) Build prompt  ------------------------------------
    # 2‑a.  Load your narrative template
    template_path = "topic_prompts/study_plan_prompt.txt"
    template_body = _read_prompt_template(template_path)
    prompt_body = template_body.format(
        subject=subject,
        topic=topic,
        grade_level=grade_level,
        diagnostic_test=(diagnostic_test_text[:800] or "[not available]"),
        student_answers=(chr(10).join(f"{k}: {v}" for k, v in test_answers.items())[:800]
                         or "[not available]"),
        diagnostic_summary=diagnostic_summary,
        learning_style=learning_style,
        study_goals=data.get("study_goals", ""),
        deadlines_json=json.dumps(data.get("deadlines_json", [])),
        busy_json=json.dumps(data.get("busy_json", {})),
        free_json=json.dumps(data.get("free_json", {})),
        json_rules="" 
    )

    # 2‑b.  Append the strict schema block
    schema_block = f"""
STRUCTURE REQUIREMENTS
Return **ONLY** valid JSON — no markdown fences, no commentary.
Top‑level key "plan" → array of session objects.

Each session object must have exactly:
  "date"        : "YYYY‑MM‑DD"  (≥ {today})
  "start"       : "HH:MM"       (24‑h)
  "end"         : "HH:MM"       (24‑h)
  "focus_topic" : string  (≤80 chars)
  "approach"    : string  (1 concise sentence)
  "tasks"       : array [2‑4] of strings (each ≤120 chars)

Mini‑example:
{{
  "plan":[{{
    "date":"{today}",
    "start":"17:00",
    "end":"18:00",
    "focus_topic":"Solving linear equations",
    "approach":"Walk through examples aloud with colour‑coded steps.",
    "tasks":[
      "Watch youtu.be/abc123 (5 min)",
      "Solve 4 practice problems",
      "Summarise the steps in your own words"
    ]
  }}]
}}

Formatting rules:
• Use straight quotes " " (no curly quotes).  
• If you wrap, wrap exactly as shown above.
""".strip()

    prompt = prompt_body + "\n\n" + schema_block

    # ---------- 3) Call GPT‑4o --------------------------------------
    try:
        app.logger.info("=== Generating Study Plan (JSON) ===")
        resp = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are Scholar AI Planner. Output JSON only."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.35,
            max_tokens=1600,
        )
        if not resp.choices:
            raise RuntimeError("OpenAI returned no choices")

        raw = resp.choices[0].message.content.strip()
        app.logger.debug("LLM raw (first 400 chars): %s", raw[:400])

        # ---------- 4) Clean → Parse → Validate ----------------------
        clean  = _normalize_quotes(_strip_code_fence(raw))
        parsed = _safe_json_loads(clean)
        if parsed is None:
            raise ValueError("Cannot parse JSON (see debug log)")

        raw_list = parsed["plan"] if isinstance(parsed, dict) and "plan" in parsed else parsed
        if not isinstance(raw_list, list):
            raise ValueError('Top‑level JSON must be list or {"plan":[…]}')

        req = {"date","start","end","focus_topic","approach","tasks"}
        sessions = [s for s in raw_list
                    if isinstance(s, dict) and set(s.keys()) == req
                    and isinstance(s["tasks"], list)]

        if not sessions:
            raise ValueError("No fully‑conforming session objects found")

        app.logger.info("✔ Parsed %d sessions", len(sessions))

        # ---------- 5) Cache & Return -------------------------------
        session["latest_study_plan"] = sessions
        return jsonify({"study_plan": sessions})

    except Exception as e:
        app.logger.exception("Study‑plan generation failed")
        return jsonify({"error": str(e)}), 500


# ---------------- diagnostic & chat endpoints -----------------


@app.route("/generate_test", methods=["POST"])
def generate_test():
    """
    Create a 10‑question diagnostic test and remember its meta‑data.
    """
    data         = request.get_json() or {}
    subject      = data.get("subject", "General")
    grade_level  = data.get("grade_level", "Unknown")
    topic        = data.get("topic", subject)   # fallback to subject if blank

    # 💾  keep meta‑data so /submit_test can use it
    session["latest_diagnostic_subject"] = subject
    session["latest_diagnostic_grade"]   = grade_level
    session["latest_diagnostic_topic"]   = topic

    system_prompt = (
        "You are an expert curriculum developer. "
        "Create a 10‑question diagnostic test mixing multiple‑choice (A–D) and short free‑response questions. "
        "Format each question on a new line."
    )

    user_prompt = (
        f"Subject: {subject}\n"
        f"Grade Level: {grade_level}\n"
        f"Topic: {topic}\n\n"
        "Generate exactly 10 diagnostic questions."
    )

    try:
        app.logger.info("=== Generating Diagnostic Test ===")
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=1000,
        )

        diagnostic_test_text = (
            response.choices[0].message.content.strip()
            if response.choices else "[No content returned by OpenAI]"
        )
        session["latest_diagnostic_test"] = diagnostic_test_text
        return jsonify({"diagnostic_test": diagnostic_test_text})

    except Exception as e:
        app.logger.error(f"Error generating test: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/submit_test", methods=["POST"])
def submit_test():
    """
    Save the student’s answers, ask GPT‑4 o for a concise strengths/weaknesses
    summary that STARTS with the topic + grade level.
    """
    answers: Dict[str, str] = request.get_json() or {}
    session["latest_test_answers"] = answers

    # clear any previous summary so the UI won’t show stale text
    session["latest_diagnostic_analysis"] = "(pending)"
    session.modified = True

    diagnostic_test_text: str = session.get("latest_diagnostic_test", "")

    # --------------- fetch meta‑data we saved earlier -----------------
    topic       = session.get("latest_diagnostic_topic",   "General")
    grade_level = session.get("latest_diagnostic_grade",   "Unknown")
    subject     = session.get("latest_diagnostic_subject", "General")

    # ---------------- build prompt -----------------------------------
    summary_prompt = (
        "You are an expert tutor analysing a diagnostic test.\n\n"
        f"Test topic      : {topic}\n"
        f"Grade level     : {grade_level}\n"
        f"Subject category: {subject}\n\n"
        "Below is the test followed by the student’s answers.  "
        "Write **only** a concise 3‑4 sentence summary describing:\n"
        " • the student’s strengths\n"
        " • their weaknesses / misconceptions\n"
        " • what topics they should focus on next\n\n"
        "FIRST line **must** be exactly:\n"
        f"{topic} diagnostic (grade {grade_level}) summary:\n\n"
        "Do **NOT** reproduce the questions, answers, or any ✔️/✖️ list.\n\n"
        "=== Diagnostic Test ===\n"
        f"{diagnostic_test_text}\n\n"
        "=== Student Answers ===\n" +
        "\n".join(f"{k}: {v}" for k, v in answers.items())
    )

    app.logger.info("▶ GPT summary prompt is %d chars", len(summary_prompt))

    try:
        resp = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.5,
            max_tokens=400,
        )
        summary_text = (
            resp.choices[0].message.content.strip()
            if resp.choices else
            f"{topic} diagnostic (grade {grade_level}) summary:\n"
            "Diagnostic summary unavailable – no content returned by OpenAI."
        )
    except Exception as exc:
        app.logger.error("Diagnostic summary generation failed: %s", exc)
        summary_text = (
            f"{topic} diagnostic (grade {grade_level}) summary:\n"
            "Diagnostic summary unavailable due to an error."
        )

    # store whatever we got so the Results page can display it
    session["latest_diagnostic_analysis"] = summary_text
    app.logger.info("☑️  latest_diagnostic_analysis set (first 120 chars): %s",
                    summary_text[:120])

    return jsonify({"status": "ok"})




@app.route("/chat", methods=["POST"])
def chat():
    """
    Primary chatbot endpoint. Sends diagnostic context + learning style
    plus conversation to the LLM, then returns the reply.
    """
    data = request.json or {}
    user_message = data.get("message", "")
    subject = data.get("subject", "General Knowledge")

    if "conversation" not in session:
        session["conversation"] = []

    if user_message:
        session["conversation"].append({"role": "user", "content": user_message})

    diagnostic_test_text = session.get("latest_diagnostic_test", "")
    test_answers = session.get("latest_test_answers", {})
    primary_learning_style = session.get("primary_learning_style", "")
    learning_style_scores = session.get("learning_style_scores", {})

    # ---------------- build system message ----------------
    text_file_path = "topic_prompts/initial_prompt.txt"
    os.makedirs(os.path.dirname(text_file_path), exist_ok=True)
    if not os.path.exists(text_file_path):
        with open(text_file_path, "w") as file:
            file.write(
                "You are Scholar AI, an intelligent tutoring assistant. "
                "Evaluate the student's diagnostic test answers below, identify correctness or mistakes, "
                "and provide detailed feedback and next steps.\n"
            )

    with open(text_file_path, "r") as file:
        initial_prompt = file.read()

    system_content = (
        initial_prompt + f"\n\nStudent has chosen the subject: {subject}\n\n"
        "IMPORTANT: When a user first messages you or asks for help studying, "
        "DO NOT ask generic questions about what subject they want to study. "
        "Instead, immediately use the diagnostic test results and learning style information "
        "provided below to offer personalized guidance. Assume they want help with the "
        "material covered in their diagnostic test unless they specifically ask for something else.\n\n"
    )

    if diagnostic_test_text and test_answers:
        system_content += "=== Diagnostic Test ===\n"
        system_content += diagnostic_test_text + "\n\n"
        system_content += "=== Student's Answers ===\n"
        for key, val in test_answers.items():
            system_content += f"{key}: {val}\n"
        system_content += "\n"

    if primary_learning_style:
        system_content += "=== Student's Learning Style ===\n"
        system_content += f"Primary Learning Style: {primary_learning_style}\n"
        if learning_style_scores:
            system_content += "Scores:\n"
            for style, score in learning_style_scores.items():
                system_content += f"- {style}: {score}\n"
        system_content += "\n"

        if primary_learning_style == "visual":
            system_content += (
                "- Use diagrams, charts, and images in explanations\n"
                "- Suggest visual study aids like mind maps and color coding\n"
                "- Describe concepts with visual metaphors and spatial relationships\n"
            )
        elif primary_learning_style == "auditory":
            system_content += (
                "- Explain concepts as if speaking them aloud\n"
                "- Suggest verbal repetition and discussion-based learning\n"
                "- Recommend audio recordings and verbal mnemonics\n"
            )
        elif primary_learning_style == "reading_writing":
            system_content += (
                "- Structure information in written format with lists and paragraphs\n"
                "- Suggest note-taking and written summaries as study techniques\n"
                "- Emphasize the importance of text-based learning resources\n"
            )
        elif primary_learning_style == "kinesthetic":
            system_content += (
                "- Relate concepts to physical experiences and real-world applications\n"
                "- Suggest hands-on activities and practice-based learning\n"
                "- Recommend movement and physical interaction while studying\n"
            )

    if diagnostic_test_text and test_answers:
        system_content += (
            "ALWAYS start by analyzing the diagnostic test results when the conversation begins "
            "or when the user asks for help studying. Evaluate these answers for correctness, "
            "identify which ones are wrong, explain the correct solutions, and offer "
            "next steps or study tips tailored to their learning style.\n"
        )

    system_content += "If the user has other questions, do your best to help using the context.\n"

    messages = [{"role": "system", "content": system_content}] + session["conversation"]

    app.logger.info("=== Chat Endpoint Called ===")
    app.logger.info(f"System message length: {len(system_content)} characters")

    try:
        if len(session["conversation"]) <= 1 and diagnostic_test_text and test_answers:
            first_time_instruction = {
                "role": "user",
                "content": "Please analyze my diagnostic test results and provide feedback.",
            }
            messages.insert(1, first_time_instruction)

        response = openai.chat.completions.create(
            model="gpt-4o", messages=messages, temperature=0.7
        )

        if not response.choices:
            app.logger.error("No choices returned from OpenAI in chat")
            gpt_response = "[No content returned by OpenAI]"
        else:
            raw_content = response.choices[0].message.content or ""
            gpt_response = raw_content.strip()

        session["conversation"].append({"role": "assistant", "content": gpt_response})

        app.logger.info("=== OpenAI Chat Response ===")
        app.logger.info(gpt_response)

        return jsonify({"response": gpt_response})

    except Exception as e:
        app.logger.error(f"An error occurred in /chat: {e}")
        return jsonify({"error": str(e)}), 500


# ---------------- Utilities ----------------


@app.route("/clear_session", methods=["GET"])
def clear_session():
    """
    Simple endpoint to clear the session for a fresh start.
    """
    session.clear()
    return jsonify({"status": "session cleared"})


@app.route("/clear_conversation", methods=["POST"])
def clear_conversation():
    """
    Clear only the conversation history but keep diagnostic and learning style data
    """
    session["conversation"] = []
    return jsonify({"status": "conversation cleared, data preserved"})

@app.route("/recommend_videos", methods=["POST"])
def recommend_videos():
    """
    Build YouTube recommendations from the diagnostic summary.
    """
    payload = request.get_json(silent=True) or {}

    diagnostic_summary = (
        payload.get("diagnostic_summary")
        or session.get("latest_diagnostic_analysis", "")
    )
    learning_style = (
        payload.get("learning_style")
        or session.get("primary_learning_style", "")
    )
    grade_level = (
        payload.get("grade_level")
        or session.get("latest_diagnostic_grade", "Unknown")
    )

    # No context yet?  Front‑end will show a placeholder.
    if not diagnostic_summary:
        return jsonify({"videos": []})

    # ---------- 1)  LLM → search queries -------------------------------
    prompt_template = _read_prompt_template("topic_prompts/video_topic_prompt.txt")
    user_prompt     = prompt_template.format(
        weak_areas      = diagnostic_summary.strip(),
        overall_subject = "General curriculum",
        learning_style  = learning_style or "unspecified",
        grade_level     = grade_level,
    )

    system_msg = (
        "You are Scholar AI Curator for an educational web app.\n"
        "Context: the user just completed a diagnostic test; your job is to "
        "propose YouTube search queries that will surface *instructional videos* "
        "to help them with their weakest areas.\n\n"
        "Guidelines for your output:\n"
        "• Produce **exactly 3‑5 lines**.\n"
        "• EACH line must end with the phrase “for grade {grade}”.\n"
        "  Example:   multiplying fractions visually **for grade {grade}**\n"
        "• Reflect the diagnostic summary and (if supplied) the learner’s primary "
        "learning style (e.g. use words like “visual explanation” for visual learners).\n"
        "• DO NOT include JSON, quotes, bullets, numbers, brackets, code‑fences, "
        "intro text, or outro comments—just the bare lines.\n"
        
    ).format(grade=grade_level)

    try:
        app.logger.info("=== Generating search queries for videos ===")
        resp = openai.chat.completions.create(
            model    = "gpt-4o",
            messages = [
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_prompt},
            ],
            temperature = 0.4,
            max_tokens  = 120,
        )
        raw     = resp.choices[0].message.content if resp.choices else ""
        queries = _parse_queries_from_text(raw)    # <-- unchanged helper you already have
        app.logger.info("‣ GPT search queries → %s", queries)
    except Exception as exc:
        app.logger.error("LLM failed: %s", exc)
        queries = []

    # ---------- 2)  Fallback if GPT came back empty --------------------
    if not queries:
        queries = [f"{q} for grade {grade_level}"
                   for q in _keyword_fallback(diagnostic_summary)]
        app.logger.info("⚠️  Using keyword‑fallback queries → %s", queries)

    # ---------- 3)  YouTube search ------------------------------------
    videos, seen = [], set()
    for q in queries:
        for vid in search_videos(q, max_results=5):
            if vid["video_id"] in seen:
                continue
            seen.add(vid["video_id"])
            videos.append(vid)
            if len(videos) >= 3:
                break
        if len(videos) >= 3:
            break

    app.logger.info("Videos selected: %s", [v['title'] for v in videos])
    return jsonify({"videos": videos})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
