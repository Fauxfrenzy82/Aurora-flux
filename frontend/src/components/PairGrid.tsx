'use client';

import React, { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

const ALL_PAIRS = [
    "frxEURUSD", "frxGBPUSD", "frxUSDJPY", "frxUSDCHF",
    "frxAUDUSD", "frxUSDCAD", "frxNZDUSD",
    "frxEURGBP", "frxEURJPY", "frxGBPJPY",
    "frxEURCHF", "frxGBPCHF", "frxAUDJPY",
    "R_10", "R_25", "R_50", "R_75", "R_100",
    "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V",
];

interface PairData {
    symbol: string;
    latest_regime: { regime: string; confidence: number; timestamp: string };
    regime_history: any[];
    recent_signals: any[];
    recent_trades: any[];
}

export function PairGrid() {
    const [pairs, setPairs] = useState<PairData[]>([]);
    const [expanded, setExpanded] = useState<string | null>(null);

    useEffect(() => {
        const fetchPairs = async () => {
            try {
                const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://aurora-flux-uc0m.onrender.com';
                const res = await fetch(`${API_URL}/api/pairs/detailed`);
                const data = await res.json();
                setPairs(data.pairs || []);
            } catch (e) { console.error(e); }
        };
        fetchPairs();
        const interval = setInterval(fetchPairs, 30000);
        return () => clearInterval(interval);
    }, []);

    const getRegimeColor = (regime: string) => {
        if (regime.includes('TRENDING_UP') || regime.includes('STRONG_TREND_UP')) return 'text-green-400';
        if (regime.includes('TRENDING_DOWN') || regime.includes('STRONG_TREND_DOWN')) return 'text-red-400';
        if (regime.includes('RANGE')) return 'text-yellow-400';
        if (regime.includes('VOLATILITY')) return 'text-purple-400';
        return 'text-gray-400';
    };

    const getRegimeBadge = (regime: string) => {
        if (regime.includes('TRENDING_UP') || regime.includes('STRONG_TREND_UP')) return 'success' as const;
        if (regime.includes('TRENDING_DOWN') || regime.includes('STRONG_TREND_DOWN')) return 'danger' as const;
        if (regime.includes('RANGE')) return 'warning' as const;
        return 'neutral' as const;
    };

    return (
        <Card variant="elevated" padding="md">
            <CardHeader>
                <CardTitle>Live Pair Analysis ({pairs.length}/23)</CardTitle>
                <span className="text-xs text-gray-500">Updates every 30s</span>
            </CardHeader>
            <CardContent>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
                    {pairs.map((pair) => (
                        <div
                            key={pair.symbol}
                            onClick={() => setExpanded(expanded === pair.symbol ? null : pair.symbol)}
                            className="p-2 bg-surface-700/50 rounded-lg cursor-pointer hover:bg-surface-700 transition-colors"
                        >
                            <p className="text-xs text-gray-400 font-mono truncate">
                                {pair.symbol.replace('frx', '')}
                            </p>
                            <Badge variant={getRegimeBadge(pair.latest_regime?.regime || 'UNKNOWN')} size="sm">
                                {pair.latest_regime?.regime?.replace(/_/g, ' ') || 'UNKNOWN'}
                            </Badge>
                            <p className={cn('text-xs mt-1', getRegimeColor(pair.latest_regime?.regime || ''))}>
                                {((pair.latest_regime?.confidence || 0) * 100).toFixed(0)}% conf
                            </p>
                            {pair.recent_signals?.length > 0 && (
                                <p className="text-xs text-aurora-400 mt-1">
                                    {pair.recent_signals.length} signals
                                </p>
                            )}
                            {pair.recent_trades?.length > 0 && (
                                <p className="text-xs text-green-400 mt-1">
                                    {pair.recent_trades.length} trades
                                </p>
                            )}
                        </div>
                    ))}
                    {pairs.length === 0 && (
                        <p className="col-span-full text-center text-gray-500 py-4">
                            Loading pair data...
                        </p>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}