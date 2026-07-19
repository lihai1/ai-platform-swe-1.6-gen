import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

interface ApprovalRequest {
  id?: string;
  chat_id?: string;
  action_type?: string;
  description?: string;
  tool_name?: string;
  parameters?: any;
  created_at?: string;

  // crewai-expert waiting_input fields
  approval_request_id?: string;
  approval_type?: string;
  message?: string;
  options?: string[];
  affected_files_count?: number;
}

@Component({
  selector: 'app-approval-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="approval-overlay" *ngIf="visible" (click)="onBackdropClick($event)">
      <div class="approval-dialog" (click)="$event.stopPropagation()">
        <div class="dialog-header">
          <h2>{{ isWaitingInput ? 'Input Required' : 'Approval Required' }}</h2>
          <button class="close-btn" (click)="closeDialog()">×</button>
        </div>
        
        <div class="dialog-body">
          <div class="approval-info">
            <div class="info-row" *ngIf="approval?.action_type">
              <span class="label">Action:</span>
              <span class="value">{{ approval.action_type }}</span>
            </div>
            <div class="info-row" *ngIf="approval?.tool_name">
              <span class="label">Tool:</span>
              <span class="value">{{ approval.tool_name }}</span>
            </div>
            <div class="info-row" *ngIf="approval?.description">
              <span class="label">Description:</span>
              <span class="value">{{ approval.description }}</span>
            </div>
            <div class="info-row" *ngIf="approval?.approval_type">
              <span class="label">Type:</span>
              <span class="value">{{ approval.approval_type }}</span>
            </div>
            <div class="info-row" *ngIf="titleMessage">
              <span class="label">Message:</span>
              <span class="value">{{ titleMessage }}</span>
            </div>
            <div class="info-row" *ngIf="approval?.affected_files_count">
              <span class="label">Affected files:</span>
              <span class="value">{{ approval.affected_files_count }}</span>
            </div>
          </div>
          
          <div class="parameters-section" *ngIf="approval?.parameters">
            <h3>Parameters</h3>
            <pre class="parameters-json">{{ formatParameters(approval.parameters) }}</pre>
          </div>
          
          <div class="options-section" *ngIf="options.length > 0">
            <h3>{{ isWaitingInput ? 'Choose an option' : 'Options' }}</h3>
            <div class="option-buttons">
              <button 
                *ngFor="let option of options" 
                class="btn btn-option" 
                (click)="selectOption(option)" 
                [disabled]="processing">
                {{ option }}
              </button>
            </div>
          </div>
          
          <div class="warning" *ngIf="!isWaitingInput">
            <strong>⚠️ Warning:</strong> This action may modify your repository or require external access.
          </div>
        </div>
        
        <div class="dialog-footer" *ngIf="!isWaitingInput">
          <button class="btn btn-reject" (click)="rejectAction()" [disabled]="processing">
            {{ processing ? 'Processing...' : 'Reject' }}
          </button>
          <button class="btn btn-approve" (click)="approveAction()" [disabled]="processing">
            {{ processing ? 'Processing...' : 'Approve' }}
          </button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .approval-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.6);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 2000;
    }
    
    .approval-dialog {
      background: white;
      border-radius: 12px;
      padding: 2rem;
      max-width: 600px;
      width: 90%;
      max-height: 80vh;
      overflow-y: auto;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    }
    
    .dialog-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid #e0e0e0;
    }
    
    .dialog-header h2 {
      margin: 0;
      font-size: 1.5rem;
      color: #1a1a1a;
    }
    
    .close-btn {
      background: none;
      border: none;
      font-size: 2rem;
      cursor: pointer;
      color: #666;
      padding: 0;
      width: 32px;
      height: 32px;
      display: flex;
      align-items: center;
      justify-content: center;
      line-height: 1;
    }
    
    .close-btn:hover {
      color: #1a1a1a;
    }
    
    .dialog-body {
      margin-bottom: 1.5rem;
    }
    
    .approval-info {
      background: #f5f5f5;
      border-radius: 8px;
      padding: 1rem;
      margin-bottom: 1rem;
    }
    
    .info-row {
      display: flex;
      margin-bottom: 0.75rem;
    }
    
    .info-row:last-child {
      margin-bottom: 0;
    }
    
    .label {
      font-weight: 600;
      color: #666;
      width: 100px;
      flex-shrink: 0;
    }
    
    .value {
      color: #1a1a1a;
      flex: 1;
    }
    
    .parameters-section {
      margin-bottom: 1rem;
    }
    
    .parameters-section h3 {
      margin: 0 0 0.5rem 0;
      font-size: 1rem;
      color: #1a1a1a;
    }
    
    .parameters-json {
      background: #f5f5f5;
      border-radius: 4px;
      padding: 1rem;
      overflow-x: auto;
      font-size: 0.85rem;
      margin: 0;
    }
    
    .warning {
      background: #fff3cd;
      border: 1px solid #ffc107;
      border-radius: 4px;
      padding: 0.75rem;
      color: #856404;
      font-size: 0.9rem;
    }
    
    .dialog-footer {
      display: flex;
      justify-content: flex-end;
      gap: 1rem;
      padding-top: 1rem;
      border-top: 1px solid #e0e0e0;
    }
    
    .btn {
      padding: 0.75rem 1.5rem;
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      cursor: pointer;
      transition: all 0.2s;
    }
    
    .btn:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
    
    .btn-reject {
      background: #dc3545;
      color: white;
    }
    
    .btn-reject:hover:not(:disabled) {
      background: #c82333;
    }
    
    .btn-approve {
      background: #28a745;
      color: white;
    }
    
    .btn-approve:hover:not(:disabled) {
      background: #218838;
    }
    
    .options-section {
      margin-bottom: 1rem;
    }
    
    .options-section h3 {
      margin: 0 0 0.5rem 0;
      font-size: 1rem;
      color: #1a1a1a;
    }
    
    .option-buttons {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }
    
    .btn-option {
      background: #667eea;
      color: white;
      text-align: left;
    }
    
    .btn-option:hover:not(:disabled) {
      background: #5568d3;
    }
  `]
})
export class ApprovalDialogComponent implements OnChanges {
  @Input() visible = false;
  @Input() approval: ApprovalRequest | null = null;
  @Output() approve = new EventEmitter<string>();
  @Output() reject = new EventEmitter<string>();
  @Output() selectedOption = new EventEmitter<string>();
  @Output() close = new EventEmitter<void>();

  processing = false;
  private approvalKey: string | undefined;

  ngOnChanges(changes: SimpleChanges): void {
    const nextApprovalKey = this.approval?.approval_request_id || this.approval?.id;
    if (changes['approval'] && nextApprovalKey !== this.approvalKey) {
      this.approvalKey = nextApprovalKey;
      this.processing = false;
    }
  }

  get isWaitingInput(): boolean {
    return !!this.approval?.approval_request_id || !!this.approval?.approval_type || this.options.length > 0;
  }

  get titleMessage(): string {
    const prompt = this.approval?.message || '';
    try {
      const parsed = JSON.parse(prompt);
      return typeof parsed?.message === 'string' ? parsed.message : prompt;
    } catch {
      return prompt;
    }
  }

  get options(): string[] {
    const prompt = this.approval?.message || '';
    try {
      const parsed = JSON.parse(prompt);
      if (Array.isArray(parsed?.options)) {
        return parsed.options.map((o: any) => (typeof o === 'string' ? o : o?.name || String(o)));
      }
    } catch {
      // prompt is not JSON, fall back to explicit options field
    }
    return this.approval?.options || [];
  }

  onBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      this.close.emit();
    }
  }

  approveAction() {
    if (!this.approval) return;
    this.processing = true;
    this.approve.emit(this.approval.id);
  }

  rejectAction() {
    if (!this.approval) return;
    this.processing = true;
    this.reject.emit(this.approval.id);
  }

  selectOption(option: string) {
    this.processing = true;
    this.selectedOption.emit(option);
  }

  closeDialog() {
    this.close.emit();
  }

  formatParameters(params: any): string {
    return JSON.stringify(params, null, 2);
  }
}
