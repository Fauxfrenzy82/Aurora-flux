'use client';

import React from 'react';
import { cn } from '@/lib/utils';

interface ProgressProps {
  value: number; // 0-100
  max?: number;
  variant?: 'success' | 'danger' | 'warning' | 'info' | 'gradient';
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  labelFormat?: 'percent' | 'fraction' | 'custom';
  customLabel?: string;
  animated?: boolean;
  className?: string;
  barClassName?: string;
  marker?: number; // Position of a marker line (e.g., stop loss)
  markerLabel?: string;
}

export function Progress({
  value,
  max = 100,
  variant = 'success',
  size = 'md',
  showLabel = true,
  labelFormat = 'percent',
  customLabel,
  animated = true,
  className,
  barClassName,
  marker,
  markerLabel,
}: ProgressProps) {
  const percentage = Math.min(100, Math.max(0, (value / max) * 100));

  const variants = {
    success: 'bg-gradient-to-r from-aurora-600 to-aurora-400',
    danger: 'bg-gradient-to-r from-red-600 to-red-400',
    warning: 'bg-gradient-to-r from-yellow-600 to-yellow-400',
    info: 'bg-gradient-to-r from-blue-600 to-blue-400',
    gradient: 'bg-gradient-to-r from-aurora-500 via-yellow-500 to-red-500',
  };

  const sizes = {
    sm: 'h-1.5',
    md: 'h-2',
    lg: 'h-3',
  };

  const label = customLabel
    ? customLabel
    : labelFormat === 'percent'
      ? `${percentage.toFixed(1)}%`
      : `${value}/${max}`;

  return (
    <div className={cn('w-full', className)}>
      {showLabel && (
        <div className="flex justify-between items-center mb-1">
          <span className="text-xs text-gray-400">{label}</span>
          {markerLabel && (
            <span className="text-xs text-red-400">{markerLabel}</span>
          )}
        </div>
      )}
      <div
        className={cn(
          'relative w-full rounded-full bg-surface-700 overflow-hidden',
          sizes[size]
        )}
      >
        <div
          className={cn(
            'h-full rounded-full transition-all duration-700 ease-out',
            variants[variant],
            animated && 'animate-pulse-slow',
            barClassName
          )}
          style={{ width: `${percentage}%` }}
        />
        {marker !== undefined && (
          <div
            className="absolute top-0 h-full w-0.5 bg-white/50"
            style={{ left: `${(marker / max) * 100}%` }}
          />
        )}
      </div>
    </div>
  );
}