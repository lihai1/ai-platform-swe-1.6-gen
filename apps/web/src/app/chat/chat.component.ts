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
  approval?: {
    approvalRequestId?: string;
    options: string[];
  };
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
                <div *ngIf="message.approval?.options?.length" class="chat-approval-options">
                  <button
                    *ngFor="let option of message.approval?.options"
                    class="btn btn-option"
                    (click)="handleChatApprovalSelection(message, option)"
                    [disabled]="isApprovalSubmitted(message.approval?.approvalRequestId)"
                  >
                    {{ option }}
                  </button>
                </div>
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
        (approve)="handleDialogDecision($event, true)"
        (reject)="handleDialogDecision($event, false)"
        (selectedOption)="handleDialogSelection($event)"
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

    .chat-approval-options {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      margin-top: 0.75rem;
    }

    .chat-approval-options .btn-option {
      background: #667eea;
      color: white;
      text-align: left;
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
  private submittedApprovalRequestIds = new Set<string>();
  private runProgressMessageIndex: number | null = null;
  
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
      this.runId = params['thread_id'] || params['run_id'] || null;
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
  
  async onConfigComplete(config: any): Promise<void> {
    console.log('Config completed:', config);
    this.agentType = config.agentType;
    this.llmProvider = config.llmProvider;
    this.modelName = config.modelName;
    this.apiKey = config.apiKey;
    this.mockMode = config.mockMode;
    this.showConfig = false;
    
    console.log('After config complete - agentType:', this.agentType, 'llmProvider:', this.llmProvider, 'modelName:', this.modelName, 'mockMode:', this.mockMode);
    
    await this.initializeChatIfNeeded();
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

    this.logMessageConfig();
    this.prepareMessageSend();
    this.addUserMessage(message);

    try {
      await this.sendChatkitMessage(message, true);
    } catch (error) {
      this.handleMessageSendError(error);
    }
  }

  private logMessageConfig(): void {
    console.log('Sending message with config:', {
      agentType: this.agentType,
      llmProvider: this.llmProvider,
      mockMode: this.mockMode,
      apiKey: this.apiKey ? '***' : 'none'
    });
  }

  private prepareMessageSend(): void {
    this.newMessage = '';
    this.isSending = true;
    this.closeActivityStream();
  }

  private closeActivityStream(): void {
    // The chat response and activity SSE share the same event stream; close any
    // active activity stream while the chat response is consuming events. It will
    // be restarted once the assistant message completes.
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  private addUserMessage(message: string): void {
    this.messages.push({ role: 'user', content: message });
  }

  private handleMessageSendError(error: any): void {
    console.error('Failed to send message:', error);
    this.messages.push({
      role: 'assistant',
      content: 'Sorry, something went wrong. Please try again.'
    });
    this.isSending = false;
    this.cdr.detectChanges();
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

    this.initializeAssistantMessage(updateUi);

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      const result = this.processSSELines(lines, assistantMessage, updateUi);
      assistantMessage = result.assistantMessage;
      if (result.workflowTriggered) {
        workflowTriggered = true;
      }
    }

    if (updateUi && !assistantMessage) {
      this.removeEmptyAssistantPlaceholder();
    }

    return { workflowTriggered };
  }

  private initializeAssistantMessage(updateUi: boolean): void {
    if (updateUi) {
      this.messages.push({ role: 'assistant', content: '' });
    }
  }

  private removeEmptyAssistantPlaceholder(): void {
    const lastMessage = this.messages[this.messages.length - 1];
    if (lastMessage?.role === 'assistant' && !lastMessage.content) {
      this.messages.pop();
      this.cdr.detectChanges();
    }
  }

  private processSSELines(
    lines: string[],
    assistantMessage: string,
    updateUi: boolean
  ): { assistantMessage: string; workflowTriggered: boolean } {
    let workflowTriggered = false;

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const result = this.processSSELine(line, assistantMessage, updateUi);
        assistantMessage = result.assistantMessage;
        if (result.workflowTriggered) {
          workflowTriggered = true;
        }
      }
    }

    return { assistantMessage, workflowTriggered };
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

      if ((data.type === 'progress_update' || (data.icon && data.text)) && updateUi) {
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
        console.log('Extracted projects from JSON text:', projects.length, 'projects');
      }
    } catch (e) {
      console.log('Failed to parse text as JSON, checking item.projects field');
      // Not JSON, use regular text
    }

    if (projects.length === 0) {
      projects = data.item.projects || [];
      console.log('Extracted projects from item.projects:', projects.length, 'projects');
    }

    console.log('Final projects array:', projects);
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
    console.log('updateAssistantMessage called with:', { content, projects, complete });
    this.ngZone.run(() => {
      const lastMessage = this.messages[this.messages.length - 1];
      if (lastMessage?.role === 'assistant') {
        this.messages[this.messages.length - 1] = {
          role: 'assistant',
          content: content,
          projects: projects
        };
        console.log('Updated message:', this.messages[this.messages.length - 1]);
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
    
    console.log('Loading thread for project:', this.projectId);
    
    try {
      const { token, userId } = this.getUserInfo();
      const savedRunId = this.getSavedRunId();
      
      if (savedRunId && await this.tryLoadThreadByRunId(savedRunId, token, userId)) {
        return;
      }
      
      if (await this.tryLoadThreadByProjectId(this.projectId, token, userId)) {
        return;
      }
      
      this.initializeEmptyThread();
    } catch (error) {
      console.error('Failed to load thread:', error);
      this.messages = [];
    }
  }

  private async tryLoadThreadByRunId(
    savedRunId: string,
    token: string | null,
    userId: string
  ): Promise<boolean> {
    const loaded = await this.loadThreadByRunId(savedRunId, token, userId);
    if (loaded) {
      return true;
    }
    this.clearProjectRunId();
    return false;
  }

  private async tryLoadThreadByProjectId(
    projectId: string,
    token: string | null,
    userId: string
  ): Promise<boolean> {
    return await this.loadThreadByProjectId(projectId, token, userId);
  }

  private async initializeChatIfNeeded(): Promise<void> {
    // If we already have a runId from URL or localStorage, just load the thread
    if (this.runId) {
      this.loadThread();
      return;
    }
    
    // Otherwise, initialize a new chat thread
    try {
      const { token, userId } = this.getUserInfo();
      const urlParams = this.getUrlParams();
      
      const newRunId = await this.initializeChatThread(token, userId, urlParams);
      
      if (newRunId) {
        this.runId = newRunId;
        this.handleRunStarted(newRunId);
      }
    } catch (error) {
      console.error('Failed to initialize chat:', error);
    }
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
    const response = await this.sendChatInitializationRequest(token, userId, urlParams);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to initialize chat: ${response.status} ${errorText}`);
    }

    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const data = await response.json();
      const runId = data.run_id || null;
      if (runId && urlParams.projectId) {
        this.updateProjectWithRunId(urlParams.projectId, runId);
      }
      return runId;
    }

    return await this.processInitializationStream(response, urlParams.projectId);
  }

  private buildInitializationRequestPayload(
    urlParams: { projectId: string | null; repositoryId: string | null; projectPath: string | null }
  ): object {
    return {
      project_id: urlParams.projectId,
      repository_id: urlParams.repositoryId,
      project_path: urlParams.projectPath,
      mock_mode: this.mockMode,
      llm_provider: this.llmProvider,
      model_name: this.modelName,
      agent_type: this.agentType,
      api_key: this.apiKey
    };
  }

  private async sendChatInitializationRequest(
    token: string | null,
    userId: string,
    urlParams: { projectId: string | null; repositoryId: string | null; projectPath: string | null }
  ): Promise<Response> {
    return await fetch('/api/chatkit/start', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-User-Subject': userId
      },
      body: JSON.stringify(this.buildInitializationRequestPayload(urlParams))
    });
  }

  private async processInitializationStream(
    response: Response,
    projectId: string | null
  ): Promise<string | null> {
    const body = response.body;
    if (!body) {
      return null;
    }

    const reader = body.getReader();
    const decoder = new TextDecoder();
    let assistantMessage = '';
    let runId: string | null = null;

    // Initialize assistant message for UI updates
    this.initializeAssistantMessage(true);

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        // Process SSE lines using the same logic as sendChatkitMessage
        const result = this.processSSELines(lines, assistantMessage, true);
        assistantMessage = result.assistantMessage;

        // Extract run_id from the stream
        if (!runId) {
          runId = this.extractRunIdFromLines(lines);
          if (runId) {
            this.updateProjectWithRunId(projectId, runId);
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    // Clean up an empty placeholder if the init stream carried only metadata
    if (!assistantMessage) {
      this.removeEmptyAssistantPlaceholder();
    }

    // Mark sending as complete
    this.isSending = false;
    this.cdr.detectChanges();

    return runId;
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
      return data.item?.thread_id || data.item?.run_id || data.thread_id || data.run_id || null;
    } catch (e) {
      console.debug('Failed to parse SSE line:', line);
      return null;
    }
  }

  private updateProjectWithRunId(projectId: string | null, runId: string): void {
    if (!projectId) {
      return;
    }

    const projectStr = localStorage.getItem(`project_${projectId}`);
    if (projectStr) {
      try {
        const project = JSON.parse(projectStr);
        project.thread_id = runId;
        localStorage.setItem(`project_${projectId}`, JSON.stringify(project));
        console.log(`Updated project ${projectId} with run_id ${runId}`);
      } catch (e) {
        console.error('Failed to update project object in localStorage:', e);
      }
    }
  }

  private getSavedRunId(): string | null {
    // Prefer thread_id from URL query params
    if (this.runId) {
      console.log('Using run_id from query params:', this.runId);
      return this.runId;
    }
    
    // Fall back to localStorage project object
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

  private async loadThreadByProjectId(
    projectId: string,
    token: string | null,
    userId: string
  ): Promise<boolean> {
    try {
      const response = await this.http.get<any>(`/api/chatkit/threads/by-project/${projectId}`, {
        headers: { 
          Authorization: `Bearer ${token}`,
          'X-User-Subject': userId
        }
      }).toPromise();

      if (response && response.thread && response.thread.run_id) {
        this.runId = response.thread.run_id;
        this.messages = response.items || [];
        console.log('Successfully loaded thread by project_id');
        if (this.runId) {
          this.handleRunStarted(this.runId);
        }
        return true;
      }
    } catch (error) {
      console.log('No thread found for project, will create new one');
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
    this.submittedApprovalRequestIds.clear();
    this.runProgressMessageIndex = null;
    this.currentRunId = runId;
    this.currentRun = {
      runId: runId,
      status: 'running',
      createdAt: new Date().toISOString()
    };
    this.startEventStream(runId);
  }
  
  handleApprovalRequired(approval: any): void {
    const normalizedApproval = this.normalizeWaitingInput(approval);
    const approvalRequestId = normalizedApproval.approval_request_id;
    if (approvalRequestId && this.submittedApprovalRequestIds.has(approvalRequestId)) {
      return;
    }

    const isNewApproval = approvalRequestId !== this.pendingApproval?.approval_request_id;
    this.pendingApproval = normalizedApproval;
    if (isNewApproval) {
      const description = normalizedApproval.description || normalizedApproval.message || 'Approval required.';
      const options = Array.isArray(normalizedApproval.options) ? normalizedApproval.options : [];
      this.messages.push({
        role: 'assistant',
        content: description,
        approval: options.length > 0 ? { approvalRequestId, options } : undefined,
      });
    }
    this.showApprovalDialog = !approvalRequestId && !normalizedApproval.options?.length;
    this.cdr.detectChanges();
  }

  private normalizeWaitingInput(eventData: any): any {
    // crewai-expert publishes waiting_input with a stringified prompt payload
    const prompt = eventData?.prompt;
    if (typeof prompt === 'string') {
      try {
        const parsed = JSON.parse(prompt);
        return {
          ...eventData,
          approval_request_id: parsed.approval_request_id || eventData.approval_request_id,
          approval_type: parsed.approval_type || eventData.approval_type,
          message: prompt,
          options: parsed.options,
          affected_files_count: parsed.affected_files_count,
          summary: parsed.summary,
        };
      } catch {
        // prompt is not JSON; keep as-is
      }
    }
    return eventData;
  }

  handleDialogSelection(option: string): void {
    this.submitUserInput(option);
  }

  handleChatApprovalSelection(message: ChatMessage, option: string): void {
    this.submitUserInput(option, message.approval?.approvalRequestId);
  }

  isApprovalSubmitted(approvalRequestId: string | undefined): boolean {
    return !!approvalRequestId && this.submittedApprovalRequestIds.has(approvalRequestId);
  }

  handleDialogDecision(approvalId: string, approved: boolean): void {
    const isWaitingInput = this.pendingApproval?.approval_request_id || this.pendingApproval?.options;
    if (isWaitingInput) {
      this.submitUserInput(approved ? 'approved' : 'rejected');
      return;
    }

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

  private async submitUserInput(value: string, approvalRequestId = this.pendingApproval?.approval_request_id): Promise<void> {
    if (!this.currentRunId) {
      console.error('No current run id; cannot submit user input');
      return;
    }

    const { token, userId } = this.getUserInfo();
    try {
      const body: any = { input: value };
      if (approvalRequestId) {
        body.approval_request_id = approvalRequestId;
      }
      const response = await fetch(`/api/chatkit/input/${this.currentRunId}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
          'X-User-Subject': userId
        },
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        throw new Error(`Failed to send input: ${response.status}`);
      }

      if (approvalRequestId) {
        this.submittedApprovalRequestIds.add(approvalRequestId);
      }
      this.messages.push({ role: 'user', content: value });
      this.showApprovalDialog = false;
      this.pendingApproval = null;
      this.cdr.detectChanges();
    } catch (err) {
      console.error('Failed to submit user input:', err);
    }
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
    const eventData = event.payload ?? event.event_data ?? event;
    switch (event.event_type) {
      case 'output':
        this.updateRunProgressMessage(this.outputMessage(eventData));
        break;
      case 'progress_update':
        this.updateRunProgressMessage(eventData.message || eventData.content);
        break;
      case 'run_completed':
      case 'completed':
        if (this.currentRun) {
          this.currentRun.status = 'completed';
        }
        this.cdr.detectChanges();
        break;
      case 'final_answer':
        if (this.currentRun) {
          this.currentRun.status = 'completed';
        }
        this.completeRunProgressMessage(eventData.content || eventData.message);
        this.closeRunEventStream();
        break;
      case 'run_failed':
      case 'failed':
      case 'run_cancelled':
      case 'cancelled':
      case 'budget_exceeded':
        if (this.currentRun) {
          this.currentRun.status = event.event_type === 'budget_exceeded'
            ? 'budget_exceeded'
            : event.event_type.replace('run_', '');
        }
        this.completeRunProgressMessage(eventData.content || eventData.error || eventData.error_message || eventData.message);
        this.closeRunEventStream();
        break;
      case 'waiting_input':
        this.handleApprovalRequired(eventData);
        break;
      case 'approval_required':
        this.handleApprovalRequired(eventData);
        break;
      case 'artifact_created':
        this.handleArtifactCreated(eventData);
        break;
    }
  }

  private outputMessage(eventData: any): string {
    const data = eventData.data || eventData.content || eventData.message;
    if (typeof data !== 'string') {
      return '';
    }
    if (data.startsWith('uv sync exit code: 0')) {
      return 'Dependencies synchronized successfully.';
    }
    return data;
  }

  private updateRunProgressMessage(content: unknown): void {
    if (typeof content !== 'string' || !content.trim()) {
      return;
    }
    this.ngZone.run(() => {
      if (this.runProgressMessageIndex === null) {
        this.runProgressMessageIndex = this.messages.length;
        this.messages.push({ role: 'assistant', content });
      } else {
        this.messages[this.runProgressMessageIndex] = { role: 'assistant', content };
      }
      this.cdr.detectChanges();
    });
  }

  private completeRunProgressMessage(content: unknown): void {
    if (typeof content === 'string' && content.trim()) {
      this.ngZone.run(() => {
        if (this.runProgressMessageIndex === null) {
          this.messages.push({ role: 'assistant', content });
        } else {
          this.messages[this.runProgressMessageIndex] = { role: 'assistant', content };
        }
        this.runProgressMessageIndex = null;
        this.cdr.detectChanges();
      });
    }
  }

  private closeRunEventStream(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.cdr.detectChanges();
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
