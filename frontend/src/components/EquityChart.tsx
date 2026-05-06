'use client';

import React, { useState, useEffect, useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Area,
  AreaChart,
} from 'recharts';
import { useSystemStore } from '@/stores/useSystemStore';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatCurrency, formatTimestamp } from '@/lib/utils';
import { TrendingUp } from 'lucide-react';

type Period = '1D' | '7D' | '30D' | '90D' | 'ALL';

interface ChartDataPoint {
  timestamp: string;
  equity: number;
  balance: number;
  drawdown: number;
}

export function EquityChart() {
  const { equityHistory, balance, equity } = useSystemStore();
  const [period, setPeriod] = useState<Period>('7D');
  const [isHovered, setIsHovered] = useState(false);

  const chartData: ChartDataPoint[] = useMemo(() => {
    if (equityHistory.length === 0) {
      // Generate placeholder data
      const now = new Date();
      const data: ChartDataPoint[] = [];
      for (let i = 30; i >= 0; i--) {
        const time = new Date(now.getTime() - i * 3600000);
        data.push({
          timestamp: time.toISOString(),
          equity: 10 + Math.random() * 0.5,
          balance: 10,
          drawdown: Math.random() * 0.02,
        });
      }
      return data;
    }

    return equityHistory.map((point) => ({
      timestamp: point.timestamp,
      equity: point.equity,
      balance: balance || point.equity,
      drawdown: 0,
    }));
  }, [equityHistory, balance]);

  const filteredData = useMemo(() => {
    const now = new Date();
    const periods: Record<Period, number> = {
      '1D': 24 * 60 * 60 * 1000,
      '7D': 7 * 24 * 60 * 60 * 1000,
      '30D': 30 * 24 * 60 * 60 * 1000,
      '90D': 90 * 24 * 60 * 60 * 1000,
      'ALL': Infinity,
    };

    const cutoff = new Date(now.getTime() - periods[period]);
    return chartData.filter((d) => new Date(d.timestamp) >= cutoff);
  }, [chartData, period]);

  const pnl = filteredData.length >= 2
    ? filteredData[filteredData.length - 1].equity - filteredData[0].equity
    : 0;

  const pnlPercent = filteredData.length >= 2 && filteredData[0].equity > 0
    ? (pnl / filteredData[0].equity) * 100
    : 0;

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-surface-800 border border-surface-600 rounded-lg p-3 shadow-xl">
          <p className="text-xs text-gray-400 mb-1">{formatTimestamp(label)}</p>
          <p className="text-sm font-mono text-white font-bold">
            {formatCurrency(payload[0].value)}
          </p>
          {payload[0].payload.balance && (
            <p className="text-xs text-gray-500">
              Balance: {formatCurrency(payload[0].payload.balance)}
            </p>
          )}
        </div>
      );
    }
    return null;
  };

  const startingEquity = filteredData.length > 0 ? filteredData[0].equity : equity;

  return (
    <Card variant="elevated" padding="md" className="h-full">
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-aurora-400" />
            Equity Curve
          </span>
        </CardTitle>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {(['1D', '7D', '30D', '90D', 'ALL'] as Period[]).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-2 py-0.5 text-xs rounded-md transition-colors ${
                  period === p
                    ? 'bg-aurora-600 text-white'
                    : 'bg-surface-700 text-gray-400 hover:bg-surface-600'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {/* P&L Summary */}
        <div className="flex items-center gap-4 mb-4">
          <div>
            <span className="text-xs text-gray-500">Period P&L</span>
            <p
              className={`text-lg font-mono font-bold ${
                pnl >= 0 ? 'text-green-400' : 'text-red-400'
              }`}
            >
              {pnl >= 0 ? '+' : ''}
              {formatCurrency(pnl)}
            </p>
          </div>
          <Badge variant={pnl >= 0 ? 'success' : 'danger'} size="sm">
            {pnlPercent >= 0 ? '+' : ''}
            {pnlPercent.toFixed(2)}%
          </Badge>
        </div>

        {/* Chart */}
        <div
          className="h-64 w-full"
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
        >
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={filteredData} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
              <defs>
                <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22c55e" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#22c55e" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#1f2937"
                vertical={false}
              />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(ts) => {
                  const date = new Date(ts);
                  return period === '1D'
                    ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    : date.toLocaleDateString([], { month: 'short', day: 'numeric' });
                }}
                stroke="#4b5563"
                fontSize={11}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                stroke="#4b5563"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => `$${value.toFixed(2)}`}
                domain={['auto', 'auto']}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine
                y={startingEquity}
                stroke="#4b5563"
                strokeDasharray="5 5"
                strokeWidth={1}
              />
              <Area
                type="monotone"
                dataKey="equity"
                stroke="#22c55e"
                strokeWidth={2}
                fill="url(#equityGradient)"
                animationDuration={1000}
                dot={false}
                activeDot={{
                  r: 4,
                  fill: '#22c55e',
                  stroke: '#0a0f1a',
                  strokeWidth: 2,
                }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}