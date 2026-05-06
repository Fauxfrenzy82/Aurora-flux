'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useSystemStore } from '@/stores/useSystemStore';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn, formatTimestamp, generateId } from '@/lib/utils';
import { sendChatMessage } from '@/lib/api';
import type { ChatMessage } from '@/types';
import {
  Send,
  Bot,
  User,
  Loader2,
  Zap,
  Shield,
  TrendingUp,
  Activity,
  Settings,
  Sparkles,
  Trash2,
} from 'lucide-react';

export default function ChatPage() {
  const { chatMessages, addChatMessage, equity, mode, regime, drawdownPct, positions } = useSystemStore();
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [chatMessages, scrollToBottom]);

  const handleSend = async () => {
    const message = input.trim();
    if (!message || loading) return;

    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    };
    addChatMessage(userMsg);
    setInput('');
    setLoading(true);

    try {
      const response = await sendChatMessage(message);
      const sysMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: response.response,
        timestamp: new Date().toISOString(),
        category: detectCategory(message),
      };
      addChatMessage(sysMsg);
    } catch (error) {
      const errorMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date().toISOString(),
      };
      addChatMessage(errorMsg);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleQuickCommand = (command: string) => {
    setInput(command);
    inputRef.current?.focus();
  };

  const handleClearChat = () => {
    localStorage.removeItem('aurora_chat_history');
    window.location.reload();
  };

  return (
    <div className="flex flex-col h-[calc(100vh-80px)]">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Aurora Chat</h1>
          <p className="text-sm text-gray-400">Ask about system status, trades, risk, and strategies</p>
        </div>
        <Button variant="ghost" size="sm" onClick={handleClearChat} icon={<Trash2 className="h-4 w-4" />}>
          Clear Chat
        </Button>
      </div>

      {/* System Context Bar */}
      <div className="flex flex-wrap gap-2 mb-4 p-3 bg-surface-800/50 rounded-lg">
        <Badge variant="info" size="sm">
          Equity: ${equity.toFixed(2)}
        </Badge>
        <Badge variant={mode === 'PHASE' ? 'info' : 'warning'} size="sm">
          Mode: {mode}
        </Badge>
        <Badge variant="neutral" size="sm">
          Regime: {regime}
        </Badge>
        <Badge variant={drawdownPct > 0.05 ? 'danger' : 'neutral'} size="sm">
          DD: {(drawdownPct * 100).toFixed(1)}%
        </Badge>
        <Badge variant="neutral" size="sm">
          Positions: {positions.length}
        </Badge>
      </div>

      {/* Quick Commands */}
      <div className="flex flex-wrap gap-2 mb-4">
        {['/status', '/positions', '/risk', '/strategies', '/trades', '/evolution', '/regime', '/help'].map((cmd) => (
          <button
            key={cmd}
            onClick={() => handleQuickCommand(cmd)}
            className="px-2 py-1 text-xs bg-surface-700 hover:bg-surface-600 text-gray-400 hover:text-gray-200 rounded-md transition-colors font-mono"
          >
            {cmd}
          </button>
        ))}
      </div>

      {/* Messages Container */}
      <Card variant="elevated" padding="none" className="flex-1 overflow-hidden flex flex-col">
        <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
          {chatMessages.length === 0 && (
            <div className="text-center py-12">
              <Bot className="h-16 w-16 mx-auto mb-4 text-gray-600" />
              <h3 className="text-lg font-semibold text-white">Welcome to Aurora Chat</h3>
              <p className="text-sm text-gray-400 mt-2 max-w-md mx-auto">
                I can help you monitor the trading system, explain strategies, check risk metrics, 
                and provide real-time insights.
              </p>
              <div className="flex flex-wrap justify-center gap-2 mt-6">
                <button
                  onClick={() => handleQuickCommand("How are we doing today?")}
                  className="px-3 py-1.5 text-xs bg-surface-700 hover:bg-surface-600 rounded-lg transition-colors"
                >
                  📊 How are we doing?
                </button>
                <button
                  onClick={() => handleQuickCommand("Show active strategies")}
                  className="px-3 py-1.5 text-xs bg-surface-700 hover:bg-surface-600 rounded-lg transition-colors"
                >
                  🧬 Show active strategies
                </button>
                <button
                  onClick={() => handleQuickCommand("What's the current risk level?")}
                  className="px-3 py-1.5 text-xs bg-surface-700 hover:bg-surface-600 rounded-lg transition-colors"
                >
                  🛡️ Current risk level?
                </button>
              </div>
            </div>
          )}

          {chatMessages.map((msg) => (
            <ChatBubble key={msg.id} message={msg} />
          ))}

          {loading && (
            <div className="flex items-center gap-2 p-3 text-gray-400">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">Aurora is thinking...</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="p-4 border-t border-surface-700">
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder="Ask anything... (Shift+Enter for new line)"
              disabled={loading}
              rows={2}
              className="flex-1 px-3 py-2 text-sm bg-surface-700 border border-surface-600 rounded-lg text-gray-200 placeholder-gray-500 focus:outline-none focus:border-aurora-500 disabled:opacity-50 resize-none"
            />
            <Button
              variant="primary"
              onClick={handleSend}
              disabled={!input.trim() || loading}
              icon={<Send className="h-4 w-4" />}
              className="self-end"
            >
              Send
            </Button>
          </div>
          <p className="text-xs text-gray-600 mt-2">
            Commands: /status, /positions, /risk, /strategies, /trades, /evolution, /regime, /help
          </p>
        </div>
      </Card>
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'assistant';

  const getCategoryIcon = () => {
    switch (message.category) {
      case 'status':
        return <Activity className="h-3 w-3" />;
      case 'risk':
        return <Shield className="h-3 w-3" />;
      case 'trade':
        return <TrendingUp className="h-3 w-3" />;
      case 'strategy':
        return <Zap className="h-3 w-3" />;
      case 'evolution':
        return <Sparkles className="h-3 w-3" />;
      case 'control':
        return <Settings className="h-3 w-3" />;
      default:
        return null;
    }
  };

  return (
    <div className={cn('flex gap-3', isUser ? 'justify-end' : 'justify-start')}>
      {isSystem && (
        <div className="flex-shrink-0 h-8 w-8 rounded-full bg-aurora-600/20 flex items-center justify-center">
          <Bot className="h-4 w-4 text-aurora-400" />
        </div>
      )}

      <div
        className={cn(
          'max-w-[80%] rounded-2xl px-4 py-3',
          isUser
            ? 'bg-aurora-600 text-white rounded-br-none'
            : 'bg-surface-700 text-gray-200 rounded-bl-none'
        )}
      >
        {message.category && (
          <div className="flex items-center gap-1 mb-1">
            {getCategoryIcon()}
            <span className="text-xs text-gray-400 uppercase tracking-wider">{message.category}</span>
          </div>
        )}
        <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>
        <p className="text-xs mt-2 opacity-60">{formatTimestamp(message.timestamp)}</p>
      </div>

      {isUser && (
        <div className="flex-shrink-0 h-8 w-8 rounded-full bg-surface-600 flex items-center justify-center">
          <User className="h-4 w-4 text-gray-300" />
        </div>
      )}
    </div>
  );
}

function detectCategory(message: string): ChatMessage['category'] {
  const msg = message.toLowerCase();
  if (msg.includes('status') || msg.includes('equity') || msg.includes('doing') || msg.includes('health')) return 'status';
  if (msg.includes('trade') || msg.includes('profit') || msg.includes('loss') || msg.includes('win') || msg.includes('pnl')) return 'trade';
  if (msg.includes('strategy') || msg.includes('dna') || msg.includes('evolution') || msg.includes('breed')) return 'strategy';
  if (msg.includes('risk') || msg.includes('drawdown') || msg.includes('exposure') || msg.includes('size')) return 'risk';
  if (msg.includes('halt') || msg.includes('close') || msg.includes('mode') || msg.includes('control')) return 'control';
  if (msg.includes('market') || msg.includes('regime') || msg.includes('session') || msg.includes('news')) return 'market';
  if (msg.includes('evolve') || msg.includes('gen') || msg.includes('population')) return 'evolution';
  return undefined;
}