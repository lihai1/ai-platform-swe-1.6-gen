import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface LLMModel {
  name: string;
  modified_at: string;
  size: number;
}

export type LLMProviderType = 'ollama' | 'openai' | 'anthropic';

@Injectable({
  providedIn: 'root'
})
export class LLMService {
  private baseUrl = '/api'; // Use relative URL to go through nginx proxy

  constructor(private http: HttpClient) {}

  getModels(providerType: LLMProviderType): Observable<LLMModel[]> {
    if (providerType === 'ollama') {
      return this.http.get<LLMModel[]>(`${this.baseUrl}/llm/models?provider=ollama`);
    }
    // For other providers, return empty array or implement as needed
    return new Observable<LLMModel[]>(observer => {
      observer.next([]);
      observer.complete();
    });
  }
}
