'use client';

import React from 'react';
import { useSystemStore } from '@/stores/useSystemStore';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn, formatTimeAgo } from '@/lib/utils';
import type { Signal } from '@/types';
import {
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
} from 'lucide-react';

export function SignalFeed() {
  const { signals } = useSystemStore();
  const recentSignals = signals.slice(0, 20);

  return (
    <Card variant="default" padding="md" className="h-full">
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-yellow-400" />
            Signal Feed
          </span>
        </CardTitle>
        <Badge variant="neutral" size="sm">
          {signals.length} signals
        </Badge>
      </CardHeader>

      <div className="space-y-2 max-h-[400px] overflow-y-auto pr-1 custom-scrollbar">
        {recentSignals.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <Zap className="h-8 w-8 mx-auto mb-2 opacity-30" />
            <p className="text-sm">No signals yet</p>
            <p className="text-xs">Signals appear when strategies fire</p>
          </div>
        ) : (
          recentSignals.map((signal) => (
            <SignalItem key={signal.signal_id} signal={signal} />
          ))
        )}
      </div>
    </Card>
  );
}

function SignalItem({ signal }: { signal: Signal }) {
  const {
    symbol,
    direction,
    strategy_name,
    confidence,
    governance_result,
    rejection_reason,
    created_at,
  } = signal;

  const isApproved = governance_result === 'APPROVED';
  const isRejected = governance_result === 'REJECTED';
  const isLong = direction === 'LONG';

  return (
    <div
      className={cn(
        'flex items-center gap-3 p-2 rounded-lg transition-colors',
        'bg-surface-700/50 hover:bg-surface-700',
        isRejected && 'opacity-60'
      )}
    >
      {/* Direction Icon */}
      <div
        className={cn(
          'flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center',
          isLong ? 'bg-green-500/20' : 'bg-red-500/20'
        )}
      >
        {isLong ? (
          <TrendingUp className="h-4 w-4 text-green-400" />
        ) : (
          <TrendingDown className="h-4 w-4 text-red-400" />
        )}
      </div>

      {/* Signal Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-white font-mono">{symbol}</span>
          <Badge
            variant={isLong ? 'success' : 'danger'}
            size="sm"
          >
            {direction}
          </Badge>
          <span className="text-xs text-gray-400">
            {(confidence * 100).toFixed(0)}% conf
          </span>
        </div>
        <p className="text-xs text-gray-500 truncate">{strategy_name}</p>
      </div>

      {/* Governance Result */}
      <div className="flex-shrink-0">
        {isApproved && (
          <CheckCircle2 className="h-4 w-4 text-green-400" />
        )}
        {isRejected && (
          <div className="flex items-center gap-1" title={rejection_reason || ''}>
            <XCircle className="h-4 w-4 text-red-400" />
          </div>
        )}
        {!isApproved && !isRejected && (
          <Clock className="h-4 w-4 text-yellow-400 animate-pulse" />
        )}
      </div>

      {/* Timestamp */}
      <span className="flex-shrink-0 text-xs text-gray-600 w-12 text-right">
        {formatTimeAgo(created_at)}
      </span>
    </div>
  );
}