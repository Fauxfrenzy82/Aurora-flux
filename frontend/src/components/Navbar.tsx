'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useSystemStore } from '@/stores/useSystemStore';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard,
  TrendingUp,
  Target,
  Dna,
  Shield,
  MessageSquare,
  Settings,
  Activity,
  Zap,
  Sparkles,
} from 'lucide-react';

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/positions', label: 'Positions', icon: TrendingUp },
  { path: '/trades', label: 'Trades', icon: Activity },
  { path: '/strategies', label: 'Strategies', icon: Dna },
  { path: '/risk', label: 'Risk', icon: Shield },
  { path: '/evolution', label: 'Evolution', icon: Sparkles },
  { path: '/chat', label: 'Chat', icon: MessageSquare },
  { path: '/settings', label: 'Settings', icon: Settings },
];

export function Navbar() {
  const pathname = usePathname();
  const { isConnected, scalpModeActive, halted, mode } = useSystemStore();

  return (
    <nav className="fixed left-0 top-0 bottom-0 w-64 bg-surface-900/95 border-r border-surface-700 flex flex-col z-40">
      {/* Logo */}
      <div className="p-4 border-b border-surface-700">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-aurora-600 flex items-center justify-center">
            <Zap className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white">AURORA FLUX</h1>
            <p className="text-[10px] text-gray-500">Autonomous Trading</p>
          </div>
        </div>

        {/* Status Indicators */}
        <div className="flex items-center gap-2 mt-3">
          <div
            className={cn(
              'h-2 w-2 rounded-full',
              isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400'
            )}
          />
          <span className="text-xs text-gray-400">
            {isConnected ? 'Online' : 'Offline'}
          </span>
          {scalpModeActive && (
            <Badge variant="warning" size="sm" dot pulse>
              SCALP
            </Badge>
          )}
          {halted && (
            <Badge variant="danger" size="sm" dot>
              HALT
            </Badge>
          )}
          <Badge
            variant={mode === 'PHASE' ? 'info' : 'warning'}
            size="sm"
          >
            {mode}
          </Badge>
        </div>
      </div>

      {/* Navigation */}
      <div className="flex-1 py-4">
        {navItems.map((item) => {
          const isActive = pathname === item.path;
          const Icon = item.icon;

          return (
            <Link
              key={item.path}
              href={item.path}
              className={cn(
                'flex items-center gap-3 px-4 py-2.5 mx-2 rounded-lg transition-colors',
                isActive
                  ? 'bg-aurora-600/20 text-aurora-400 border-l-2 border-aurora-500'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-surface-800'
              )}
            >
              <Icon className="h-4 w-4" />
              <span className="text-sm font-medium">{item.label}</span>
              {item.path === '/strategies' && (
                <span className="ml-auto text-xs text-gray-500">
                  {useSystemStore.getState().strategies.filter(s => s.status === 'ACTIVE').length}
                </span>
              )}
              {item.path === '/positions' && (
                <span className="ml-auto text-xs text-gray-500">
                  {useSystemStore.getState().positions.length}
                </span>
              )}
            </Link>
          );
        })}
      </div>

      {/* Version Footer */}
      <div className="p-4 border-t border-surface-700">
        <p className="text-[10px] text-gray-600 text-center">
          v{process.env.NEXT_PUBLIC_APP_VERSION || '1.0.0'}
          <br />
          Autonomous Evolution
        </p>
      </div>
    </nav>
  );
}