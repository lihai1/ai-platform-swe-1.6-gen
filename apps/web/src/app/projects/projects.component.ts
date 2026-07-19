import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpClientService } from '../core/http-client.service';
import { lastValueFrom } from 'rxjs';

interface Project {
  id: string;
  name: string;
  description: string;
}

interface Repository {
  id: string;
  name: string;
  url: string;
}

@Component({
  selector: 'app-projects',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="projects-container">
      <header class="header">
        <h1>Agentic Engineering Platform</h1>
        <p class="subtitle">AI-powered software development automation</p>
      </header>

      <div class="actions">
        <button class="btn btn-primary" (click)="showCreateModal = true">+ New Project</button>
      </div>

      @if (loading) {
        <div class="loading-state">
          <div class="loading-spinner"></div>
          <p>Loading projects...</p>
        </div>
      }

      @if (error) {
        <div class="error-state">
          <p>{{ error }}</p>
          <button class="btn btn-secondary" (click)="loadProjects()">Retry</button>
        </div>
      }

      @if (!loading && !error) {
        @if (projects.length > 0) {
          <div class="project-list">
            <div *ngFor="let project of projects" class="project-card" (click)="selectProject(project)">
              <div class="project-icon">📁</div>
              <div class="project-info">
                <h3>{{ project.name }}</h3>
                <p>{{ project.description }}</p>
                <div class="project-repos" *ngIf="projectRepositories[project.id]">
                  <span class="repo-count">{{ projectRepositories[project.id].length }} repositories</span>
                </div>
              </div>
              <div class="project-arrow">→</div>
            </div>
          </div>
        } @else {
          <div class="empty-state">
            <div class="empty-icon">🚀</div>
            <h2>No projects yet</h2>
            <p>Create your first project to start building with AI agents</p>
            <button class="btn btn-primary" (click)="showCreateModal = true">Create Project</button>
          </div>
        }
      }

      <!-- Repository Selection Modal -->
      @if (showRepoModal) {
        <div class="modal-overlay" (click)="closeRepoModal()">
          <div class="modal" (click)="$event.stopPropagation()">
            <div class="modal-header">
              <h2>Add Repository (Optional)</h2>
              <button class="close-btn" (click)="closeRepoModal()">×</button>
            </div>
            <div class="modal-body">
              <p class="info-text">Connect a GitHub repository to your project or skip to start chatting.</p>

              <div class="repo-options">
                <button class="option-card" (click)="showGitHubForm()">
                  <div class="option-icon">🔗</div>
                  <h3>Add GitHub Repository</h3>
                  <p>Connect a repository from GitHub</p>
                </button>

                <button class="option-card" (click)="skipRepository()">
                  <div class="option-icon">💬</div>
                  <h3>Skip for Now</h3>
                  <p>Start chatting without a repository</p>
                </button>
              </div>

              @if (showGitHubInput) {
                <div class="github-form">
                  <div class="form-group">
                    <label for="repoName">Repository Name</label>
                    <input
                      id="repoName"
                      type="text"
                      [(ngModel)]="newRepo.name"
                      (ngModelChange)="clearRepoError()"
                      placeholder="my-repo"
                      class="form-input"
                    >
                  </div>
                  <div class="form-group">
                    <label for="gitUrl">Git URL</label>
                    <input
                      id="gitUrl"
                      type="text"
                      [(ngModel)]="newRepo.git_url"
                      (ngModelChange)="clearRepoError()"
                      placeholder="https://github.com/username/repo.git"
                      class="form-input"
                    >
                  </div>
                  <div class="form-group">
                    <label for="branch">Branch</label>
                    <input
                      id="branch"
                      type="text"
                      [(ngModel)]="newRepo.branch"
                      (ngModelChange)="clearRepoError()"
                      placeholder="main"
                      class="form-input"
                    >
                  </div>
                  @if (repoError) {
                    <div class="error-message">
                      {{ repoError }}
                    </div>
                  }
                  <div class="form-actions">
                    <button class="btn btn-secondary" (click)="showGitHubInput = false">Back</button>
                    <button class="btn btn-primary" (click)="addRepository()" [disabled]="addingRepo">
                      {{ addingRepo ? 'Adding...' : 'Add Repository' }}
                    </button>
                  </div>
                </div>
              }
            </div>
          </div>
        </div>
      }

      <!-- Create Project Modal -->
      @if (showCreateModal) {
        <div class="modal-overlay" (click)="closeCreateModal()">
          <div class="modal" (click)="$event.stopPropagation()">
            <div class="modal-header">
              <h2>Create New Project</h2>
              <button class="close-btn" (click)="closeCreateModal()">×</button>
            </div>
            <div class="modal-body">
              <div class="form-group">
                <label for="projectName">Project Name</label>
                <input
                  id="projectName"
                  type="text"
                  [(ngModel)]="newProject.name"
                  (ngModelChange)="clearCreateError()"
                  placeholder="Enter project name"
                  class="form-input"
                >
              </div>
              <div class="form-group">
                <label for="projectDescription">Description</label>
                <textarea
                  id="projectDescription"
                  [(ngModel)]="newProject.description"
                  (ngModelChange)="clearCreateError()"
                  placeholder="Enter project description"
                  class="form-textarea"
                  rows="3"
                ></textarea>
              </div>
              @if (createError) {
                <div class="error-message">
                  {{ createError }}
                </div>
              }
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" (click)="closeCreateModal()">Cancel</button>
              <button class="btn btn-primary" (click)="createProject()" [disabled]="creating">
                {{ creating ? 'Creating...' : 'Create Project' }}
              </button>
            </div>
          </div>
        </div>
      }
    </div>
  `,
  styles: [`
    .projects-container {
      max-width: 1200px;
      margin: 0 auto;
      padding: 2rem;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }

    .header {
      margin-bottom: 2rem;
      text-align: center;
    }

    .header h1 {
      font-size: 2.5rem;
      margin: 0 0 0.5rem 0;
      color: #1a1a1a;
    }

    .subtitle {
      font-size: 1.1rem;
      color: #666;
      margin: 0;
    }

    .actions {
      margin-bottom: 2rem;
      display: flex;
      justify-content: flex-end;
    }

    .btn {
      padding: 0.75rem 1.5rem;
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      cursor: pointer;
      transition: all 0.2s;
    }

    .btn-primary {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
    }

    .btn-primary:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }

    .btn-secondary {
      background: #6c757d;
      color: white;
    }

    .loading-state, .error-state {
      text-align: center;
      padding: 2rem;
      color: #666;
    }

    .loading-spinner {
      width: 40px;
      height: 40px;
      border: 3px solid #f3f3f3;
      border-top: 3px solid #667eea;
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 0 auto 1rem auto;
    }

    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }

    .error-state {
      color: #dc3545;
    }

    .project-list {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
      gap: 1.5rem;
    }

    .project-card {
      background: white;
      border: 1px solid #e0e0e0;
      border-radius: 12px;
      padding: 1.5rem;
      display: flex;
      align-items: center;
      gap: 1rem;
      cursor: pointer;
      transition: all 0.2s;
      box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }

    .project-card:hover {
      transform: translateY(-4px);
      box-shadow: 0 8px 16px rgba(0,0,0,0.1);
      border-color: #667eea;
    }

    .project-icon {
      font-size: 2.5rem;
    }

    .project-info {
      flex: 1;
    }

    .project-info h3 {
      margin: 0 0 0.5rem 0;
      font-size: 1.2rem;
      color: #1a1a1a;
    }

    .project-info p {
      margin: 0 0 0.5rem 0;
      color: #666;
      font-size: 0.9rem;
    }

    .project-repos {
      margin-top: 0.5rem;
    }

    .repo-count {
      font-size: 0.8rem;
      color: #667eea;
      background: #e3f2fd;
      padding: 0.25rem 0.5rem;
      border-radius: 4px;
    }

    .project-arrow {
      font-size: 1.5rem;
      color: #667eea;
    }

    .empty-state {
      text-align: center;
      padding: 4rem 2rem;
      background: #f8f9fa;
      border-radius: 12px;
    }

    .empty-icon {
      font-size: 4rem;
      margin-bottom: 1rem;
    }

    .empty-state h2 {
      font-size: 1.8rem;
      margin: 0 0 0.5rem 0;
      color: #1a1a1a;
    }

    .empty-state p {
      color: #666;
      margin: 0 0 2rem 0;
      font-size: 1.1rem;
    }

    .modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }

    .modal {
      background: white;
      border-radius: 12px;
      padding: 2rem;
      max-width: 500px;
      width: 90%;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
    }

    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
    }

    .modal-header h2 {
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
    }

    .close-btn:hover {
      color: #1a1a1a;
    }

    .form-group {
      margin-bottom: 1.5rem;
    }

    .form-group label {
      display: block;
      margin-bottom: 0.5rem;
      font-weight: 500;
      color: #1a1a1a;
    }

    .form-input,
    .form-textarea {
      width: 100%;
      padding: 0.75rem;
      border: 1px solid #e0e0e0;
      border-radius: 8px;
      font-size: 1rem;
      font-family: inherit;
      box-sizing: border-box;
    }

    .form-input:focus,
    .form-textarea:focus {
      outline: none;
      border-color: #667eea;
      box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }

    .form-textarea {
      resize: vertical;
    }

    .error-message {
      color: #dc3545;
      font-size: 0.9rem;
      margin-top: 0.5rem;
    }

    .modal-footer {
      display: flex;
      justify-content: flex-end;
      gap: 1rem;
      margin-top: 2rem;
    }

    .btn:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    .info-text {
      color: #666;
      margin-bottom: 1.5rem;
      text-align: center;
    }

    .repo-options {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
      margin-bottom: 1.5rem;
    }

    .option-card {
      background: #f8f9fa;
      border: 2px solid #e0e0e0;
      border-radius: 12px;
      padding: 1.5rem;
      cursor: pointer;
      transition: all 0.2s;
      text-align: center;
    }

    .option-card:hover {
      border-color: #667eea;
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);
    }

    .option-icon {
      font-size: 2.5rem;
      margin-bottom: 0.5rem;
    }

    .option-card h3 {
      margin: 0 0 0.5rem 0;
      font-size: 1.1rem;
      color: #1a1a1a;
    }

    .option-card p {
      margin: 0;
      font-size: 0.9rem;
      color: #666;
    }

    .github-form {
      margin-top: 1.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid #e0e0e0;
    }

    .form-actions {
      display: flex;
      justify-content: flex-end;
      gap: 1rem;
      margin-top: 1rem;
    }
  `]
})
export class ProjectsComponent implements OnInit {
  projects: Project[] = [];
  projectRepositories: { [projectId: string]: Repository[] } = {};
  loading = true;
  error: string | null = null;
  showCreateModal = false;
  creating = false;
  createError: string | null = null;
  newProject: { name: string; description: string } = { name: '', description: '' };

  showRepoModal = false;
  showGitHubInput = false;
  currentProjectId: string | null = null;
  addingRepo = false;
  repoError: string | null = null;
  newRepo: { name: string; git_url: string; branch: string } = { name: '', git_url: 'https://github.com/crewAIInc/crewAI-examples.git', branch: 'main' };

  constructor(
    private router: Router,
    private http: HttpClientService
  ) {}

  ngOnInit(): void {
    this.loadProjects();
  }

  async loadProjects(): Promise<void> {
    this.loading = true;
    this.error = null;

    try {
      const projects = await lastValueFrom(this.http.get<Project[]>('/api/projects'));
      this.projects = projects || [];
      this.projects.forEach((project) => {
        localStorage.setItem(`project_${project.id}`, JSON.stringify(project));
      });
      this.loading = false;
      await this.loadRepositories();
    } catch (e: any) {
      console.error('Failed to load projects:', e);
      this.error = `Failed to load projects: ${e?.message || 'Unknown error'}. Please try again.`;
      this.loading = false;
    }
  }

  async loadRepositories(): Promise<void> {
    const repoPromises = this.projects.map(async (project) => {
      try {
        const repos = await lastValueFrom(this.http.get<Repository[]>(`/api/repositories?project_id=${project.id}`));
        this.projectRepositories[project.id] = repos || [];
      } catch (e) {
        console.error(`Failed to load repositories for project ${project.id}:`, e);
        this.projectRepositories[project.id] = [];
      }
    });

    await Promise.all(repoPromises);
  }

  async selectProject(project: Project): Promise<void> {
    const repos = this.projectRepositories[project.id] || [];
    const repoId = repos.length > 0 ? repos[0].id : null;
    
    // Try to fetch existing thread for this project
    let threadId: string | null = null;
    try {
      const response = await lastValueFrom(this.http.get<any>(`/api/chatkit/threads/by-project/${project.id}`));
      if (response && response.thread && response.thread.run_id) {
        threadId = response.thread.run_id;
        console.log(`Found existing thread ${threadId} for project ${project.id}`);
      }
    } catch (error) {
      console.log(`No existing thread found for project ${project.id}, will create new one`);
    }
    
    this.navigateToChat(project.id, repoId, threadId);
  }

  async createProject(): Promise<void> {
    if (!this.validateProjectInput()) {
      return;
    }

    this.creating = true;
    this.createError = null;

    try {
      const createdProject = await this.createProjectOnServer();
      
      if (createdProject) {
        this.handleProjectCreated(createdProject);
      } else {
        this.createError = 'Failed to create project. No response from server.';
      }
    } catch (e: any) {
      this.handleProjectCreationError(e);
    } finally {
      this.creating = false;
    }
  }

  private validateProjectInput(): boolean {
    if (!this.newProject.name.trim()) {
      this.createError = 'Project name is required';
      return false;
    }
    return true;
  }

  private async createProjectOnServer(): Promise<Project | null> {
    const payload = {
      ...this.newProject,
      organization_id: '' // backend creates default org when empty
    };
    return await lastValueFrom(this.http.post<Project>('/api/projects', payload));
  }

  private handleProjectCreated(project: Project): void {
    this.projects.push(project);
    this.closeCreateModal();
    this.currentProjectId = project.id;
    this.showRepoModal = true;
  }

  private handleProjectCreationError(e: any): void {
    console.error('Failed to create project:', e);
    const errorMessage = e?.error?.message || e?.message || 'Failed to create project. Please try again.';
    this.createError = errorMessage;
  }

  showGitHubForm(): void {
    this.showGitHubInput = true;
  }

  closeCreateModal(): void {
    this.showCreateModal = false;
    this.resetCreateModal();
  }

  closeRepoModal(): void {
    this.showRepoModal = false;
    this.resetRepoModal();
  }

  clearCreateError(): void {
    this.createError = null;
  }

  clearRepoError(): void {
    this.repoError = null;
  }

  async addRepository(): Promise<void> {
    if (!this.validateRepositoryInput()) {
      return;
    }

    this.addingRepo = true;
    this.repoError = null;

    try {
      const repo = await this.createRepositoryOnServer();
      
      if (repo) {
        this.addRepositoryToProject(repo);
        if (this.currentProjectId && repo.id) {
          this.navigateToChat(this.currentProjectId, repo.id);
        }
      } else {
        this.repoError = 'Failed to add repository. No response from server.';
      }
    } catch (e) {
      console.error('Failed to add repository:', e);
      this.repoError = 'Failed to add repository. Please try again.';
    } finally {
      this.addingRepo = false;
    }
  }

  private validateRepositoryInput(): boolean {
    if (!this.newRepo.name.trim() || !this.newRepo.git_url.trim()) {
      this.repoError = 'Repository name and Git URL are required';
      return false;
    }

    if (!this.currentProjectId) {
      this.repoError = 'No project selected';
      return false;
    }

    return true;
  }

  private async createRepositoryOnServer(): Promise<Repository | null> {
    return await lastValueFrom(this.http.post<Repository>('/api/repositories', {
      project_id: this.currentProjectId,
      name: this.newRepo.name,
      git_url: this.newRepo.git_url,
      branch: this.newRepo.branch || 'main'
    }));
  }

  private addRepositoryToProject(repo: Repository): void {
    if (!this.currentProjectId) {
      return;
    }
    
    if (!this.projectRepositories[this.currentProjectId]) {
      this.projectRepositories[this.currentProjectId] = [];
    }
    this.projectRepositories[this.currentProjectId].push(repo);
  }

  skipRepository(): void {
    if (this.currentProjectId) {
      this.navigateToChat(this.currentProjectId, null);
    }
  }

  navigateToChat(projectId: string, repositoryId: string | null, threadId: string | null = null): void {
    this.closeRepoModal();

    const queryParams: { project_id: string; repository_id?: string; thread_id?: string } = { project_id: projectId };
    if (repositoryId) {
      queryParams.repository_id = repositoryId;
    }
    if (threadId) {
      queryParams.thread_id = threadId;
    }

    this.router.navigate(['/chat'], { queryParams });
  }

  private resetCreateModal(): void {
    this.newProject = { name: '', description: '' };
    this.createError = null;
  }

  private resetRepoModal(): void {
    this.showGitHubInput = false;
    this.currentProjectId = null;
    this.resetRepoForm();
    this.repoError = null;
  }

  private resetRepoForm(): void {
    this.newRepo = { name: '', git_url: '', branch: 'main' };
  }
}
