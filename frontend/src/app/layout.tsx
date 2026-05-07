'use client';

import React, { useEffect, useState } from 'react';
import { useSystemStore, initWebSocketStore } from '@/stores/useSystemStore';
import { getStatus, getStrategies, getPerformance, getSnapshots } from '@/lib/api';
import { Navbar } from '@/components/Navbar';
import { StatusBar } from '@/components/StatusBar';
import { ChatWindow } from '@/components/ChatWindow';
import { Button } from '@/components/ui/button';
import { Loader2, MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import './globals.css';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const { isLoading: storeLoading, setRefreshing } = useSystemStore();

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    let cancelled = false;

    const initialize = async () => {
      try {
        const [status, strategies, performance, snapshots] = await Promise.all([
          getStatus(),
          getStrategies(),
          getPerformance(),
          getSnapshots(100),
        ]);

        if (cancelled) return;

        const store = useSystemStore.getState();
        store.updateFromStatus(status);
        store.setStrategies(strategies);
        store.setPerformance(performance);
        store.setEquityHistory(snapshots);

        initWebSocketStore();

        interval = setInterval(async () => {
          if (cancelled || document.hidden) return;
          store.setRefreshing(true);
          try {
            const newStatus = await getStatus();
            if (!cancelled) store.updateFromStatus(newStatus);
          } catch (error) {
            console.error('Polling error:', error);
          } finally {
            if (!cancelled) store.setRefreshing(false);
          }
        }, 10000);

      } catch (error) {
        console.error('Initialization error:', error);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    initialize();

    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, []);

  if (isLoading || storeLoading) {
    return (
      <html lang="en">
        <body className="bg-surface-950">
          <div className="flex items-center justify-center h-screen">
            <div className="text-center">
              <Loader2 className="h-12 w-12 text-aurora-500 animate-spin mx-auto mb-4" />
              <p className="text-gray-400">Initializing Aurora Flux...</p>
              <p className="text-xs text-gray-600 mt-2">Connecting to trading engine</p>
            </div>
          </div>
        </body>
      </html>
    );
  }

  return (
    <html lang="en">
      <head>
        <title>Aurora Flux — Autonomous Trading</title>
        <meta name="description" content="Self-evolving Forex trading system" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#22c55e" />
      </head>
      <body className="bg-surface-950 text-gray-200">
        <Navbar />

        <div className="ml-64">
          <StatusBar />

          <main className="p-4 min-h-screen">
            {children}
          </main>
        </div>

        <button
          onClick={() => setIsChatOpen(!isChatOpen)}
          className="fixed bottom-4 right-4 z-50 h-12 w-12 rounded-full bg-aurora-600 hover:bg-aurora-500 text-white shadow-lg transition-all flex items-center justify-center"
        >
          <MessageSquare className="h-5 w-5" />
        </button>

        {isChatOpen && (
          <div className="fixed bottom-20 right-4 z-50 w-96 shadow-2xl">
            <ChatWindow
              minimized={false}
              onToggleMinimize={() => setIsChatOpen(false)}
            />
          </div>
        )}
      </body>
    </html>
  );
}