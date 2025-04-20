from __future__ import annotations

import json
import logging
import os
from datetime import datetime
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

# Force the logger to show INFO level messages
app.logger.setLevel(logging.INFO)

# put api key here 
openai.api_key = "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"
# --------------------- Helper Functions ---------------------


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
    Accepts JSON payload from the intake wizard and returns a
    JSON study plan produced by the LLM.
    """
    data = request.get_json() or {}
    try:
        # read & format prompt template
        template_path = "topic_prompts/study_plan_prompt.txt"
        template = _read_prompt_template(template_path)
        filled_prompt = template.format(
            diagnostic_summary=data.get("diagnostic_summary", ""),
            learning_style=data.get("learning_style", ""),
            study_goals=data.get("study_goals", ""),
            deadlines_json=json.dumps(data.get("deadlines_json", [])),
            busy_json=json.dumps(data.get("busy_json", {})),
            free_json=json.dumps(data.get("free_json", {})),
        )

        app.logger.info("=== Generating Study Plan ===")
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are Scholar AI Planner, an expert educational coach.",
                },
                {"role": "user", "content": filled_prompt},
            ],
            temperature=0.5,
            max_tokens=1500,
        )

        if not response.choices:
            raise RuntimeError("No choices returned from OpenAI")

        raw_plan = response.choices[0].message.content.strip()
        parsed_plan = _safe_json_loads(raw_plan) or {"raw": raw_plan}

        # unwrap nested plan if LLM wrapped it
        if isinstance(parsed_plan, dict) and "study_plan" in parsed_plan:
            parsed_plan = parsed_plan["study_plan"]

        # store a copy so user sees it on refresh
        session["latest_study_plan"] = parsed_plan

        return jsonify({"study_plan": parsed_plan})

    except Exception as e:
        app.logger.error(f"Error generating study plan: {e}")
        return jsonify({"error": str(e)}), 500


# ---------------- Existing diagnostic & chat endpoints -----------------


@app.route("/generate_test", methods=["POST"])
def generate_test():
    """
    Generate a 10-question diagnostic test based on user input
    and store it in session for later analysis.
    """
    data = request.get_json() or {}
    subject = data.get("subject", "General")
    grade_level = data.get("grade_level", "Unknown")
    topic = data.get("topic", "")

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
            if response.choices
            else "[No content returned by OpenAI]"
        )
        session["latest_diagnostic_test"] = diagnostic_test_text
        return jsonify({"diagnostic_test": diagnostic_test_text})

    except Exception as e:
        app.logger.error(f"Error generating test: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/submit_test", methods=["POST"])
def submit_test():
    answers = request.get_json() or {}
    session["latest_test_answers"] = answers

    # ① immediately wipe the old summary so nothing stale can leak through
    session["latest_diagnostic_analysis"] = "(pending)"   #  <<< NEW
    session.modified = True                                #  <<< NEW

    diagnostic_test_text = session.get("latest_diagnostic_test", "")
    try:
        if diagnostic_test_text:
            summary_prompt = (
                "Below is a diagnostic test followed by the student's answers.\n"
                "Write a concise 3‑4 sentence summary …"
            )
            resp = openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.5,
                max_tokens=250,
            )
            summary_text = resp.choices[0].message.content.strip() if resp.choices else ""
        else:
            summary_text = "Diagnostic summary unavailable (test text missing)."
    except Exception as e:
        app.logger.error(f"Diagnostic summary generation failed: {e}")
        summary_text = "Diagnostic summary unavailable due to an error."

    # ② always — even on failure — store *something* new
    session["latest_diagnostic_analysis"] = summary_text
    app.logger.info("☑️  latest_diagnostic_analysis set to: %s",
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
    Return a JSON list of recommended videos.

    The payload may include:
        diagnostic_summary – str
        learning_style     – str
    If those are missing we fall back to whatever is in the session.
    """
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    diagnostic_summary: str = (
        payload.get("diagnostic_summary")
        or session.get("latest_diagnostic_analysis", "")
    )
    learning_style: str = (
        payload.get("learning_style")
        or session.get("primary_learning_style", "")
    )

    if not diagnostic_summary:
        # No context → front‑end shows placeholder
        return jsonify({"videos": []})

    # ───────────────── 1.  Build search queries with GPT ──────────────────
    prompt_template = _read_prompt_template("topic_prompts/video_topic_prompt.txt")
    user_prompt = prompt_template.format(
        weak_areas=diagnostic_summary.strip(),
        overall_subject="General curriculum",
    )

    try:
        app.logger.info("=== Generating search queries for videos ===")
        resp = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are Scholar AI Curator."},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=200,
        )
        raw = resp.choices[0].message.content if resp.choices else "[]"
        queries = _safe_json_loads(raw) or []
        if not isinstance(queries, list):
            queries = []
        app.logger.info("‣ GPT search queries → %s", queries)
    except Exception as exc:
        app.logger.error("LLM failed, fallback to generic query: %s", exc)
        queries = []

    # ─────── 2.  Use YouTube API —  ────────
    videos: List[Dict[str, str]] = []
    seen: set[str] = set()

    for q in queries:
        for v in search_videos(q, max_results=5):
            if v["video_id"] in seen:
                continue
            seen.add(v["video_id"])
            videos.append(v)
            if len(videos) >= 8:
                break
        if len(videos) >= 8:
            break

    # If nothing came back, *just* return an empty list – the UI will say so.
    app.logger.info("Videos selected: %s", [v["title"] for v in videos])
    return jsonify({"videos": videos})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
