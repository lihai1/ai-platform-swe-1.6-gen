import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

interface ApprovalRequest {
  id: string;
  chat_id: string;
  action_type: string;
  description: string;
  tool_name: string;
  parameters: any;
  created_at: string;
}

@Component({
  selector: 'app-approval-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="approval-overlay" *ngIf="visible" (click)="onBackdropClick($event)">
      <div class="approval-dialog" (click)="$event.stopPropagation()">
        <div class="dialog-header">
          <h2>Approval Required</h2>
          <button class="close-btn" (click)="closeDialog()">×</button>
        </div>
        
        <div class="dialog-body">
          <div class="approval-info">
            <div class="info-row">
              <span class="label">Action:</span>
              <span class="value">{{ approval?.action_type }}</span>
            </div>
            <div class="info-row">
              <span class="label">Tool:</span>
              <span class="value">{{ approval?.tool_name }}</span>
            </div>
            <div class="info-row">
              <span class="label">Description:</span>
              <span class="value">{{ approval?.description }}</span>
            </div>
          </div>
          
          <div class="parameters-section" *ngIf="approval?.parameters">
            <h3>Parameters</h3>
            <pre class="parameters-json">{{ formatParameters(approval.parameters) }}</pre>
          </div>
          
          <div class="warning">
            <strong>⚠️ Warning:</strong> This action may modify your repository or require external access.
          </div>
        </div>
        
        <div class="dialog-footer">
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
  `]
})
export class ApprovalDialogComponent {
  @Input() visible = false;
  @Input() approval: ApprovalRequest | null = null;
  @Output() approve = new EventEmitter<string>();
  @Output() reject = new EventEmitter<string>();
  @Output() close = new EventEmitter<void>();
  
  processing = false;
  
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
  
  closeDialog() {
    this.close.emit();
  }
  
  formatParameters(params: any): string {
    return JSON.stringify(params, null, 2);
  }
}
