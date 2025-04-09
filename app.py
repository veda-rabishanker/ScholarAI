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

#put api key here

# --------------------- Routes ---------------------

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/diagnostic')
def diagnostic():
    # Renders the page where users can generate and answer a 10-question diagnostic
    return render_template('diagnostic.html')

@app.route('/results')
def results():
    # Diagnostic results
    diagnostic_analysis = session.get('latest_diagnostic_analysis', '')
    test_questions = session.get('latest_diagnostic_test', '')
    test_answers = session.get('latest_test_answers', {})
    
    # Learning style results
    learning_style_scores = session.get('learning_style_scores', {})
    learning_interpretation = session.get('learning_style_interpretation', '')
    primary_style = session.get('primary_learning_style', '')
    
    return render_template('results.html',
                         diagnostic_analysis=diagnostic_analysis,
                         test_questions=test_questions,
                         test_answers=test_answers,
                         learning_scores=learning_style_scores,
                         learning_interpretation=learning_interpretation,
                         primary_style=primary_style)

@app.route('/check_diagnostic_status', methods=['GET'])
def check_diagnostic_status():
    """Check if user has completed a diagnostic test"""
    has_diagnostic = 'latest_test_answers' in session and session['latest_test_answers']
    return jsonify({"has_diagnostic": has_diagnostic})


@app.route('/check_learning_style_status', methods=['GET'])
def check_learning_style_status():
    """Check if user has completed the learning style assessment"""
    has_learning_style = 'primary_learning_style' in session and session['primary_learning_style']
    learning_style = session.get('primary_learning_style', '')
    return jsonify({
        "has_learning_style": bool(has_learning_style),
        "learning_style": learning_style
    })

@app.route('/submit_learning_style', methods=['POST'])
def submit_learning_style():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data received"}), 400
    
    try:
        # Store raw scores
        session['learning_style_scores'] = {
            'visual': data.get('visual', 0),
            'auditory': data.get('auditory', 0),
            'reading_writing': data.get('reading_writing', 0),
            'kinesthetic': data.get('kinesthetic', 0)
        }
        
        # Determine primary learning style
        max_score = max(session['learning_style_scores'].values())
        primary_style = [k for k, v in session['learning_style_scores'].items() if v == max_score][0]
        
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
            max_tokens=500
        )
        
        if response.choices:
            session['learning_style_interpretation'] = response.choices[0].message.content
            session['primary_learning_style'] = primary_style
        else:
            session['learning_style_interpretation'] = "Interpretation unavailable"
        
        return jsonify({
            "status": "success",
            "primary_style": primary_style,
            "interpretation": session['learning_style_interpretation']
        })
        
    except Exception as e:
        app.logger.error(f"Error processing learning style: {e}")
        return jsonify({"error": str(e)}), 500

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
    Primary chatbot endpoint. Sends all context (test + answers + learning style) plus conversation 
    to the OpenAI model. Then returns the model's reply.
    """
    data = request.json or {}
    user_message = data.get('message', '')
    subject = data.get('subject', 'General Knowledge')

    # Retrieve or create conversation history
    if 'conversation' not in session:
        session['conversation'] = []

    # If there's a new user message, add it
    if user_message:
        session['conversation'].append({"role": "user", "content": user_message})

    # Retrieve the stored diagnostic test and answers
    diagnostic_test_text = session.get('latest_diagnostic_test', '')
    test_answers = session.get('latest_test_answers', {})
    
    # Retrieve learning style information
    primary_learning_style = session.get('primary_learning_style', '')
    learning_style_scores = session.get('learning_style_scores', {})

    # Read the initial prompt file but don't modify it
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

    # Read the file contents but don't append to it
    with open(text_file_path, 'r') as file:
        initial_prompt = file.read()

    # Add current subject context
    system_content = initial_prompt + f"\n\nStudent has chosen the subject: {subject}\n\n"
    
    # Add instructions for automatic context recognition
    system_content += (
        "IMPORTANT: When a user first messages you or asks for help studying, "
        "DO NOT ask generic questions about what subject they want to study. "
        "Instead, immediately use the diagnostic test results and learning style information "
        "provided below to offer personalized guidance. Assume they want help with the "
        "material covered in their diagnostic test unless they specifically ask for something else.\n\n"
    )
    
    # Add diagnostic test information if available
    if diagnostic_test_text and test_answers:
        system_content += "=== Diagnostic Test ===\n"
        system_content += diagnostic_test_text + "\n\n"
        system_content += "=== Student's Answers ===\n"
        for key, val in test_answers.items():
            system_content += f"{key}: {val}\n"
        system_content += "\n"
    
    # Add learning style information if available
    if primary_learning_style:
        system_content += "=== Student's Learning Style ===\n"
        system_content += f"Primary Learning Style: {primary_learning_style}\n"
        if learning_style_scores:
            system_content += "Scores:\n"
            for style, score in learning_style_scores.items():
                system_content += f"- {style}: {score}\n"
        system_content += "\n"
        system_content += (
            f"The student has a {primary_learning_style} learning preference. "
            f"Please tailor your explanations and suggestions accordingly. "
            f"For this learning style, you should emphasize:\n"
        )
        
        # Add specific guidance based on learning style
        if primary_learning_style == 'visual':
            system_content += (
                "- Use diagrams, charts, and images in explanations\n"
                "- Suggest visual study aids like mind maps and color coding\n"
                "- Describe concepts with visual metaphors and spatial relationships\n"
            )
        elif primary_learning_style == 'auditory':
            system_content += (
                "- Explain concepts as if speaking them aloud\n"
                "- Suggest verbal repetition and discussion-based learning\n"
                "- Recommend audio recordings and verbal mnemonics\n"
            )
        elif primary_learning_style == 'reading_writing':
            system_content += (
                "- Structure information in written format with lists and paragraphs\n"
                "- Suggest note-taking and written summaries as study techniques\n"
                "- Emphasize the importance of text-based learning resources\n"
            )
        elif primary_learning_style == 'kinesthetic':
            system_content += (
                "- Relate concepts to physical experiences and real-world applications\n"
                "- Suggest hands-on activities and practice-based learning\n"
                "- Recommend movement and physical interaction while studying\n"
            )
    
    # Add instructions for response
    if diagnostic_test_text and test_answers:
        system_content += (
            "ALWAYS start by analyzing the diagnostic test results when the conversation begins "
            "or when the user asks for help studying. Evaluate these answers for correctness, "
            "identify which ones are wrong, explain the correct solutions, and offer "
            "next steps or study tips tailored to their learning style.\n"
        )
    
    system_content += "If the user has other questions, do your best to help using the context.\n"

    # Construct messages for the model - use the system message
    messages = [
        {"role": "system", "content": system_content}
    ] + session['conversation']

    app.logger.info("=== Chat Endpoint Called ===")
    app.logger.info(f"System message length: {len(system_content)} characters")

    try:
        # If this is the first message from the user and we have diagnostic data,
        # add an instruction to analyze test results right away
        if len(session['conversation']) <= 1 and diagnostic_test_text and test_answers:
            first_time_instruction = {
                "role": "user", 
                "content": "Please analyze my diagnostic test results and provide feedback."
            }
            messages.insert(1, first_time_instruction)  # Insert after system but before user message
        
        # Send the conversation to OpenAI
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7
        )
        
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


@app.route('/clear_conversation', methods=['POST'])
def clear_conversation():
    """
    Clear only the conversation history but keep diagnostic and learning style data
    """
    # Only clear conversation history
    session['conversation'] = []
    return jsonify({'status': 'conversation cleared, data preserved'})


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080)