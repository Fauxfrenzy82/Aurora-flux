'use client';

import React from 'react';
import { cn } from '@/lib/utils';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  variant?: 'default' | 'elevated' | 'bordered' | 'glow';
  padding?: 'none' | 'sm' | 'md' | 'lg';
  onClick?: () => void;
  hover?: boolean;
}

export function Card({
  children,
  className,
  variant = 'default',
  padding = 'md',
  onClick,
  hover = false,
}: CardProps) {
  const baseStyles = 'rounded-xl transition-all duration-200';

  const variants = {
    default: 'bg-surface-800/80 backdrop-blur-sm',
    elevated: 'bg-surface-800 shadow-xl shadow-black/20',
    bordered: 'bg-surface-800/80 border border-surface-700',
    glow: 'bg-surface-800/80 border border-aurora-600/30 shadow-lg shadow-aurora-600/10',
  };

  const paddings = {
    none: '',
    sm: 'p-3',
    md: 'p-4',
    lg: 'p-6',
  };

  return (
    <div
      className={cn(
        baseStyles,
        variants[variant],
        paddings[padding],
        hover && 'hover:bg-surface-700/80 hover:border-surface-600 cursor-pointer',
        onClick && 'cursor-pointer',
        className
      )}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

// Card sub-components
export function CardHeader({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex items-center justify-between mb-3', className)}>
      {children}
    </div>
  );
}

export function CardTitle({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <h3 className={cn('text-sm font-semibold text-gray-200 uppercase tracking-wider', className)}>
      {children}
    </h3>
  );
}

export function CardContent({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn('', className)}>{children}</div>;
}

export function CardFooter({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('mt-3 pt-3 border-t border-surface-700', className)}>
      {children}
    </div>
  );
}