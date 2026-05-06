/**
 * WebSocket client for real-time Aurora Flux updates.
 * Handles connection lifecycle, reconnection, and heartbeat.
 */

import type { WSMessage, WSEventType } from '@/types';

type MessageHandler = (data: Record<string, unknown>, timestamp: string) => void;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: Map<WSEventType, Set<MessageHandler>> = new Map();
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 20;
  private baseReconnectDelay: number = 1000;
  private maxReconnectDelay: number = 30000;
  private heartbeatInterval: number | null = null;
  private heartbeatTimeout: number | null = null;
  private intentionalClose: boolean = false;
  private connected: boolean = false;

  constructor(url?: string) {
    this.url = url || process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';
  }

  // ── Connection Management ──────────────────────────────

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    if (this.ws?.readyState === WebSocket.CONNECTING) return;

    this.intentionalClose = false;

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.connected = true;
        this.reconnectAttempts = 0;
        this.startHeartbeat();
        this.notifyHandlers('state_update', { status: 'connected' }, new Date().toISOString());
        console.log('[WS] Connected to Aurora Flux');
      };

      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const message: WSMessage = JSON.parse(event.data as string);
          this.handleMessage(message);
        } catch (error) {
          console.error('[WS] Failed to parse message:', error);
        }
      };

      this.ws.onclose = (event: CloseEvent) => {
        this.connected = false;
        this.stopHeartbeat();
        console.log(`[WS] Disconnected — code: ${event.code}, reason: ${event.reason}`);

        if (!this.intentionalClose) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = (error: Event) => {
        console.error('[WS] Connection error:', error);
      };
    } catch (error) {
      console.error('[WS] Failed to create WebSocket:', error);
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    this.intentionalClose = true;
    this.stopHeartbeat();
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
    this.connected = false;
    this.reconnectAttempts = 0;
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[WS] Max reconnection attempts reached');
      this.notifyHandlers('error_alert', {
        message: 'Connection lost — max reconnection attempts reached',
      }, new Date().toISOString());
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(
      this.baseReconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1),
      this.maxReconnectDelay
    );

    console.log(
      `[WS] Reconnecting in ${Math.round(delay / 1000)}s... ` +
      `(attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`
    );

    setTimeout(() => this.connect(), delay);
  }

  // ── Heartbeat ──────────────────────────────────────────

  private startHeartbeat(): void {
    this.stopHeartbeat();

    this.heartbeatInterval = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send('ping');

        // Set timeout for pong response
        this.heartbeatTimeout = window.setTimeout(() => {
          console.warn('[WS] Heartbeat timeout — reconnecting');
          this.ws?.close(4000, 'Heartbeat timeout');
        }, 10000);
      }
    }, 25000); // Every 25 seconds
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
    if (this.heartbeatTimeout) {
      clearTimeout(this.heartbeatTimeout);
      this.heartbeatTimeout = null;
    }
  }

  // ── Message Handling ───────────────────────────────────

  private handleMessage(message: WSMessage): void {
    const { type, data, timestamp } = message;

    // Handle pong (heartbeat response)
    if (type === 'heartbeat') {
      if (this.heartbeatTimeout) {
        clearTimeout(this.heartbeatTimeout);
        this.heartbeatTimeout = null;
      }
      return;
    }

    this.notifyHandlers(type, data as Record<string, unknown>, timestamp);
  }

  private notifyHandlers(
    type: WSEventType,
    data: Record<string, unknown>,
    timestamp: string
  ): void {
    const handlers = this.handlers.get(type);
    if (!handlers) return;

    handlers.forEach((handler) => {
      try {
        handler(data, timestamp);
      } catch (error) {
        console.error(`[WS] Handler error for ${type}:`, error);
      }
    });
  }

  // ── Event Subscription ────────────────────────────────

  on(type: WSEventType, handler: MessageHandler): () => void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set());
    }
    this.handlers.get(type)!.add(handler);

    // Return unsubscribe function
    return () => {
      const handlers = this.handlers.get(type);
      if (handlers) {
        handlers.delete(handler);
        if (handlers.size === 0) {
          this.handlers.delete(type);
        }
      }
    };
  }

  // Subscribe to multiple event types
  onMany(types: WSEventType[], handler: MessageHandler): () => void {
    const unsubscribers = types.map((type) => this.on(type, handler));
    return () => unsubscribers.forEach((unsub) => unsub());
  }

  // ── Send ──────────────────────────────────────────────

  send(data: unknown): boolean {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
      return true;
    }
    return false;
  }

  // ── Status ────────────────────────────────────────────

  isConnected(): boolean {
    return this.connected && this.ws?.readyState === WebSocket.OPEN;
  }

  getState(): 'connecting' | 'connected' | 'disconnected' | 'reconnecting' {
    if (this.isConnected()) return 'connected';
    if (this.ws?.readyState === WebSocket.CONNECTING) return 'connecting';
    if (this.reconnectAttempts > 0 && !this.intentionalClose) return 'reconnecting';
    return 'disconnected';
  }

  getStats(): {
    connected: boolean;
    state: string;
    reconnectAttempts: number;
    url: string;
  } {
    return {
      connected: this.connected,
      state: this.getState(),
      reconnectAttempts: this.reconnectAttempts,
      url: this.url,
    };
  }
}

// Singleton instance
let wsClient: WebSocketClient | null = null;

export function getWebSocket(): WebSocketClient {
  if (!wsClient) {
    wsClient = new WebSocketClient();
  }
  return wsClient;
}

export function initWebSocket(url?: string): WebSocketClient {
  wsClient = new WebSocketClient(url);
  wsClient.connect();
  return wsClient;
}

export { WebSocketClient };
export default WebSocketClient;