import { Component, OnDestroy, OnInit, NgZone, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { ActivityComponent } from '../activity/activity.component';
import { ArtifactViewerComponent } from '../artifact-viewer/artifact-viewer.component';
import { DiffViewerComponent } from '../diff-viewer/diff-viewer.component';
import { ApprovalDialogComponent } from '../approval-dialog/approval-dialog.component';
import { RunContextComponent } from '../run-context/run-context.component';
import { ChatConfigComponent } from '../chat-config/chat-config.component';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  projects?: any[];
}

interface Project {
  name: string;
  path: string;
  main_file: string;
  description?: string;
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, ActivityComponent, ArtifactViewerComponent, DiffViewerComponent, ApprovalDialogComponent, RunContextComponent, ChatConfigComponent],
  template: `
    <app-chat-config *ngIf="showConfig" (configComplete)="onConfigComplete($event)"></app-chat-config>
    
    <div class="chat-container" *ngIf="!showConfig">
      @if (loadingThread) {
        <div class="loading-overlay">
          <div class="loading-spinner"></div>
          <p>Loading conversation...</p>
        </div>
      }
      <div class="chat-header">
        <h1>Agent Chat</h1>
        <div class="chat-controls">
          <label class="workflow-toggle">
            <input type="checkbox" [(ngModel)]="triggerWorkflow" />
            <span>Trigger Agent Workflow</span>
          </label>
          <button class="btn btn-secondary" (click)="toggleActivityPanel()" [class.active]="showActivityPanel">
            Activity
          </button>
          <button class="btn btn-secondary" (click)="resetConfig()">
            Reset Config
          </button>
          <button class="btn btn-close" (click)="closeSession()" [disabled]="!runId">
            Close session
          </button>
        </div>
      </div>
      
      <div class="chat-layout">
        <div class="chat-main" [class.with-panel]="showActivityPanel">
          <app-run-context [run]="currentRun"></app-run-context>
          
          <div class="chat-messages" *ngIf="messages.length > 0; else noMessages">
            <div *ngFor="let message of messages" class="message" [class.user]="message.role === 'user'" [class.assistant]="message.role === 'assistant'">
              <div *ngIf="message.projects && message.projects.length > 0" class="project-list">
                <div *ngFor="let project of message.projects" class="project-card" (click)="selectProject(project)">
                  <div class="project-name">{{ project.name }}</div>
                  <div class="project-path">{{ project.path }}</div>
                  <div class="project-main">Main: {{ project.main_file }}</div>
                  <div *ngIf="project.description" class="project-description">{{ project.description }}</div>
                </div>
              </div>
              <div *ngIf="!message.projects || message.projects.length === 0" class="message-content">
                <div *ngIf="isJsonArray(message.content)" class="project-list">
                  <div *ngFor="let project of parseJsonArray(message.content)" class="project-card" (click)="selectProject(project)">
                    <div class="project-name">{{ project.name }}</div>
                    <div class="project-path">{{ project.path }}</div>
                    <div class="project-main">Main: {{ project.main_file }}</div>
                    <div *ngIf="project.description" class="project-description">{{ project.description }}</div>
                  </div>
                </div>
                <span *ngIf="!isJsonArray(message.content)">{{ message.content }}</span>
              </div>
            </div>
          </div>
          
          <ng-template #noMessages>
            <div class="empty-chat">
              <p>Start a conversation with the AI agent</p>
            </div>
          </ng-template>
          
          <div class="chat-input-area">
            <textarea 
              [(ngModel)]="newMessage" 
              placeholder="Type your message..."
              (keydown.enter)="handleEnter($event)"
              [disabled]="isSending"
              rows="3"
              class="message-input"
            ></textarea>
            <button 
              class="btn btn-primary send-button" 
              (click)="sendMessage()" 
              [disabled]="isSending || !newMessage.trim()"
            >
              {{ isSending ? 'Sending...' : 'Send' }}
            </button>
          </div>
        </div>
        
        <div class="activity-sidebar" *ngIf="showActivityPanel && currentRunId">
          <app-activity [chatId]="currentRunId"></app-activity>
        </div>
      </div>
      
      <app-artifact-viewer *ngIf="selectedArtifact" [artifact]="selectedArtifact" (close)="selectedArtifact = null"></app-artifact-viewer>
      <app-diff-viewer *ngIf="selectedDiff" [diff]="selectedDiff" (close)="selectedDiff = null"></app-diff-viewer>
      
      <app-approval-dialog
        [visible]="showApprovalDialog"
        [approval]="pendingApproval"
        (approve)="handleApproval($event, true)"
        (reject)="handleApproval($event, false)"
        (close)="showApprovalDialog = false"
      ></app-approval-dialog>
    </div>
  `,
  styles: [`
    .chat-container {
      display: flex;
      flex-direction: column;
      height: 100vh;
      background: #f5f5f5;
    }
    
    .chat-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 1.5rem 2rem;
      background: white;
      border-bottom: 1px solid #e0e0e0;
    }
    
    .chat-header h1 {
      margin: 0;
      font-size: 1.5rem;
      color: #1a1a1a;
    }
    
    .chat-controls {
      display: flex;
      align-items: center;
      gap: 1rem;
    }
    
    .workflow-toggle {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      cursor: pointer;
      padding: 0.5rem 1rem;
      background: #f5f5f5;
      border-radius: 6px;
    }
    
    .workflow-toggle input {
      cursor: pointer;
    }
    
    .btn {
      padding: 0.5rem 1rem;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.2s;
    }
    
    .btn-secondary {
      background: #6c757d;
      color: white;
    }
    
    .btn-secondary:hover {
      background: #5a6268;
    }
    
    .btn-secondary.active {
      background: #667eea;
    }

    .btn-close {
      background: #dc3545;
      color: white;
    }

    .btn-close:hover:not(:disabled) {
      background: #c82333;
    }

    .btn-close:disabled {
      background: #ccc;
      cursor: not-allowed;
    }
    
    .chat-layout {
      display: flex;
      flex: 1;
      overflow: hidden;
    }
    
    .chat-main {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    
    .chat-main.with-panel {
      flex: 1;
    }
    
    #chatkit-root {
      flex: 1;
      overflow: hidden;
    }
    
    .activity-sidebar {
      width: 400px;
      background: white;
      border-left: 1px solid #e0e0e0;
      overflow-y: auto;
    }
    
    .chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 1rem;
      background: #f5f5f5;
      border-radius: 8px;
      margin-bottom: 1rem;
    }
    
    .message {
      margin-bottom: 0.75rem;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      max-width: 80%;
    }
    
    .message.user {
      background: #667eea;
      color: white;
      margin-left: auto;
    }
    
    .message.assistant {
      background: white;
      color: #333;
      border: 1px solid #e0e0e0;
    }
    
    .message-content {
      white-space: pre-wrap;
      word-wrap: break-word;
    }
    
    .project-list {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 1rem;
      margin-top: 1rem;
    }
    
    .project-card {
      background: #f8f9fa;
      border: 1px solid #e0e0e0;
      border-radius: 8px;
      padding: 1rem;
      cursor: pointer;
      transition: all 0.2s;
    }
    
    .project-card:hover {
      background: #e9ecef;
      border-color: #667eea;
      transform: translateY(-2px);
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    
    .project-name {
      font-weight: 600;
      color: #333;
      margin-bottom: 0.5rem;
      font-size: 1rem;
    }
    
    .project-path {
      color: #666;
      font-size: 0.85rem;
      margin-bottom: 0.25rem;
      font-family: monospace;
    }
    
    .project-main {
      color: #888;
      font-size: 0.8rem;
      margin-bottom: 0.25rem;
    }
    
    .project-description {
      color: #555;
      font-size: 0.85rem;
      margin-top: 0.5rem;
      line-height: 1.4;
    }
    
    .empty-chat {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #999;
      padding: 2rem;
    }
    
    .chat-input-area {
      display: flex;
      gap: 0.5rem;
      padding: 1rem 0;
    }
    
    .message-input {
      flex: 1;
      padding: 0.75rem;
      border: 1px solid #ddd;
      border-radius: 8px;
      resize: none;
      font-family: inherit;
    }
    
    .message-input:focus {
      outline: none;
      border-color: #667eea;
    }
    
    .send-button {
      padding: 0.75rem 1.5rem;
      background: #667eea;
      color: white;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      font-weight: 500;
    }
    
    .send-button:hover:not(:disabled) {
      background: #5568d3;
    }
    
    .send-button:disabled {
      background: #ccc;
      cursor: not-allowed;
    }
    
    .api-key-input {
    padding: 0.5rem;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-family: inherit;
    width: 200px;
  }

  .loading-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(255, 255, 255, 0.9);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }

  .loading-spinner {
    width: 40px;
    height: 40px;
    border: 3px solid #f3f3f3;
    border-top: 3px solid #667eea;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .loading-overlay p {
    color: #666;
    font-size: 1rem;
    margin: 0;
  }

  .btn-primary {
      background: #667eea;
      color: white;
    }
  `]
})
export class ChatComponent implements OnInit, OnDestroy {
  projectId: string | null = null;
  repositoryId: string | null = null;
  triggerWorkflow = false;
  mockMode = false;
  llmProvider = 'fake';
  modelName = '';
  agentType = 'specialist'; // 'single-agent' or 'specialist'
  apiKey = ''; // API key for non-Ollama providers
  showConfig = false;
  
  showActivityPanel = false;
  currentRunId: string | null = null;
  currentRun: any = null;
  selectedArtifact: any = null;
  selectedDiff: string | null = null;
  
  showApprovalDialog = false;
  pendingApproval: any = null;
  
  loadingThread = false;
  messages: ChatMessage[] = [];
  newMessage = '';
  isSending = false;
  runId: string | null = null;
  
  private eventSource: EventSource | null = null;
  
  constructor(
    private route: ActivatedRoute,
    private http: HttpClient,
    private ngZone: NgZone,
    private cdr: ChangeDetectorRef
  ) {
    this.route.queryParams.subscribe(params => {
      this.projectId = params['project_id'] || null;
      this.repositoryId = params['repository_id'] || null;
    });
  }

  ngOnInit(): void {
    // Load configuration from localStorage
    this.loadConfig();
    
    console.log('ngOnInit - loaded config:', {
      agentType: this.agentType,
      llmProvider: this.llmProvider,
      apiKey: this.apiKey ? '***' : 'none',
      mockMode: this.mockMode
    });
    
    // Always show config modal on page load to allow reconfiguration
    this.showConfig = true;
  }
  
  ngOnDestroy(): void {
    if (this.eventSource) {
      this.eventSource.close();
    }
  }
  
  toggleActivityPanel(): void {
    this.showActivityPanel = !this.showActivityPanel;
  }
  
  loadConfig(): void {
    this.agentType = localStorage.getItem('chat_agent_type') || '';
    this.llmProvider = localStorage.getItem('chat_llm_provider') || '';
    this.modelName = localStorage.getItem('chat_model_name') || '';
    this.apiKey = localStorage.getItem('chat_api_key') || '';
    this.mockMode = localStorage.getItem('chat_mock_mode') === 'true';
  }
  
  isConfigComplete(): boolean {
    if (!this.agentType || !this.llmProvider) {
      return false;
    }
    
    // Check if API key is required for selected provider
    if ((this.llmProvider === 'openai' || this.llmProvider === 'anthropic') && !this.apiKey) {
      return false;
    }
    
    return true;
  }
  
  onConfigComplete(config: any): void {
    console.log('Config completed:', config);
    this.agentType = config.agentType;
    this.llmProvider = config.llmProvider;
    this.modelName = config.modelName;
    this.apiKey = config.apiKey;
    this.mockMode = config.mockMode;
    this.showConfig = false;
    
    console.log('After config complete - agentType:', this.agentType, 'llmProvider:', this.llmProvider, 'modelName:', this.modelName, 'mockMode:', this.mockMode);
    
    this.loadThread();
  }
  
  resetConfig(): void {
    localStorage.removeItem('chat_agent_type');
    localStorage.removeItem('chat_llm_provider');
    localStorage.removeItem('chat_model_name');
    localStorage.removeItem('chat_api_key');
    localStorage.removeItem('chat_mock_mode');
    this.agentType = '';
    this.llmProvider = '';
    this.modelName = '';
    this.apiKey = '';
    this.mockMode = false;
    this.runId = null;
    this.showConfig = true;
  }
  
  handleEnter(event: Event): void {
    const keyboardEvent = event as KeyboardEvent;
    if (keyboardEvent.shiftKey) return;
    keyboardEvent.preventDefault();
    this.sendMessage();
  }
  
  async sendMessage(): Promise<void> {
    const message = this.newMessage.trim();
    if (!message || this.isSending) return;

    console.log('Sending message with config:', {
      agentType: this.agentType,
      llmProvider: this.llmProvider,
      mockMode: this.mockMode,
      apiKey: this.apiKey ? '***' : 'none'
    });

    this.newMessage = '';
    this.isSending = true;

    // The chat response and activity SSE share the same event stream; close any
    // active activity stream while the chat response is consuming events. It will
    // be restarted once the assistant message completes.
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }

    // Add user message immediately
    this.messages.push({ role: 'user', content: message });

    try {
      await this.sendChatkitMessage(message, true);
    } catch (error) {
      console.error('Failed to send message:', error);
      this.messages.push({
        role: 'assistant',
        content: 'Sorry, something went wrong. Please try again.'
      });
      this.isSending = false;
      this.cdr.detectChanges();
    }
  }

  private async sendChatkitMessage(message: string, updateUi: boolean): Promise<void> {
    const { token, userId } = this.getUserInfo();
    const response = await this.sendChatkitRequest(token, userId, message);
    
    if (!response.ok) {
      throw new Error('Failed to send message');
    }

    const result = await this.processChatkitStream(response, updateUi);
    
    if (this.isSending) {
      this.isSending = false;
      this.cdr.detectChanges();
    }

    if (result.workflowTriggered && this.runId) {
      this.handleRunStarted(this.runId);
    }
  }

  private getUserInfo(): { token: string | null; userId: string } {
    const token = localStorage.getItem('jwt_token');
    const userStr = localStorage.getItem('user');
    const user = userStr ? JSON.parse(userStr) : null;
    const userId = (user?.id || 'user-local-dev').replace(/:/g, '-');
    return { token, userId };
  }

  private async sendChatkitRequest(
    token: string | null,
    userId: string,
    message: string
  ): Promise<Response> {
    return await fetch('/api/chatkit/', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-User-Subject': userId
      },
      body: JSON.stringify({
        message: message,
        run_id: this.runId,
        trigger_workflow: this.triggerWorkflow,
        project_id: this.projectId,
        repository_id: this.repositoryId,
        mock_mode: this.mockMode,
        llm_provider: this.llmProvider,
        model_name: this.modelName,
        agent_type: this.agentType,
        api_key: this.apiKey
      })
    });
  }

  private async processChatkitStream(
    response: Response,
    updateUi: boolean
  ): Promise<{ workflowTriggered: boolean }> {
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let assistantMessage = '';
    let workflowTriggered = false;

    if (updateUi) {
      this.messages.push({ role: 'assistant', content: '' });
    }

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const result = this.processSSELine(line, assistantMessage, updateUi);
          assistantMessage = result.assistantMessage;
          if (result.workflowTriggered) {
            workflowTriggered = true;
          }
        }
      }
    }

    return { workflowTriggered };
  }

  private processSSELine(
    line: string,
    assistantMessage: string,
    updateUi: boolean
  ): { assistantMessage: string; workflowTriggered: boolean } {
    try {
      const data = JSON.parse(line.slice(6));
      console.log('SSE data:', data);

      let workflowTriggered = false;
      if (data.workflow_triggered) {
        workflowTriggered = true;
      }

      if (data.type === 'progress_update' && updateUi) {
        this.handleProgressUpdate(data);
      } else if (data.type === 'thread.item.done' && data.item) {
        const result = this.handleThreadItemDone(data, assistantMessage, updateUi);
        assistantMessage = result.assistantMessage;
      } else if (data.content) {
        assistantMessage = this.handleContentUpdate(data, assistantMessage, updateUi);
      }

      return { assistantMessage, workflowTriggered };
    } catch (e) {
      console.error('SSE parse error:', e);
      return { assistantMessage, workflowTriggered: false };
    }
  }

  private handleProgressUpdate(data: any): void {
    this.ngZone.run(() => {
      const lastMessage = this.messages[this.messages.length - 1];
      if (lastMessage?.role === 'assistant') {
        this.messages[this.messages.length - 1] = {
          role: 'assistant',
          content: data.text || lastMessage.content
        };
        this.cdr.detectChanges();
      }
    });
  }

  private handleThreadItemDone(
    data: any,
    assistantMessage: string,
    updateUi: boolean
  ): { assistantMessage: string } {
    const content = data.item.content || [];
    if (content.length > 0) {
      const text = content.map((c: any) => c.text || '').join('');
      assistantMessage = text;

      const projects = this.extractProjectsFromItem(data, text);

      if (data.item.thread_id) {
        this.updateRunId(data.item.thread_id);
      }

      if (updateUi) {
        this.updateAssistantMessage(assistantMessage, projects, true);
      }
    }
    return { assistantMessage };
  }

  private extractProjectsFromItem(data: any, text: string): any[] {
    let projects: any[] = [];
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        projects = parsed;
      }
    } catch (e) {
      // Not JSON, use regular text
    }

    if (projects.length === 0) {
      projects = data.item.projects || [];
    }

    return projects;
  }

  private handleContentUpdate(
    data: any,
    assistantMessage: string,
    updateUi: boolean
  ): string {
    assistantMessage += data.content;
    if (data.thread_id) {
      this.updateRunId(data.thread_id);
    }

    if (updateUi) {
      this.updateAssistantMessage(assistantMessage, undefined, false);
    }

    return assistantMessage;
  }

  private updateAssistantMessage(
    content: string,
    projects: any[] | undefined,
    complete: boolean
  ): void {
    this.ngZone.run(() => {
      const lastMessage = this.messages[this.messages.length - 1];
      if (lastMessage?.role === 'assistant') {
        this.messages[this.messages.length - 1] = {
          role: 'assistant',
          content: content,
          projects: projects
        };
        if (complete) {
          this.isSending = false;
        }
        this.cdr.detectChanges();
      }
    });
  }

  private updateRunId(runId: string): void {
    this.runId = runId;
    if (this.projectId) {
      const projectStr = localStorage.getItem(`project_${this.projectId}`);
      if (projectStr) {
        try {
          const project = JSON.parse(projectStr);
          project.thread_id = runId;
          localStorage.setItem(`project_${this.projectId}`, JSON.stringify(project));
          console.log(`Updated project ${this.projectId} with run_id ${runId}`);
        } catch (e) {
          console.log('Failed to update project object in localStorage');
        }
      }
    }
    this.handleRunStarted(runId);
  }
  
  private async loadThread(): Promise<void> {
    if (!this.projectId) {
      console.log('No projectId, skipping loadThread');
      return;
    }
    
    this.loadingThread = true;
    console.log('Loading thread for project:', this.projectId);
    
    try {
      const { token, userId } = this.getUserInfo();
      const savedRunId = this.getSavedRunId();
      
      if (savedRunId) {
        const loaded = await this.loadThreadByRunId(savedRunId, token, userId);
        if (loaded) {
          return;
        }
        this.clearProjectRunId();
      }
      
      this.initializeEmptyThread();
    } catch (error) {
      console.error('Failed to load thread:', error);
      this.messages = [];
    } finally {
      console.log('loadThread completed, setting loadingThread = false');
      this.loadingThread = false;
    }
  }

  private getSavedRunId(): string | null {
    const projectStr = localStorage.getItem(`project_${this.projectId}`);
    if (projectStr) {
      try {
        const project = JSON.parse(projectStr);
        const savedRunId = project.thread_id;
        console.log('Found project object with run_id:', savedRunId);
        return savedRunId;
      } catch (error) {
        console.log('Failed to parse project object from localStorage');
      }
    }
    return null;
  }

  private async loadThreadByRunId(
    savedRunId: string,
    token: string | null,
    userId: string
  ): Promise<boolean> {
    try {
      const response = await this.http.get<any>(`/api/chatkit/threads/${savedRunId}`, {
        headers: { 
          Authorization: `Bearer ${token}`,
          'X-User-Subject': userId
        }
      }).toPromise();

      if (response && response.thread) {
        this.runId = savedRunId;
        this.messages = response.items || [];
        console.log('Successfully loaded thread from project.run_id');
        this.handleRunStarted(savedRunId);
        return true;
      }
    } catch (error) {
      console.log('Thread not found or invalid, clearing run_id from project');
    }
    return false;
  }

  private clearProjectRunId(): void {
    const projectStr = localStorage.getItem(`project_${this.projectId}`);
    if (projectStr) {
      try {
        const project = JSON.parse(projectStr);
        project.thread_id = null;
        localStorage.setItem(`project_${this.projectId}`, JSON.stringify(project));
      } catch (e) {
        console.log('Failed to update project object in localStorage');
      }
    }
  }

  private initializeEmptyThread(): void {
    console.log('No run_id found in project, initializing empty thread');
    this.messages = [];
    this.runId = null;
  }
  
  handleRunStarted(runId: string): void {
    this.currentRunId = runId;
    this.currentRun = {
      runId: runId,
      status: 'running',
      createdAt: new Date().toISOString()
    };
    this.startEventStream(runId);
  }
  
  handleApprovalRequired(approval: any): void {
    this.pendingApproval = approval;
    this.showApprovalDialog = true;
  }
  
  handleApproval(approvalId: string, approved: boolean): void {
    const endpoint = approved ? 'approve' : 'reject';
    this.http.post(`/api/agent/runs/${this.currentRunId}/approvals/${approvalId}/${endpoint}`, {})
      .subscribe({
        next: () => {
          this.showApprovalDialog = false;
          this.pendingApproval = null;
        },
        error: (err) => {
          console.error('Failed to submit approval:', err);
        }
      });
  }
  
  handleArtifactCreated(artifact: any): void {
    if (artifact.kind === 'code_diff') {
      this.selectedDiff = artifact.content;
    } else {
      this.selectedArtifact = artifact;
    }
  }
  
  private startEventStream(runId: string): void {
    if (this.eventSource) {
      this.eventSource.close();
    }
    
    const token = localStorage.getItem('jwt_token');
    this.eventSource = new EventSource(`/api/agent/runs/${runId}/events?token=${token}`);
    
    this.eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleEvent(data);
    };
    
    this.eventSource.onerror = (error) => {
      console.error('EventStream error:', error);
    };
  }
  
  private handleEvent(event: any): void {
    switch (event.event_type) {
      case 'run_completed':
      case 'run_failed':
      case 'run_cancelled':
      case 'completed':
      case 'failed':
      case 'cancelled':
      case 'budget_exceeded':
      case 'final_answer':
        if (this.currentRun) {
          if (event.event_type === 'final_answer' || event.event_type === 'completed') {
            this.currentRun.status = 'completed';
          } else if (event.event_type === 'budget_exceeded') {
            this.currentRun.status = 'budget_exceeded';
          } else {
            this.currentRun.status = event.event_type.replace('run_', '');
          }
        }
        if (this.eventSource) {
          this.eventSource.close();
        }
        break;
      case 'approval_required':
        this.handleApprovalRequired(event.event_data);
        break;
      case 'artifact_created':
        this.handleArtifactCreated(event.event_data);
        break;
    }
  }
  
  selectProject(project: Project): void {
    // Pre-fill the input with selected project path
    this.newMessage = project.path;
  }

  isJsonArray(content: string): boolean {
    try {
      const parsed = JSON.parse(content);
      return Array.isArray(parsed);
    } catch (e) {
      return false;
    }
  }

  parseJsonArray(content: string): any[] {
    try {
      const parsed = JSON.parse(content);
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }

  async closeSession(): Promise<void> {
    if (!this.runId) return;

    try {
      const { token, userId } = this.getUserInfo();
      await this.closeSessionOnServer(token, userId);
      this.clearThreadState();
      this.clearProjectThreadId();
      this.addSuccessMessage();
    } catch (error) {
      console.error('Failed to close session:', error);
      this.addErrorMessage();
    }
  }

  private async closeSessionOnServer(token: string | null, userId: string): Promise<void> {
    await this.http.post(`/api/chatkit/close/${this.runId}`, {}, {
      headers: {
        Authorization: `Bearer ${token}`,
        'X-User-Subject': userId
      }
    }).toPromise();
  }

  private clearThreadState(): void {
    this.runId = null;
    this.messages = [];
    this.currentRunId = null;
    this.currentRun = null;
  }

  private clearProjectThreadId(): void {
    if (this.projectId) {
      const projectStr = localStorage.getItem(`project_${this.projectId}`);
      if (projectStr) {
        try {
          const project = JSON.parse(projectStr);
          project.thread_id = null;
          localStorage.setItem(`project_${this.projectId}`, JSON.stringify(project));
          console.log(`Cleared thread_id from project ${this.projectId}`);
        } catch (e) {
          console.error('Failed to clear thread_id from project object:', e);
        }
      }
    }
  }

  private addSuccessMessage(): void {
    this.messages.push({ role: 'assistant', content: 'Session closed. You can start a new conversation.' });
  }

  private addErrorMessage(): void {
    this.messages.push({ role: 'assistant', content: 'Failed to close session. Please try again.' });
  }
}
