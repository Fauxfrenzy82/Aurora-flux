/**
 * Utility functions for formatting and display.
 */

// ── Number Formatting ─────────────────────────────────────

export function formatCurrency(
  value: number,
  currency: string = 'USD',
  decimals: number = 2
): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatCompactCurrency(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(2)}M`;
  }
  if (Math.abs(value) >= 1_000) {
    return `$${(value / 1_000).toFixed(1)}K`;
  }
  return `$${value.toFixed(2)}`;
}

export function formatPips(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(1)} pips`;
}

export function formatPercent(value: number, decimals: number = 2): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

export function formatLargeNumber(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return value.toFixed(0);
}

// ── Time Formatting ───────────────────────────────────────

export function formatTimeAgo(timestamp: string): string {
  const now = new Date();
  const date = new Date(timestamp);
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return date.toLocaleDateString();
}

export function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  }
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return `${days}d ${hours}h`;
}

// ── CSS Helpers ───────────────────────────────────────────

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

// ── Color Helpers ─────────────────────────────────────────

export function getDirectionColor(direction: string): string {
  return direction === 'LONG' ? 'text-long' : 'text-short';
}

export function getDirectionBg(direction: string): string {
  return direction === 'LONG' ? 'bg-long/20' : 'bg-short/20';
}

export function getRegimeColor(regime: string): string {
  const colorMap: Record<string, string> = {
    TRENDING_UP: 'text-regime-trending_up',
    STRONG_TREND_UP: 'text-regime-trending_up',
    TRENDING_DOWN: 'text-regime-trending_down',
    STRONG_TREND_DOWN: 'text-regime-trending_down',
    RANGE_BOUND: 'text-regime-range',
    VOLATILITY_EXPANSION: 'text-regime-volatile',
    VOLATILITY_CONTRACTION: 'text-regime-volatile',
    TRANSITION: 'text-regime-transition',
    RISK_OFF: 'text-regime-risk_off',
    UNCERTAIN: 'text-regime-uncertain',
  };
  return colorMap[regime] || 'text-gray-400';
}

export function getStatusColor(status: string): string {
  const colorMap: Record<string, string> = {
    ACTIVE: 'bg-green-500',
    TESTING: 'bg-blue-500',
    SUSPENDED: 'bg-yellow-500',
    RETIRED: 'bg-gray-500',
    APPROVED: 'bg-green-500',
    REJECTED: 'bg-red-500',
    PENDING: 'bg-yellow-500',
    WIN: 'bg-green-500',
    LOSS: 'bg-red-500',
    BREAKEVEN: 'bg-gray-500',
  };
  return colorMap[status] || 'bg-gray-500';
}

// ── Drawdown Severity ─────────────────────────────────────

export function getDrawdownSeverity(
  current: number,
  max: number
): 'safe' | 'warning' | 'danger' | 'critical' {
  const ratio = max > 0 ? current / max : 0;
  if (ratio >= 1.0) return 'critical';
  if (ratio >= 0.75) return 'danger';
  if (ratio >= 0.5) return 'warning';
  return 'safe';
}

export function getDrawdownColor(severity: string): string {
  const colorMap: Record<string, string> = {
    safe: '#22c55e',
    warning: '#f59e0b',
    danger: '#f97316',
    critical: '#ef4444',
  };
  return colorMap[severity] || '#9ca3af';
}

// ── Truncation ────────────────────────────────────────────

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return str.slice(0, length - 3) + '...';
}

export function truncateMiddle(str: string, startChars: number, endChars: number): string {
  if (str.length <= startChars + endChars + 3) return str;
  return `${str.slice(0, startChars)}...${str.slice(-endChars)}`;
}

// ── ID Generation ─────────────────────────────────────────

export function generateId(): string {
  return `ui_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

// ── Debounce ──────────────────────────────────────────────

export function debounce<T extends (...args: unknown[]) => void>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let timer: NodeJS.Timeout;
  return (...args: Parameters<T>) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

// ── Local Storage Helpers ─────────────────────────────────

export function getStorageItem<T>(key: string, defaultValue: T): T {
  if (typeof window === 'undefined') return defaultValue;
  try {
    const item = localStorage.getItem(key);
    return item ? (JSON.parse(item) as T) : defaultValue;
  } catch {
    return defaultValue;
  }
}

export function setStorageItem(key: string, value: unknown): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage full or unavailable
  }
}

// ── Copy to Clipboard ─────────────────────────────────────

export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand('copy');
      return true;
    } catch {
      return false;
    } finally {
      document.body.removeChild(textarea);
    }
  }
}