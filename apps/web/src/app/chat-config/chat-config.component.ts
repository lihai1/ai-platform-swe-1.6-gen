import { Component, Output, EventEmitter, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LLMService, LLMModel, LLMProviderType } from '../services/ollama.service';

@Component({
  selector: 'app-chat-config',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="config-container">
      <div class="config-card">
        <h2>Configure Your Chat Session</h2>
        <p class="subtitle">Please select your preferences before starting</p>
        
        <div class="config-section">
          <label class="config-label">
            <span>Agent Type</span>
            <select [(ngModel)]="agentType" class="config-select">
              <option value="">Select agent type...</option>
              <option value="specialist">Specialist (Multi-Agent)</option>
              <option value="single-agent">Single Agent</option>
              <option value="crewai">CrewAI</option>
            </select>
          </label>
          <p class="config-hint">Specialist mode uses multiple specialized agents, Single Agent uses one general agent, CrewAI runs CrewAI projects from source</p>
        </div>
        
        <div class="config-section">
          <label class="config-label">
            <span>LLM Provider</span>
            <select [(ngModel)]="llmProvider" (ngModelChange)="onLLMProviderChange()" class="config-select">
              <option value="">Select LLM provider...</option>
              <option value="fake">Fake (Testing)</option>
              <option value="ollama">Ollama (Local)</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </label>
          <p class="config-hint">Choose your AI model provider</p>
        </div>
        
        <div class="config-section" *ngIf="llmProvider === 'ollama'">
          <label class="config-label">
            <span>Ollama Model</span>
            <select [(ngModel)]="modelName" class="config-select" [disabled]="loadingModels">
              <option value="">Loading models...</option>
              <option *ngFor="let model of llmModels" [value]="model.name">{{ model.name }}</option>
            </select>
          </label>
          <p class="config-hint" *ngIf="loadingModels">Loading available models from Ollama...</p>
          <p class="config-hint" *ngIf="!loadingModels && llmModels.length === 0">No models available. Make sure Ollama is running.</p>
        </div>
        
        <div class="config-section" *ngIf="showAPIKeyInput">
          <label class="config-label">
            <span>API Key</span>
            <input type="password" [(ngModel)]="apiKey" placeholder="Enter your API key" class="config-input" />
          </label>
          <p class="config-hint">Required for {{ llmProvider }} provider</p>
        </div>
        
        <div class="config-section">
          <label class="config-label">
            <input type="checkbox" [(ngModel)]="mockMode" />
            <span>Mock Mode</span>
          </label>
          <p class="config-hint">Enable mock mode for testing without actual AI execution</p>
        </div>
        
        <button 
          class="btn btn-primary start-button" 
          (click)="onStartChat()" 
          [disabled]="!isFormValid()"
          [class.disabled]="!isFormValid()"
        >
          Start Chat
        </button>
      </div>
    </div>
  `,
  styles: [`
    .config-container {
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      padding: 2rem;
    }
    
    .config-card {
      background: white;
      border-radius: 16px;
      padding: 2.5rem;
      max-width: 500px;
      width: 100%;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    }
    
    .config-card h2 {
      margin: 0 0 0.5rem 0;
      font-size: 1.75rem;
      color: #1a1a1a;
      text-align: center;
    }
    
    .subtitle {
      text-align: center;
      color: #666;
      margin-bottom: 2rem;
      font-size: 0.95rem;
    }
    
    .config-section {
      margin-bottom: 1.5rem;
    }
    
    .config-label {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      font-weight: 500;
      color: #333;
    }
    
    .config-label input[type="checkbox"] {
      display: inline-block;
      width: auto;
      margin-right: 0.5rem;
    }
    
    .config-label span:first-child {
      font-size: 0.95rem;
    }
    
    .config-select,
    .config-input {
      padding: 0.75rem;
      border: 2px solid #e0e0e0;
      border-radius: 8px;
      font-size: 1rem;
      font-family: inherit;
      transition: border-color 0.2s;
    }
    
    .config-select:focus,
    .config-input:focus {
      outline: none;
      border-color: #667eea;
    }
    
    .config-hint {
      font-size: 0.85rem;
      color: #888;
      margin: 0.5rem 0 0 0;
      line-height: 1.4;
    }
    
    .start-button {
      width: 100%;
      padding: 1rem;
      font-size: 1.1rem;
      font-weight: 600;
      margin-top: 1rem;
      background: #667eea;
      color: white;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s;
    }
    
    .start-button:hover:not(.disabled) {
      background: #5568d3;
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }
    
    .start-button.disabled {
      background: #ccc;
      cursor: not-allowed;
      transform: none;
      box-shadow: none;
    }
    
    .btn-primary {
      background: #667eea;
      color: white;
    }
  `]
})
export class ChatConfigComponent implements OnInit {
  agentType = '';
  llmProvider = '';
  modelName = '';
  apiKey = '';
  mockMode = false;
  showAPIKeyInput = false;
  loadingModels = false;
  llmModels: LLMModel[] = [];
  
  @Output() configComplete = new EventEmitter<{
    agentType: string;
    llmProvider: string;
    modelName: string;
    apiKey: string;
    mockMode: boolean;
  }>();
  
  constructor(private llmService: LLMService) {
    // Load existing configuration from localStorage
    this.agentType = localStorage.getItem('chat_agent_type') || '';
    this.llmProvider = localStorage.getItem('chat_llm_provider') || '';
    this.modelName = localStorage.getItem('chat_model_name') || '';
    this.apiKey = localStorage.getItem('chat_api_key') || '';
    this.mockMode = localStorage.getItem('chat_mock_mode') === 'true';
    
    // Check if API key input should be shown
    this.showAPIKeyInput = this.llmProvider === 'openai' || this.llmProvider === 'anthropic';
  }
  
  ngOnInit(): void {
    // Load LLM models if provider is selected
    if (this.llmProvider) {
      this.loadLLMModels();
    }
  }
  
  loadLLMModels(): void {
    this.loadingModels = true;
    this.llmService.getModels(this.llmProvider as LLMProviderType).subscribe({
      next: (models: LLMModel[]) => {
        this.llmModels = models;
        this.loadingModels = false;
        // Set default model if none selected
        if (!this.modelName && models.length > 0) {
          this.modelName = models[0].name;
        }
      },
      error: (error: any) => {
        console.error('Failed to load LLM models:', error);
        this.llmModels = [];
        this.loadingModels = false;
      }
    });
  }
  
  onLLMProviderChange(): void {
    this.showAPIKeyInput = this.llmProvider === 'openai' || this.llmProvider === 'anthropic';
    if (!this.showAPIKeyInput) {
      this.apiKey = '';
    }
    
    // Load LLM models when provider is selected
    if (this.llmProvider === 'ollama') {
      this.loadLLMModels();
    } else {
      this.llmModels = [];
      this.modelName = '';
    }
  }
  
  isFormValid(): boolean {
    if (!this.agentType || !this.llmProvider) {
      return false;
    }
    
    if (this.llmProvider === 'ollama' && !this.modelName) {
      return false;
    }
    
    if (this.showAPIKeyInput && !this.apiKey) {
      return false;
    }
    
    return true;
  }
  
  async onStartChat(): Promise<void> {
    console.log('onStartChat called, form valid:', this.isFormValid());
    if (this.isFormValid()) {
      // Save to localStorage
      localStorage.setItem('chat_agent_type', this.agentType);
      localStorage.setItem('chat_llm_provider', this.llmProvider);
      localStorage.setItem('chat_model_name', this.modelName);
      localStorage.setItem('chat_api_key', this.apiKey);
      localStorage.setItem('chat_mock_mode', this.mockMode.toString());
      
      console.log('Calling startAgent...');
      // Call agent start API
      await this.startAgent();
      this.emitConfigComplete();
      
      console.log('startAgent completed');
    } else {
      console.log('Form is not valid');
    }
  }
  
  async startAgent(): Promise<void> {
    const { token, userId } = this.getUserInfo();
    const urlParams = this.getUrlParams();
    
    try {
      this.initializeChatThread(token, userId, urlParams);
    } catch (error) {
      console.error('Failed to initialize chat:', error);
    }
  }

  private getUserInfo(): { token: string | null; userId: string } {
    const token = localStorage.getItem('jwt_token');
    const userStr = localStorage.getItem('user');
    const user = userStr ? JSON.parse(userStr) : null;
    const userId = (user?.id || 'user-local-dev').replace(/:/g, '-');
    return { token, userId };
  }

  private getUrlParams(): { projectId: string | null; repositoryId: string | null; projectPath: string | null } {
    const urlParams = new URLSearchParams(window.location.search);
    return {
      projectId: urlParams.get('project_id'),
      repositoryId: urlParams.get('repository_id'),
      projectPath: urlParams.get('project_path')
    };
  }

  private async initializeChatThread(
    token: string | null,
    userId: string,
    urlParams: { projectId: string | null; repositoryId: string | null; projectPath: string | null }
  ): Promise<string | null> {
    const response = await fetch('/api/chatkit/', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-User-Subject': userId
      },
      body: JSON.stringify({
        message: 'Hi',
        project_id: urlParams.projectId,
        repository_id: urlParams.repositoryId,
        project_path: urlParams.projectPath,
        mock_mode: this.mockMode,
        llm_provider: this.llmProvider,
        model_name: this.modelName,
        agent_type: this.agentType,
        api_key: this.apiKey
      })
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to initialize chat: ${response.status} ${errorText}`);
    }

    // Extract runId from stream
    const body = response.body;
    if (!body) {
      return null;
    }

    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        const runId = this.extractRunIdFromLines(lines);
        if (runId) {
          // Update project with runId if projectId exists
          if (urlParams.projectId) {
            const projectStr = localStorage.getItem(`project_${urlParams.projectId}`);
            if (projectStr) {
              try {
                const project = JSON.parse(projectStr);
                project.thread_id = runId;
                localStorage.setItem(`project_${urlParams.projectId}`, JSON.stringify(project));
                console.log(`Updated project ${urlParams.projectId} with run_id ${runId}`);
              } catch (e) {
                console.error('Failed to update project object in localStorage:', e);
              }
            }
          }
          return runId;
        }
      }
    } finally {
      reader.releaseLock();
    }

    return null;
  }

  private emitConfigComplete(): void {
    console.log('Emitting configComplete event');
    this.configComplete.emit({
      agentType: this.agentType,
      llmProvider: this.llmProvider,
      modelName: this.modelName,
      apiKey: this.apiKey,
      mockMode: this.mockMode
    });
    console.log('configComplete event emitted');
  }

  private extractRunIdFromLines(lines: string[]): string | null {
    for (const line of lines) {
      const trimmedLine = line.trim();
      if (trimmedLine.startsWith('data: ')) {
        const runId = this.parseSSELineForRunId(trimmedLine);
        if (runId) {
          return runId;
        }
      }
    }
    return null;
  }

  private parseSSELineForRunId(line: string): string | null {
    try {
      const data = JSON.parse(line.slice(6));
      return data.thread_id || data.run_id || null;
    } catch (e) {
      console.debug('Failed to parse SSE line:', line);
      return null;
    }
  }
}
