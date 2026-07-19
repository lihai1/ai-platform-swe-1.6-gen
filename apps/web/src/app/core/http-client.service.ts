import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

@Injectable({
  providedIn: 'root'
})
export class HttpClientService {
  private apiUrl = ''; // Empty base URL - full paths are specified in component calls
  private agentApiUrl = ''; // Use relative URLs to go through nginx proxy

  constructor(private http: HttpClient) {}

  private getHeaders(): HttpHeaders {
    const token = localStorage.getItem('jwt_token');
    const userStr = localStorage.getItem('user');
    const user = userStr ? JSON.parse(userStr) : null;
    
    const headers = new HttpHeaders({
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    });

    // Add X-User-Subject header for agent-service requests
    // Sanitize user ID: replace colons with hyphens for NATS subject compatibility
    if (user?.id) {
      const sanitizedUserId = user.id.replace(/:/g, '-');
      return headers.set('X-User-Subject', sanitizedUserId);
    }

    return headers;
  }

  get<T>(url: string, useAgentApi = false): Observable<T> {
    const baseUrl = useAgentApi ? this.agentApiUrl : this.apiUrl;
    const fullUrl = `${baseUrl}${url}`;
    const headers = this.getHeaders();
    console.log(`GET ${fullUrl}`, { headers: headers.keys() });
    return this.http.get<T>(fullUrl, { headers })
      .pipe(catchError(this.handleError));
  }

  post<T>(url: string, body: any, useAgentApi = false): Observable<T> {
    const baseUrl = useAgentApi ? this.agentApiUrl : this.apiUrl;
    return this.http.post<T>(`${baseUrl}${url}`, body, { headers: this.getHeaders() })
      .pipe(catchError(this.handleError));
  }

  private handleError(error: HttpErrorResponse) {
    if (error.error instanceof ErrorEvent) {
      console.error('An error occurred:', error.error.message);
    } else {
      console.error(`Backend returned code ${error.status}, body was:`, error.error);
    }
    return throwError(() => 'Something bad happened; please try again later.');
  }
}
