import React from 'react';

export interface DataStatusBadgeProps {
  status: 'live' | 'cached' | 'error';
  label?: string;
  className?: string;
}

export const DataStatusBadge: React.FC<DataStatusBadgeProps> = ({
  status,
  label,
  className = '',
}) => {
  if (status === 'live') {
    return (
      <span
        className={`inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 font-mono text-xs font-bold tracking-wider uppercase shadow-[0_0_10px_rgba(16,185,129,0.3)] ${className}`}
        title="Connected to live FastAPI backend container"
      >
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
        </span>
        <span>{label || '● LIVE BACKEND'}</span>
      </span>
    );
  }

  if (status === 'error') {
    return (
      <span
        className={`inline-flex items-center gap-2 px-3 py-1 rounded-full bg-rose-500/15 border border-rose-500/40 text-rose-300 font-mono text-xs font-bold tracking-wider uppercase shadow-[0_0_10px_rgba(244,63,94,0.3)] ${className}`}
        title="Live backend unreachable; resilient local benchmark fallback active"
      >
        <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span>
        <span>{label || '▲ OFFLINE (FALLBACK ACTIVE)'}</span>
      </span>
    );
  }

  // Cached / Mock mode
  return (
    <span
      className={`inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/15 border border-amber-500/40 text-amber-300 font-mono text-xs font-bold tracking-wider uppercase shadow-[0_0_10px_rgba(245,158,11,0.3)] ${className}`}
      title="Running in verified standalone benchmark mode"
    >
      <span className="w-2 h-2 rounded-full bg-amber-400"></span>
      <span>{label || '◌ DEMO BENCHMARK'}</span>
    </span>
  );
};
