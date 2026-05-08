'use client';

import React, { useEffect, useState, useRef } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface LogEntry {
    type: string;
    timestamp: string;
    symbol: string;
    data: string;
}

export function ActivityLog() {
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const fetchLogs = async () => {
            try {
                const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://aurora-flux-uc0m.onrender.com';
                const res = await fetch(`${API_URL}/api/activity/logs?limit=50`);
                const data = await res.json();
                setLogs(data.logs || []);
            } catch (e) { console.error(e); }
        };
        fetchLogs();
        const interval = setInterval(fetchLogs, 10000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logs]);

    const getTypeColor = (type: string) => {
        switch (type) {
            case 'regime': return 'text-blue-400';
            case 'signal': return 'text-yellow-400';
            case 'trade': return 'text-green-400';
            case 'event': return 'text-gray-400';
            default: return 'text-gray-400';
        }
    };

    const getTypeIcon = (type: string) => {
        switch (type) {
            case 'regime': return '📊';
            case 'signal': return '⚡';
            case 'trade': return '💱';
            case 'event': return 'ℹ️';
            default: return '•';
        }
    };

    const formatTime = (ts: string) => {
        if (!ts) return '';
        const d = new Date(ts);
        return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    };

    return (
        <Card variant="elevated" padding="md">
            <CardHeader>
                <CardTitle>System Activity Log</CardTitle>
                <span className="text-xs text-gray-500">{logs.length} entries</span>
            </CardHeader>
            <CardContent>
                <div className="max-h-[400px] overflow-y-auto custom-scrollbar space-y-1">
                    {logs.length === 0 ? (
                        <p className="text-center text-gray-500 py-4">No activity yet</p>
                    ) : (
                        logs.map((log, i) => (
                            <div
                                key={i}
                                className="flex items-start gap-2 p-1.5 rounded hover:bg-surface-700/50 transition-colors text-xs"
                            >
                                <span className="flex-shrink-0">{getTypeIcon(log.type)}</span>
                                <span className="flex-shrink-0 text-gray-600 font-mono w-16">
                                    {formatTime(log.timestamp)}
                                </span>
                                {log.symbol && (
                                    <span className="flex-shrink-0 font-mono text-gray-400 w-20 truncate">
                                        {log.symbol.replace('frx', '')}
                                    </span>
                                )}
                                <span className={cn('flex-1', getTypeColor(log.type))}>
                                    {log.data}
                                </span>
                            </div>
                        ))
                    )}
                    <div ref={bottomRef} />
                </div>
            </CardContent>
        </Card>
    );
}