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

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, ActivityComponent, ArtifactViewerComponent, DiffViewerComponent, ApprovalDialogComponent, RunContextComponent],
  template: `
    <div class="chat-container">
      <div class="chat-header">
        <h1>Agent Chat</h1>
        <div class="chat-controls">
          <label class="workflow-toggle">
            <input type="checkbox" [(ngModel)]="triggerWorkflow" />
            <span>Trigger Agent Workflow</span>
          </label>
          <label class="workflow-toggle">
            <input type="checkbox" [(ngModel)]="mockMode" />
            <span>Mock Mode</span>
          </label>
          <button class="btn btn-secondary" (click)="toggleActivityPanel()" [class.active]="showActivityPanel">
            Activity
          </button>
        </div>
      </div>
      
      <div class="chat-layout">
        <div class="chat-main" [class.with-panel]="showActivityPanel">
          <app-run-context [run]="currentRun"></app-run-context>
          
          <div class="chat-messages" *ngIf="messages.length > 0; else noMessages">
            <div *ngFor="let message of messages" class="message" [class.user]="message.role === 'user'" [class.assistant]="message.role === 'assistant'">
              <div class="message-content">{{ message.content }}</div>
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
  
  showActivityPanel = false;
  currentRunId: string | null = null;
  currentRun: any = null;
  selectedArtifact: any = null;
  selectedDiff: string | null = null;
  
  showApprovalDialog = false;
  pendingApproval: any = null;
  
  messages: ChatMessage[] = [];
  newMessage = '';
  isSending = false;
  threadId: string | null = null;
  
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
    this.loadThread();
  }
  
  ngOnDestroy(): void {
    if (this.eventSource) {
      this.eventSource.close();
    }
  }
  
  toggleActivityPanel(): void {
    this.showActivityPanel = !this.showActivityPanel;
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
    
    this.newMessage = '';
    this.isSending = true;
    
    // Add user message immediately
    this.messages.push({ role: 'user', content: message });
    
    try {
      const token = localStorage.getItem('jwt_token');
      const response = await fetch('/chatkit/', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: message,
          thread_id: this.threadId,
          model_provider: 'ollama',
          model_name: 'llama3.2',
          trigger_workflow: this.triggerWorkflow,
          project_id: this.projectId,
          repository_id: this.repositoryId,
          mock_mode: this.mockMode
        })
      });
      
      if (!response.ok) {
        throw new Error('Failed to send message');
      }
      
      // Handle streaming response
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let assistantMessage = '';
      let workflowTriggered = false;
      
      // Add empty assistant message that will be updated
      this.messages.push({ role: 'assistant', content: '' });
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              console.log('Angular SSE data:', data);
              
              // Handle ChatKit protocol events
              if (data.type === 'progress_update') {
                console.log('Angular progress_update:', data.text);
                // Update with progress text
                this.ngZone.run(() => {
                  const lastMessage = this.messages[this.messages.length - 1];
                  if (lastMessage && lastMessage.role === 'assistant') {
                    this.messages[this.messages.length - 1] = { role: 'assistant', content: data.text || lastMessage.content };
                    this.cdr.detectChanges();
                  }
                });
              } else if (data.type === 'thread.item.done' && data.item) {
                console.log('Angular thread.item.done:', data.item);
                // Handle final assistant message
                const content = data.item.content || [];
                if (content.length > 0) {
                  const text = content.map((c: any) => c.text || '').join('');
                  assistantMessage = text;
                  if (data.item.thread_id) {
                    this.threadId = data.item.thread_id;
                  }
                  
                  this.ngZone.run(() => {
                    const lastMessage = this.messages[this.messages.length - 1];
                    if (lastMessage && lastMessage.role === 'assistant') {
                      this.messages[this.messages.length - 1] = { role: 'assistant', content: assistantMessage };
                      this.cdr.detectChanges();
                    }
                  });
                }
              } else if (data.content) {
                console.log('Angular legacy format:', data.content);
                // Legacy format fallback
                assistantMessage += data.content;
                if (data.thread_id) {
                  this.threadId = data.thread_id;
                }
                if (data.workflow_triggered) {
                  workflowTriggered = true;
                }
                
                // Update last message (assistant) - run in Angular zone and force change detection
                this.ngZone.run(() => {
                  const lastMessage = this.messages[this.messages.length - 1];
                  if (lastMessage && lastMessage.role === 'assistant') {
                    this.messages[this.messages.length - 1] = { role: 'assistant', content: assistantMessage };
                    this.cdr.detectChanges();
                  }
                });
              }
            } catch (e) {
              console.error('Angular SSE parse error:', e);
              // Ignore parse errors for incomplete chunks
            }
          }
        }
      }
      
      // Start event stream if workflow was triggered
      if (workflowTriggered && this.threadId) {
        this.handleRunStarted(this.threadId);
      }
      
    } catch (error) {
      console.error('Failed to send message:', error);
      this.messages.push({ 
        role: 'assistant', 
        content: 'Sorry, something went wrong. Please try again.' 
      });
    } finally {
      this.isSending = false;
    }
  }
  
  private async loadThread(): Promise<void> {
    if (!this.threadId) return;
    
    try {
      const token = localStorage.getItem('jwt_token');
      const response = await this.http.get<any>(`http://localhost:8000/api/chatkit/threads/${this.threadId}`, {
        headers: { Authorization: `Bearer ${token}` }
      }).toPromise();
      
      if (response) {
        this.messages = response.items || [];
      }
    } catch (error) {
      console.error('Failed to load thread:', error);
    }
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
    this.http.post(`http://localhost:8000/agent/v1/runs/${this.currentRunId}/approvals/${approvalId}/${endpoint}`, {})
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
    this.eventSource = new EventSource(`http://localhost:8000/agent/v1/runs/${runId}/events?token=${token}`);
    
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
        if (this.currentRun) {
          this.currentRun.status = event.event_type.replace('run_', '');
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
}
