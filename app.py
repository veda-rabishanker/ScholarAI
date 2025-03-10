from flask import Flask, render_template, request, jsonify, session
from flask_session import Session
import openai
import os
app = Flask(__name__)
# Session configuration
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)
openai.api_key = ''
app.secret_key = 'supersecretkey'
# Home route
@app.route('/')
def home():
    return render_template('index.html')
@app.route('/diagnostic')
def diagnostic():
    return render_template('diagnostic.html')
@app.route('/chatbot')
def chatbot_page():
    return render_template('chatbot.html')
@app.route('/learning_style')
def learning_style():
    return render_template('learning_styles.html')

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    subject = request.json.get('subject', 'General Knowledge')
    
    if 'conversation' not in session:
        session['conversation'] = []
    
    if user_message:
        session['conversation'].append({"role": "user", "content": user_message})
    text_file_path = 'topic_prompts/initial_prompt.txt'
    # Ensure the directory exists
    os.makedirs(os.path.dirname(text_file_path), exist_ok=True)
    # Ensure the file exists before appending
    if not os.path.exists(text_file_path):
        with open(text_file_path, 'w') as file:
            file.write("Initial prompt for chatbot interaction.\n")
    with open(text_file_path, 'a') as file: 
        file.write(f"\n\nStudent has chosen the subject: {subject}\n")
    with open(text_file_path, 'r') as file:
        initial_prompt = file.read()
    messages = [{"role": "system", "content": initial_prompt}] + session['conversation']
    try:
        # Make API call to OpenAI using the messages
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=messages
        )
        # Extract the content from the response
        gpt_response = response.choices[0].message.content
        # Append the GPT response to the conversation history
        session['conversation'].append({
            "role": "assistant",
            "content": gpt_response
        })

        # Return a valid JSON response
        return jsonify({'response': gpt_response})
    except Exception as e:
        app.logger.error(f"An error occurred: {e}")
        return jsonify({'error': str(e)}), 500
   
# Clear session route
@app.route('/clear_session', methods=['GET'])
def clear_session():
    # Clear the session
    session.clear()
    return jsonify({'status': 'session cleared'})
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080)
