import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ChatComponent } from './chat.component';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';

describe('ChatComponent', () => {
  let component: ChatComponent;
  let fixture: ComponentFixture<ChatComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ChatComponent],
      providers: [
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: {
            queryParams: of({ project_id: 'test-project', repository_id: 'test-repo' })
          }
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ChatComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should initialize with query params', () => {
    fixture.detectChanges();
    expect(component.projectId).toBe('test-project');
    expect(component.repositoryId).toBe('test-repo');
  });

  it('should handle missing query params', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [ChatComponent],
      providers: [
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: {
            queryParams: of({})
          }
        }
      ]
    });

    const newFixture = TestBed.createComponent(ChatComponent);
    const newComponent = newFixture.componentInstance;
    newFixture.detectChanges();

    expect(newComponent.projectId).toBeNull();
    expect(newComponent.repositoryId).toBeNull();
  });
});
