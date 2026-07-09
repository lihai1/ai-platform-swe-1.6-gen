import { Component, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { lastValueFrom } from 'rxjs';

interface AgentEvent {
  id: string;
  chat_id: string;
  step_id: string | null;
  event_type: string;
  event_data: any;
  sequence_number: number;
  created_at: string;
}

interface AgentStep {
  id: string;
  chat_id: string;
  phase: string;
  agent_name: string;
  status: string;
  started_at: string;
  completed_at: string | null;
}

@Component({
  selector: 'app-activity',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="activity-panel">
      <div class="activity-header">
        <h3>Agent Activity</h3>
        <div class="filters">
          <select [(ngModel)]="phaseFilter" class="filter-select">
            <option value="">All Phases</option>
            <option *ngFor="let phase of phases" [value]="phase">{{ phase }}</option>
          </select>
          <select [(ngModel)]="agentFilter" class="filter-select">
            <option value="">All Agents</option>
            <option *ngFor="let agent of agents" [value]="agent">{{ agent }}</option>
          </select>
        </div>
      </div>
      
      <div class="activity-timeline">
        <div *ngFor="let step of filteredSteps" class="timeline-item" [class.completed]="step.status === 'completed'" [class.failed]="step.status === 'failed'">
          <div class="timeline-marker"></div>
          <div class="timeline-content">
            <div class="timeline-header">
              <span class="phase">{{ step.phase }}</span>
              <span class="agent">{{ step.agent_name }}</span>
              <span class="status" [class.success]="step.status === 'completed'" [class.error]="step.status === 'failed'">
                {{ step.status }}
              </span>
            </div>
            <div class="timeline-events">
              <div *ngFor="let event of getEventsForStep(step)" class="event-item" (click)="toggleEvent(event)">
                <span class="event-type">{{ event.event_type }}</span>
                <span class="event-time">{{ formatTime(event.created_at) }}</span>
                <div *ngIf="expandedEvents.has(event.id)" class="event-details">
                  <pre>{{ formatEventData(event.event_data) }}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .activity-panel {
      padding: 20px;
      background: #f5f5f5;
      border-radius: 8px;
    }
    
    .activity-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
    }
    
    .filters {
      display: flex;
      gap: 10px;
    }
    
    .filter-select {
      padding: 8px;
      border: 1px solid #ddd;
      border-radius: 4px;
    }
    
    .timeline-item {
      display: flex;
      margin-bottom: 20px;
      padding: 15px;
      background: white;
      border-radius: 6px;
      border-left: 4px solid #ddd;
    }
    
    .timeline-item.completed {
      border-left-color: #4caf50;
    }
    
    .timeline-item.failed {
      border-left-color: #f44336;
    }
    
    .timeline-marker {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: #ddd;
      margin-right: 15px;
      margin-top: 5px;
    }
    
    .timeline-item.completed .timeline-marker {
      background: #4caf50;
    }
    
    .timeline-item.failed .timeline-marker {
      background: #f44336;
    }
    
    .timeline-content {
      flex: 1;
    }
    
    .timeline-header {
      display: flex;
      gap: 15px;
      margin-bottom: 10px;
      font-weight: 500;
    }
    
    .phase {
      color: #666;
    }
    
    .agent {
      color: #333;
    }
    
    .status {
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 12px;
      text-transform: uppercase;
    }
    
    .status.success {
      background: #e8f5e9;
      color: #4caf50;
    }
    
    .status.error {
      background: #ffebee;
      color: #f44336;
    }
    
    .event-item {
      padding: 8px;
      margin: 5px 0;
      background: #f9f9f9;
      border-radius: 4px;
      cursor: pointer;
    }
    
    .event-item:hover {
      background: #f0f0f0;
    }
    
    .event-type {
      font-weight: 500;
      margin-right: 10px;
    }
    
    .event-time {
      color: #999;
      font-size: 12px;
    }
    
    .event-details {
      margin-top: 10px;
      padding: 10px;
      background: #f5f5f5;
      border-radius: 4px;
    }
    
    .event-details pre {
      margin: 0;
      white-space: pre-wrap;
      word-wrap: break-word;
    }
  `]
})
export class ActivityComponent implements OnInit {
  @Input() chatId!: string;
  
  steps: AgentStep[] = [];
  events: AgentEvent[] = [];
  phases: string[] = [];
  agents: string[] = [];
  
  phaseFilter = '';
  agentFilter = '';
  expandedEvents = new Set<string>();
  
  constructor(private http: HttpClient) {}
  
  ngOnInit() {
    this.loadActivity();
  }
  
  async loadActivity() {
    if (!this.chatId) return;
    
    const token = localStorage.getItem('jwt_token');
    
    try {
      // Load steps from API
      const steps = await lastValueFrom(
        this.http.get<AgentStep[]>(`http://localhost:8000/agent/v1/runs/${this.chatId}/steps`, {
          headers: { Authorization: `Bearer ${token}` }
        })
      );
      this.steps = steps || [];
      
      // Load events from API
      const events = await lastValueFrom(
        this.http.get<AgentEvent[]>(`http://localhost:8000/agent/v1/runs/${this.chatId}/events`, {
          headers: { Authorization: `Bearer ${token}` }
        })
      );
      this.events = events || [];
      
      // Extract unique phases and agents
      this.phases = [...new Set(this.steps.map(s => s.phase))];
      this.agents = [...new Set(this.steps.map(s => s.agent_name))];
    } catch (error) {
      console.error('Failed to load activity:', error);
      this.steps = [];
      this.events = [];
    }
  }
  
  get filteredSteps() {
    return this.steps.filter(step => {
      if (this.phaseFilter && step.phase !== this.phaseFilter) return false;
      if (this.agentFilter && step.agent_name !== this.agentFilter) return false;
      return true;
    });
  }
  
  getEventsForStep(step: AgentStep) {
    return this.events.filter(e => e.step_id === step.id);
  }
  
  toggleEvent(event: AgentEvent) {
    if (this.expandedEvents.has(event.id)) {
      this.expandedEvents.delete(event.id);
    } else {
      this.expandedEvents.add(event.id);
    }
  }
  
  formatTime(timestamp: string) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  }
  
  formatEventData(data: any) {
    return JSON.stringify(data, null, 2);
  }
}
