document.addEventListener('DOMContentLoaded', () => {
  const chatForm = document.getElementById('chat-form');
  const chatInput = document.getElementById('chat-input');
  const chatBox = document.getElementById('chat-box');

  chatForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const message = chatInput.value.trim();
      if (!message) return;

      appendMessage('You', message);
      chatInput.value = '';

      try {
          const response = await fetch('/chat', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ message: message, subject: "General" })
          });

          const data = await response.json();
          appendMessage('AI', data.response || "Error: No response from AI.");
      } catch (error) {
          appendMessage('AI', 'Error: Could not reach server.');
      }
  });

  function appendMessage(sender, text) {
      const messageElement = document.createElement('div');
      messageElement.textContent = `${sender}: ${text}`;
      chatBox.appendChild(messageElement);
      chatBox.scrollTop = chatBox.scrollHeight;
  }
});
