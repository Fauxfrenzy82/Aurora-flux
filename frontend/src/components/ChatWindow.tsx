'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useSystemStore } from '@/stores/useSystemStore';
import { Card } from '@/components/ui/card';
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
} from 'lucide-react';

interface ChatWindowProps {
  minimized?: boolean;
  onToggleMinimize?: () => void;
}

export function ChatWindow({ minimized = false, onToggleMinimize }: ChatWindowProps) {
  const { chatMessages, addChatMessage, equity, mode } = useSystemStore();
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [chatMessages, scrollToBottom]);

  const handleSend = async () => {
    const message = input.trim();
    if (!message || loading) return;

    // Add user message
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

      // Add system response
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

  if (minimized) return null;

  return (
    <Card variant="elevated" padding="none" className="flex flex-col h-[500px]">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-surface-700">
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-aurora-400" />
          <span className="text-sm font-semibold text-white">Aurora Chat</span>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="info" size="sm">
            Equity: ${equity.toFixed(2)}
          </Badge>
          {onToggleMinimize && (
            <Button variant="ghost" size="xs" onClick={onToggleMinimize}>
              —
            </Button>
          )}
        </div>
      </div>

      {/* Quick Commands */}
      <div className="flex gap-1 px-3 py-2 overflow-x-auto border-b border-surface-700/50">
        {['/status', '/positions', '/risk', '/strategies', '/halt', '/help'].map(
          (cmd) => (
            <button
              key={cmd}
              onClick={() => handleQuickCommand(cmd)}
              className="flex-shrink-0 px-2 py-0.5 text-xs bg-surface-700 hover:bg-surface-600 text-gray-400 hover:text-gray-200 rounded-md transition-colors"
            >
              {cmd}
            </button>
          )
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 custom-scrollbar">
        {chatMessages.length === 0 && (
          <div className="text-center py-8">
            <Bot className="h-12 w-12 mx-auto mb-3 text-gray-600" />
            <p className="text-sm text-gray-500">Ask me anything about the system</p>
            <p className="text-xs text-gray-600 mt-1">
              Try: "How are we doing?" or "Show today's trades"
            </p>
          </div>
        )}

        {chatMessages.map((msg) => (
          <ChatBubble key={msg.id} message={msg} />
        ))}

        {loading && (
          <div className="flex items-center gap-2 p-3 text-gray-400">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-sm">Thinking...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-surface-700">
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about status, trades, risk, strategies..."
            disabled={loading}
            className="flex-1 px-3 py-2 text-sm bg-surface-700 border border-surface-600 rounded-lg text-gray-200 placeholder-gray-500 focus:outline-none focus:border-aurora-500 disabled:opacity-50"
          />
          <Button
            variant="primary"
            size="sm"
            onClick={handleSend}
            disabled={!input.trim() || loading}
            icon={<Send className="h-4 w-4" />}
          >
            Send
          </Button>
        </div>
      </div>
    </Card>
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
      default:
        return null;
    }
  };

  return (
    <div
      className={cn(
        'flex gap-2',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
      {isSystem && (
        <div className="flex-shrink-0 h-8 w-8 rounded-full bg-aurora-600/20 flex items-center justify-center">
          <Bot className="h-4 w-4 text-aurora-400" />
        </div>
      )}

      <div
        className={cn(
          'max-w-[80%] rounded-lg px-3 py-2',
          isUser
            ? 'bg-aurora-600 text-white rounded-br-none'
            : 'bg-surface-700 text-gray-200 rounded-bl-none'
        )}
      >
        {message.category && (
          <div className="flex items-center gap-1 mb-1">
            {getCategoryIcon()}
            <span className="text-xs text-gray-400 uppercase">{message.category}</span>
          </div>
        )}
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        <p className="text-xs mt-1 opacity-60">
          {formatTimestamp(message.timestamp)}
        </p>
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
  if (msg.includes('status') || msg.includes('equity') || msg.includes('doing')) return 'status';
  if (msg.includes('trade') || msg.includes('profit') || msg.includes('loss')) return 'trade';
  if (msg.includes('strategy') || msg.includes('evolution')) return 'strategy';
  if (msg.includes('risk') || msg.includes('drawdown') || msg.includes('exposure')) return 'risk';
  if (msg.includes('halt') || msg.includes('close') || msg.includes('mode')) return 'control';
  if (msg.includes('market') || msg.includes('regime') || msg.includes('session')) return 'market';
  return undefined;
}