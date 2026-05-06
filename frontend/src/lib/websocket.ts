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
        } catch (error)