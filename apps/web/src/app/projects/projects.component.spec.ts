import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ProjectsComponent } from './projects.component';
import { HttpClientService } from '../core/http-client.service';
import { Observable, of, throwError } from 'rxjs';

describe('ProjectsComponent', () => {
  let component: ProjectsComponent;
  let fixture: ComponentFixture<ProjectsComponent>;
  let httpService: HttpClientService;

  beforeEach(async () => {
    const httpServiceMock = {
      get: jasmine.createSpy('get').and.callFake((url: string) => {
        if (url.includes('/api/repositories')) {
          return of([]);
        }
        return of([]);
      }),
      post: jasmine.createSpy('post').and.returnValue(of({ id: '1', name: 'Test', description: 'Test' }))
    };

    await TestBed.configureTestingModule({
      imports: [ProjectsComponent],
      providers: [
        provideRouter([]),
        { provide: HttpClientService, useValue: httpServiceMock }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ProjectsComponent);
    component = fixture.componentInstance;
    httpService = TestBed.inject(HttpClientService);
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should load projects on init', () => {
    spyOn(component, 'loadProjects');
    const mockProjects = [
      { id: '1', name: 'Test Project', description: 'Test description' }
    ];
    component.projects = mockProjects;
    component.loading = false;
    component.error = null;
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.project-list')).toBeTruthy();
  });

  it('should show loading state and then render the project list', () => {
    spyOn(component, 'loadProjects');
    const mockProjects = [
      { id: '1', name: 'Test Project', description: 'Test description' }
    ];
    component.projects = mockProjects;
    component.loading = false;
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.project-list')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('.project-card')).toBeTruthy();
  });

  it('should handle error state', () => {
    spyOn(component, 'loadProjects');
    component.loading = false;
    component.error = 'Failed to load projects: API error. Please try again.';
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.error-state')).toBeTruthy();
  });

  it('should navigate to chat with project context on selection', () => {
    const routerSpy = spyOn(component['router'], 'navigate');
    const mockProject = { id: '1', name: 'Test', description: 'Test' };
    component.projectRepositories = { '1': [{ id: 'repo1', name: 'Repo', url: 'http://test.com' }] };

    component.selectProject(mockProject);

    expect(routerSpy).toHaveBeenCalledWith(['/chat'], {
      queryParams: { project_id: '1', repository_id: 'repo1' }
    });
  });

  it('should navigate to chat without repository if none exists', () => {
    const routerSpy = spyOn(component['router'], 'navigate');
    const mockProject = { id: '1', name: 'Test', description: 'Test' };
    component.projectRepositories = { '1': [] };

    component.selectProject(mockProject);

    expect(routerSpy).toHaveBeenCalledWith(['/chat'], {
      queryParams: { project_id: '1' }
    });
  });

  it('should show repository modal after creating project', async () => {
    const mockProject = { id: '1', name: 'New Project', description: 'Test' };
    (httpService.post as jasmine.Spy).and.returnValue(of(mockProject));

    component.newProject = { name: 'New Project', description: 'Test' };
    await component.createProject();

    expect(httpService.post).toHaveBeenCalledWith('/api/projects', jasmine.objectContaining({
      name: 'New Project',
      description: 'Test',
      organization_id: ''
    }));
    expect(component.showRepoModal).toBeTrue();
    expect(component.currentProjectId).toBe('1');
    expect(component.showCreateModal).toBeFalse();
  });

  it('should navigate to chat when skipping repository', () => {
    const routerSpy = spyOn(component['router'], 'navigate');
    component.currentProjectId = '1';

    component.skipRepository();

    expect(routerSpy).toHaveBeenCalledWith(['/chat'], {
      queryParams: { project_id: '1' }
    });
    expect(component.showRepoModal).toBeFalse();
  });

  it('should add repository and navigate to chat', async () => {
    const routerSpy = spyOn(component['router'], 'navigate');
    const mockRepo = { id: 'repo1', name: 'test-repo', url: 'https://github.com/test/repo.git' };
    (httpService.post as jasmine.Spy).and.returnValue(of(mockRepo));

    component.currentProjectId = '1';
    component.newRepo = { name: 'test-repo', git_url: 'https://github.com/test/repo.git', branch: 'main' };

    await component.addRepository();

    expect(httpService.post).toHaveBeenCalledWith('/api/repositories', {
      project_id: '1',
      name: 'test-repo',
      git_url: 'https://github.com/test/repo.git',
      branch: 'main'
    });
    expect(routerSpy).toHaveBeenCalledWith(['/chat'], {
      queryParams: { project_id: '1', repository_id: 'repo1' }
    });
  });
});
