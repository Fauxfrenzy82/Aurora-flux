'use client';

import React from 'react';
import { useSystemStore } from '@/stores/useSystemStore';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { sendControl } from '@/lib/api';
import { cn, formatCurrency } from '@/lib/utils';
import {
  Lock,
  Unlock,
  TrendingUp,
  AlertTriangle,
  Zap,
  Shield,
} from 'lucide-react';

interface ModeToggleProps {
  className?: string;
}

export function ModeToggle({ className }: ModeToggleProps) {
  const { mode, phaseDay, dailyPnL, equity, setMode } = useSystemStore();
  const [switching, setSwitching] = React.useState(false);
  const [showConfirm, setShowConfirm] = React.useState(false);

  const isPhaseComplete = phaseDay > 5;
  const isProfitableEnough = dailyPnL > 0 && (dailyPnL / equity) > 0.02;
  const canUnlockFreedom = isPhaseComplete && isProfitableEnough;

  const handleSwitchToFreedom = async () => {
    if (!canUnlockFreedom) return;

    setSwitching(true);
    try {
      const result = await sendControl('switch_mode', { mode: 'FREEDOM' });
      if (result.status === 'switched') {
        setMode('FREEDOM');
        setShowConfirm(false);
      }
    } catch (error) {
      console.error('Failed to switch mode:', error);
    } finally {
      setSwitching(false);
    }
  };

  const handleSwitchToPhase = async () => {
    setSwitching(true);
    try {
      const result = await sendControl('switch_mode', { mode: 'PHASE' });
      if (result.status === 'switched') {
        setMode('PHASE');
        setShowConfirm(false);
      }
    } catch (error) {
      console.error('Failed to switch mode:', error);
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div className={cn('relative', className)}>
      {mode === 'PHASE' ? (
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500/10 rounded-lg border border-blue-500/30">
            <Lock className="h-3.5 w-3.5 text-blue-400" />
            <span className="text-xs font-medium text-blue-400">PHASE MODE</span>
            <Badge variant="info" size="sm" className="ml-1">
              Day {phaseDay}/5
            </Badge>
          </div>

          {canUnlockFreedom && !showConfirm && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowConfirm(true)}
              icon={<Unlock className="h-3.5 w-3.5" />}
            >
              Unlock Freedom
            </Button>
          )}

          {showConfirm && (
            <div className="absolute top-full right-0 mt-2 z-50 bg-surface-800 border border-surface-600 rounded-lg p-3 shadow-xl animate-fade-in min-w-[200px]">
              <p className="text-xs text-gray-300 mb-2">
                Unlock <span className="text-yellow-400 font-bold">FREEDOM MODE</span>?
                <br />
                <span className="text-gray-500">
                  No caps, full Kelly fraction, aggressive pyramiding.
                </span>
              </p>
              <div className="flex gap-2">
                <Button
                  variant="danger"
                  size="sm"
                  loading={switching}
                  onClick={handleSwitchToFreedom}
                >
                  Yes, Unlock
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowConfirm(false)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-yellow-500/10 rounded-lg border border-yellow-500/30 animate-pulse-slow">
            <Unlock className="h-3.5 w-3.5 text-yellow-400" />
            <span className="text-xs font-medium text-yellow-400">FREEDOM MODE</span>
            <Zap className="h-3 w-3 text-yellow-400" />
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleSwitchToPhase}
            icon={<Lock className="h-3.5 w-3.5" />}
          >
            Back to Phase
          </Button>
        </div>
      )}

      {/* Phase Progress Info */}
      {mode === 'PHASE' && (
        <div className="absolute -bottom-6 left-0 text-[10px] text-gray-500 whitespace-nowrap">
          {isPhaseComplete ? (
            <span className="text-green-400">Phase complete — ready to unlock Freedom</span>
          ) : (
            <span>{5 - phaseDay + 1} days remaining in Phase</span>
          )}
        </div>
      )}
    </div>
  );
}