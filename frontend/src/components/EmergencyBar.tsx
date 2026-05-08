'use client';

import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useSystemStore } from '@/stores/useSystemStore';
import { cn } from '@/lib/utils';
import { ShieldAlert, ShieldCheck, TrendingDown, AlertTriangle } from 'lucide-react';

export function EmergencyBar() {
    const { halted, setHalted } = useSystemStore();
    const [loading, setLoading] = useState<string | null>(null);

    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://aurora-flux-uc0m.onrender.com';

    const sendCommand = async (action: string) => {
        setLoading(action);
        try {
            await fetch(`${API_URL}/api/control?action=${action}`, { method: 'POST' });
            if (action === 'halt') setHalted(true);
            if (action === 'resume') setHalted(false);
        } catch (e) { console.error(e); }
        finally { setLoading(null); }
    };

    return (
        <div className={cn(
            'fixed bottom-0 left-0 right-0 z-50 p-3 border-t',
            halted
                ? 'bg-red-900/90 border-red-500/50 backdrop-blur-sm'
                : 'bg-surface-900/90 border-surface-700 backdrop-blur-sm'
        )}>
            <div className="flex items-center justify-center gap-3">
                {halted ? (
                    <>
                        <Badge variant="danger" size="md" dot pulse>SYSTEM HALTED</Badge>
                        <Button
                            variant="primary"
                            size="sm"
                            onClick={() => sendCommand('resume')}
                            loading={loading === 'resume'}
                            icon={<ShieldCheck className="h-4 w-4" />}
                        >
                            Resume Trading
                        </Button>
                    </>
                ) : (
                    <>
                        <span className="text-xs text-gray-400 hidden sm:inline">Trading Active</span>
                        <Button
                            variant="danger"
                            size="sm"
                            holdDuration={3000}
                            onClick={() => sendCommand('halt')}
                            disabled={loading !== null}
                            icon={<ShieldAlert className="h-4 w-4" />}
                        >
                            Hold to Halt
                        </Button>
                    </>
                )}
                <Button
                    variant="danger"
                    size="sm"
                    holdDuration={3000}
                    onClick={() => sendCommand('close_all')}
                    disabled={loading !== null}
                    icon={<TrendingDown className="h-4 w-4" />}
                >
                    Hold to Close All
                </Button>
            </div>
        </div>
    );
}