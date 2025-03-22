import logging
from flask import Flask, render_template, request, jsonify, session
from flask_session import Session
import openai
import os

app = Flask(__name__)

# --------------------- Configuration ---------------------

# Session configuration
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Force the logger to show INFO level messages
app.logger.setLevel(logging.INFO)



# --------------------- Routes ---------------------

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/diagnostic')
def diagnostic():
    # Renders the page where users can generate and answer a 10-question diagnostic
    return render_template('diagnostic.html')


@app.route('/chatbot')
def chatbot_page():
    # Renders the chatbot page where users can ask questions
    return render_template('chatbot.html')


@app.route('/learning_style')
def learning_style():
    # Renders the page for the VARK learning style assessment
    return render_template('learning_styles.html')


@app.route('/schedule')
def schedule():
    # Renders the weekly schedule/planner
    return render_template('schedule.html')


@app.route('/generate_test', methods=['POST'])
def generate_test():
    """
    Generate a 10-question diagnostic test based on user input:
      - subject
      - grade_level
      - topic
    Store the generated test in session so we can reference it later.
    """
    data = request.get_json() or {}
    subject = data.get('subject', 'General')
    grade_level = data.get('grade_level', 'Unknown')
    topic = data.get('topic', '')

    # A specialized system prompt for generating a test
    system_prompt = (
        "You are an expert curriculum developer. "
        "You will create a 10-question diagnostic test for a student, given the subject, grade level, and topic. "
        "Use a mixture of multiple-choice (with A-D) and short free-response questions. "
        "Format each question on a new line."
    )

    # The user's request to generate the test
    user_prompt = (
        f"Subject: {subject}\n"
        f"Grade Level: {grade_level}\n"
        f"Topic: {topic}\n\n"
        "Please create exactly 10 diagnostic questions. At least half should be multiple choice "
        "with (A), (B), (C), and (D), and the rest can be short free-response questions. "
        "Use line breaks to separate each question."
    )

    try:
        app.logger.info("=== Generating Diagnostic Test ===")
        app.logger.info(f"System Prompt:\n{system_prompt}")
        app.logger.info(f"User Prompt:\n{user_prompt}")

        # Call the OpenAI API
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        # Log the entire raw response for debugging
        app.logger.info(f"Raw OpenAI response (generate_test):\n{response}")

        # Safely retrieve the content
        if not response.choices:
            app.logger.error("No choices returned from OpenAI in generate_test")
            diagnostic_test_text = "[No content returned by OpenAI]"
        else:
            raw_content = response.choices[0].message.content or ""
            diagnostic_test_text = raw_content.strip()

        # Store the generated test in session
        session['latest_diagnostic_test'] = diagnostic_test_text

        app.logger.info("=== Diagnostic Test Generated ===")
        app.logger.info(diagnostic_test_text)

        return jsonify({"diagnostic_test": diagnostic_test_text})

    except Exception as e:
        app.logger.error(f"Error generating test: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/submit_test', methods=['POST'])
def submit_test():
    """
    Receive the student's answers for the 10-question test.
    Store them in session so we can reference them in the chat.
    """
    answers = request.get_json() or {}
    session['latest_test_answers'] = answers

    app.logger.info("=== Diagnostic Test Answers Submitted ===")
    app.logger.info(answers)

    return jsonify({"status": "ok"})


@app.route('/chat', methods=['POST'])
def chat():
    """
    Primary chatbot endpoint. Sends all context (test + answers) plus conversation 
    to the OpenAI model. Then returns the model's reply.
    """
    data = request.json or {}
    user_message = data.get('message', '')
    subject = data.get('subject', 'General Knowledge')

    # Retrieve the stored diagnostic test and answers
    diagnostic_test_text = session.get('latest_diagnostic_test', '')
    test_answers = session.get('latest_test_answers', {})

    # Retrieve or create conversation history
    if 'conversation' not in session:
        session['conversation'] = []

    # If there's a new user message, add it
    if user_message:
        session['conversation'].append({"role": "user", "content": user_message})

    # We maintain an external prompt file for the base instructions
    text_file_path = 'topic_prompts/initial_prompt.txt'
    os.makedirs(os.path.dirname(text_file_path), exist_ok=True)

    # If the prompt file doesn't exist, create a minimal prompt
    if not os.path.exists(text_file_path):
        with open(text_file_path, 'w') as file:
            file.write(
                "You are Scholar AI, an intelligent tutoring assistant. "
                "Evaluate the student's diagnostic test answers below, identify correctness or mistakes, "
                "and provide detailed feedback and next steps.\n"
            )

    # We append the chosen subject for logging or reference
    with open(text_file_path, 'a') as file:
        file.write(f"\nStudent has chosen the subject: {subject}\n")

    # Now read the entire prompt from file
    with open(text_file_path, 'r') as file:
        initial_prompt = file.read()

    # Build context about the test & answers:
    # Instruct the AI to evaluate them if the user asks about their performance
    background_info = (
        "You are Scholar AI, an adaptive tutor. "
        "The user has completed a 10-question diagnostic test. "
        "Below is the test and the user’s answers:\n\n"
    )
    if diagnostic_test_text:
        background_info += "=== Diagnostic Test ===\n"
        background_info += diagnostic_test_text + "\n\n"
    if test_answers:
        background_info += "=== Student's Answers ===\n"
        for key, val in test_answers.items():
            background_info += f"{key}: {val}\n"
        background_info += "\n"
    background_info += (
        "Please evaluate these answers for correctness, identify which ones are wrong, "
        "explain the correct solutions, and offer any next steps or study tips. "
        "If the user asks about their performance, provide a thorough analysis. "
        "If the user has other questions, do your best to help using the context.\n"
    )

    # Combine the initial prompt + background info as a single system message
    system_content = initial_prompt.strip() + "\n\n" + background_info.strip()

    # Construct messages for the model
    messages = [
        {"role": "system", "content": system_content}
    ] + session['conversation']

    app.logger.info("=== Chat Endpoint Called ===")
    app.logger.info("Messages being sent to OpenAI:")
    for i, msg in enumerate(messages, start=1):
        role = msg['role'].upper()
        app.logger.info(f"Message {i} ({role}):\n{msg['content']}")

    try:
        # Send the entire conversation to OpenAI
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        # Log the entire raw response
        app.logger.info(f"Raw OpenAI response (chat):\n{response}")

        # Safely extract the AI's reply
        if not response.choices:
            app.logger.error("No choices returned from OpenAI in chat")
            gpt_response = "[No content returned by OpenAI]"
        else:
            raw_content = response.choices[0].message.content or ""
            gpt_response = raw_content.strip()

        # Add the AI's reply to the conversation
        session['conversation'].append({"role": "assistant", "content": gpt_response})

        # Log the final GPT response
        app.logger.info("=== OpenAI Chat Response ===")
        app.logger.info(gpt_response)

        return jsonify({'response': gpt_response})

    except Exception as e:
        app.logger.error(f"An error occurred in /chat: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/clear_session', methods=['GET'])
def clear_session():
    """
    Simple endpoint to clear the session for a fresh start.
    """
    session.clear()
    return jsonify({'status': 'session cleared'})


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080)
