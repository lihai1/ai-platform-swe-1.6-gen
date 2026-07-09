// ChatKit Client - Framework-agnostic chat component
(function(window) {
  'use strict';

  class ChatKit {
    constructor(options) {
      this.root = options.root;
      this.apiUrl = options.apiUrl;
      this.token = options.token;
      this.threadId = options.threadId || null;
      this.projectId = options.projectId || null;
      this.repositoryId = options.repositoryId || null;
      this.triggerWorkflow = options.triggerWorkflow || false;
      this.messages = [];
      this.eventSource = null;

      this.init();
    }

    init() {
      const rootElement = document.getElementById(this.root);
      if (!rootElement) {
        console.error('ChatKit root element not found:', this.root);
        return;
      }

      this.render(rootElement);
      this.loadThread();
    }

    render(rootElement) {
      rootElement.innerHTML = `
        <div class="chatkit-container">
          <div class="chatkit-messages" id="${this.root}-messages"></div>
          <div class="chatkit-input-area">
            <textarea 
              id="${this.root}-input" 
              placeholder="Type your message..." 
              rows="3"
            ></textarea>
            <button id="${this.root}-send" class="chatkit-send-button">Send</button>
          </div>
        </div>
        <style>
          .chatkit-container {
            display: flex;
            flex-direction: column;
            height: 100%;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          }
          .chatkit-messages {
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
            background: #f5f5f5;
            border-radius: 8px;
            margin-bottom: 1rem;
          }
          .chatkit-message {
            margin-bottom: 0.75rem;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            max-width: 80%;
          }
          .chatkit-message.user {
            background: #667eea;
            color: white;
            margin-left: auto;
          }
          .chatkit-message.assistant {
            background: white;
            color: #333;
            border: 1px solid #e0e0e0;
          }
          .chatkit-input-area {
            display: flex;
            gap: 0.5rem;
          }
          .chatkit-input-area textarea {
            flex: 1;
            padding: 0.75rem;
            border: 1px solid #ddd;
            border-radius: 8px;
            resize: none;
            font-family: inherit;
          }
          .chatkit-send-button {
            padding: 0.75rem 1.5rem;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 500;
          }
          .chatkit-send-button:hover {
            background: #5568d3;
          }
          .chatkit-send-button:disabled {
            background: #ccc;
            cursor: not-allowed;
          }
        </style>
      `;

      const input = document.getElementById(`${this.root}-input`);
      const sendButton = document.getElementById(`${this.root}-send`);

      sendButton.addEventListener('click', () => this.sendMessage());
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this.sendMessage();
        }
      });
    }

    async loadThread() {
      if (!this.threadId) return;

      try {
        const response = await fetch(`${this.apiUrl}/chatkit/threads/${this.threadId}`, {
          headers: {
            'Authorization': `Bearer ${this.token}`,
            'Content-Type': 'application/json'
          }
        });

        if (response.ok) {
          const data = await response.json();
          this.messages = data.items || [];
          this.renderMessages();
        } else {
          // If thread not found in ChatKit, start fresh
          this.messages = [];
          this.renderMessages();
        }
      } catch (error) {
        console.error('Failed to load thread:', error);
        // On error, start fresh
        this.messages = [];
        this.renderMessages();
      }
    }

    renderMessages() {
      const messagesContainer = document.getElementById(`${this.root}-messages`);
      messagesContainer.innerHTML = this.messages.map(msg => `
        <div class="chatkit-message ${msg.role}">
          ${this.escapeHtml(msg.content)}
        </div>
      `).join('');
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    async sendMessage() {
      const input = document.getElementById(`${this.root}-input`);
      const sendButton = document.getElementById(`${this.root}-send`);
      const message = input.value.trim();

      if (!message) return;

      input.value = '';
      sendButton.disabled = true;

      // Add user message to UI immediately
      this.messages.push({ role: 'user', content: message });
      this.renderMessages();

      try {
        console.log('Sending message to:', `${this.apiUrl}/chatkit/`);
        const response = await fetch(`${this.apiUrl}/chatkit/`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${this.token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            message: message,
            thread_id: this.threadId,
            model_provider: 'ollama',
            model_name: 'llama3.2',
            trigger_workflow: this.triggerWorkflow,
            project_id: this.projectId,
            repository_id: this.repositoryId
          })
        });

        console.log('Response status:', response.status);
        console.log('Response headers:', Object.fromEntries(response.headers.entries()));

        if (!response.ok) {
          throw new Error('Failed to send message');
        }

        // Handle streaming response
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let assistantMessage = '';

        console.log('Starting to read stream...');

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            console.log('Stream reading completed');
            break;
          }

          const chunk = decoder.decode(value);
          console.log('Received chunk:', chunk);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                console.log('Parsed SSE data:', data);
                
                // Handle ChatKit protocol events
                if (data.type === 'progress_update') {
                  console.log('Processing progress_update:', data.text);
                  // Show progress updates in the UI
                  const lastMessage = this.messages[this.messages.length - 1];
                  if (lastMessage && lastMessage.role === 'assistant') {
                    lastMessage.content = data.text || lastMessage.content;
                  } else {
                    this.messages.push({ role: 'assistant', content: data.text || '' });
                  }
                  this.renderMessages();
                } else if (data.type === 'thread.item.done' && data.item) {
                  console.log('Processing thread.item.done:', data.item);
                  // Handle final assistant message
                  const content = data.item.content || [];
                  if (content.length > 0) {
                    const text = content.map(c => c.text || '').join('');
                    assistantMessage = text;
                    if (data.item.thread_id) {
                      this.threadId = data.item.thread_id;
                    }
                    
                    const lastMessage = this.messages[this.messages.length - 1];
                    if (lastMessage && lastMessage.role === 'assistant') {
                      lastMessage.content = assistantMessage;
                    } else {
                      this.messages.push({ role: 'assistant', content: assistantMessage });
                    }
                    this.renderMessages();
                  }
                } else if (data.content) {
                  console.log('Processing legacy format:', data.content);
                  // Legacy format fallback
                  assistantMessage += data.content;
                  if (data.thread_id) {
                    this.threadId = data.thread_id;
                  }
                  
                  const lastMessage = this.messages[this.messages.length - 1];
                  if (lastMessage && lastMessage.role === 'assistant') {
                    lastMessage.content = assistantMessage;
                  } else {
                    this.messages.push({ role: 'assistant', content: assistantMessage });
                  }
                  this.renderMessages();
                }
              } catch (e) {
                console.error('Error parsing SSE data:', e, 'Line:', line);
                // Ignore parse errors for incomplete chunks
              }
            }
          }
        }

        // Save final assistant message
        if (assistantMessage) {
          const lastMessage = this.messages[this.messages.length - 1];
          if (lastMessage && lastMessage.role === 'assistant') {
            lastMessage.content = assistantMessage;
          }
        }

      } catch (error) {
        console.error('Failed to send message:', error);
        this.messages.push({ 
          role: 'assistant', 
          content: 'Sorry, something went wrong. Please try again.' 
        });
        this.renderMessages();
      } finally {
        sendButton.disabled = false;
        input.focus();
      }
    }

    escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      window.ChatKit = ChatKit;
    });
  } else {
    window.ChatKit = ChatKit;
  }

})(window);
