'use client';

import React from 'react';
import { cn } from '@/lib/utils';
import { Loader2 } from 'lucide-react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'outline';
  size?: 'xs' | 'sm' | 'md' | 'lg';
  loading?: boolean;
  loadingText?: string;
  icon?: React.ReactNode;
  fullWidth?: boolean;
  holdDuration?: number; // Hold-to-confirm duration in ms
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  loadingText,
  icon,
  fullWidth = false,
  holdDuration,
  className,
  children,
  disabled,
  onMouseDown,
  onMouseUp,
  onMouseLeave,
  onClick,
  ...props
}: ButtonProps) {
  const [holding, setHolding] = React.useState(false);
  const [holdProgress, setHoldProgress] = React.useState(0);
  const holdTimerRef = React.useRef<NodeJS.Timeout | null>(null);
  const holdIntervalRef = React.useRef<NodeJS.Timeout | null>(null);

  const handleMouseDown = (e: React.MouseEvent<HTMLButtonElement>) => {
    onMouseDown?.(e);
    if (holdDuration && !disabled && !loading) {
      setHolding(true);
      setHoldProgress(0);
      const startTime = Date.now();
      holdIntervalRef.current = setInterval(() => {
        const elapsed = Date.now() - startTime;
        setHoldProgress(Math.min(100, (elapsed / holdDuration) * 100));
      }, 50);
      holdTimerRef.current = setTimeout(() => {
        setHolding(false);
        setHoldProgress(0);
        onClick?.(e as unknown as React.MouseEvent<HTMLButtonElement>);
      }, holdDuration);
    }
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLButtonElement>) => {
    onMouseUp?.(e);
    if (holdTimerRef.current) {
      clearTimeout(holdTimerRef.current);
      holdTimerRef.current = null;
    }
    if (holdIntervalRef.current) {
      clearInterval(holdIntervalRef.current);
      holdIntervalRef.current = null;
    }
    setHolding(false);
    setHoldProgress(0);
    if (!holdDuration) {
      onClick?.(e);
    }
  };

  const handleMouseLeave = (e: React.MouseEvent<HTMLButtonElement>) => {
    onMouseLeave?.(e);
    if (holdTimerRef.current) {
      clearTimeout(holdTimerRef.current);
      holdTimerRef.current = null;
    }
    if (holdIntervalRef.current) {
      clearInterval(holdIntervalRef.current);
      holdIntervalRef.current = null;
    }
    setHolding(false);
    setHoldProgress(0);
  };

  const baseStyles =
    'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-surface-900 disabled:opacity-50 disabled:cursor-not-allowed select-none';

  const variants = {
    primary:
      'bg-aurora-600 hover:bg-aurora-500 text-white focus:ring-aurora-500 shadow-lg shadow-aurora-600/20',
    secondary:
      'bg-surface-700 hover:bg-surface-600 text-gray-200 focus:ring-gray-500',
    danger:
      'bg-red-600 hover:bg-red-500 text-white focus:ring-red-500 shadow-lg shadow-red-600/20',
    ghost: 'bg-transparent hover:bg-surface-700 text-gray-300 focus:ring-gray-500',
    outline:
      'border border-surface-600 hover:border-surface-500 text-gray-300 bg-transparent focus:ring-gray-500',
  };

  const sizes = {
    xs: 'px-2 py-1 text-xs gap-1',
    sm: 'px-3 py-1.5 text-sm gap-1.5',
    md: 'px-4 py-2 text-sm gap-2',
    lg: 'px-6 py-3 text-base gap-2',
  };

  return (
    <button
      className={cn(
        baseStyles,
        variants[variant],
        sizes[size],
        fullWidth && 'w-full',
        holding && 'ring-2 ring-aurora-500',
        className
      )}
      disabled={disabled || loading}
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseLeave}
      {...props}
    >
      {loading ? (
        <>
          <Loader2 className="h-4 w-4 animate-spin" />
          {loadingText || children}
        </>
      ) : (
        <>
          {icon}
          {children}
        </>
      )}
      {holding && holdDuration && (
        <div
          className="absolute bottom-0 left-0 h-1 bg-aurora-500 rounded-b-lg transition-all"
          style={{ width: `${holdProgress}%` }}
        />
      )}
    </button>
  );
}