import React from 'react';
import {
  BrainCircuit,
  LayoutDashboard,
  ShieldAlert,
  Satellite,
  Send,
  TrendingUp,
} from 'lucide-react';
import type { NavigationItemId } from '../types';

interface SidebarProps {
  activeTab: NavigationItemId;
  onSelectTab: (tab: NavigationItemId) => void;
  openSosCount?: number;
  activeAlertCount?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  openSosCount,
  activeAlertCount,
}) => {
  const navItems = [
    {
      id: 'command-overview' as NavigationItemId,
      label: 'Command Overview',
      icon: LayoutDashboard,
      color: 'text-sky-400',
      activeBorder: 'border-sky-400',
      activeBg: 'bg-gradient-to-r from-sky-500/20 via-sky-500/10 to-transparent',
      glow: 'shadow-[0_0_12px_rgba(56,189,248,0.25)]',
    },
    {
      id: 'prediction-centre' as NavigationItemId,
      label: 'Prediction Centre',
      icon: TrendingUp,
      color: 'text-amber-400',
      activeBorder: 'border-amber-400',
      activeBg: 'bg-gradient-to-r from-amber-500/20 via-amber-500/10 to-transparent',
      glow: 'shadow-[0_0_12px_rgba(245,158,11,0.25)]',
    },
    {
      id: 'satellite-intel' as NavigationItemId,
      label: 'Satellite Intelligence',
      icon: Satellite,
      color: 'text-purple-400',
      activeBorder: 'border-purple-400',
      activeBg: 'bg-gradient-to-r from-purple-500/20 via-purple-500/10 to-transparent',
      glow: 'shadow-[0_0_12px_rgba(192,132,252,0.25)]',
    },
    {
      id: 'response-ops' as NavigationItemId,
      label: 'Incident Intelligence',
      sublabel: 'Authority Coordination',
      icon: ShieldAlert,
      color: 'text-emerald-400',
      activeBorder: 'border-emerald-400',
      activeBg: 'bg-gradient-to-r from-emerald-500/20 via-emerald-500/10 to-transparent',
      glow: 'shadow-[0_0_12px_rgba(52,211,153,0.25)]',
      badge: openSosCount && openSosCount > 0 ? `${openSosCount}` : undefined,
      badgeColor: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40',
    },
    {
      id: 'alert-dispatcher' as NavigationItemId,
      label: 'Alert Dispatcher',
      icon: Send,
      color: 'text-rose-400',
      activeBorder: 'border-rose-400',
      activeBg: 'bg-gradient-to-r from-rose-500/20 via-rose-500/10 to-transparent',
      glow: 'shadow-[0_0_12px_rgba(244,63,94,0.25)]',
      badge: activeAlertCount && activeAlertCount > 0 ? `${activeAlertCount}` : undefined,
      badgeColor: 'bg-rose-500/20 text-rose-300 border border-rose-500/40',
    },
    {
      id: 'model-analytics' as NavigationItemId,
      label: 'Model Analytics',
      icon: BrainCircuit,
      color: 'text-indigo-400',
      activeBorder: 'border-indigo-400',
      activeBg: 'bg-gradient-to-r from-indigo-500/20 via-indigo-500/10 to-transparent',
      glow: 'shadow-[0_0_12px_rgba(129,140,248,0.25)]',
    },
  ];

  return (
    <aside className="w-full md:w-60 lg:w-64 flex-shrink-0 border-r border-[#1e293b]/90 bg-[#060d1b]/85 backdrop-blur-xl flex flex-col justify-between shadow-[4px_0_24px_rgba(0,0,0,0.5)]">
      {/* Top Nav Section */}
      <div className="p-3 space-y-3">
        {/* Navigation Category Label with Luminous Cyan Eyebrow */}
        <div className="px-3 pt-2 pb-1 flex items-center justify-between">
          <span className="font-micro text-xs uppercase tracking-[1.4px] text-[#38bdf8] font-bold">
            CONSOLE NAVIGATION
          </span>
          <span className="inline-flex items-center gap-1.5 text-xs text-emerald-400 font-mono px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 font-semibold">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            NOMINAL
          </span>
        </div>

        {/* Navigation List: Colorful Icons & Glowing Active Borders */}
        <nav className="space-y-1.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;

            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`w-full group flex items-center justify-between px-3.5 py-3 text-left transition-all duration-200 rounded-md cursor-pointer ${
                  isActive
                    ? `${item.activeBg} text-white border-l-2 ${item.activeBorder} ${item.glow}`
                    : 'text-[#94a3b8] hover:text-white hover:bg-[#0f1d36]/70 border-l-2 border-transparent hover:border-[#38bdf8]/50'
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`p-1.5 rounded transition-colors ${isActive ? 'bg-white/10' : 'group-hover:bg-white/5'}`}>
                    <Icon
                      className={`w-4.5 h-4.5 transition-transform duration-200 group-hover:scale-110 ${
                        isActive ? item.color : `${item.color} opacity-70 group-hover:opacity-100`
                      }`}
                    />
                  </div>
                  <span className="font-display text-sm tracking-wide uppercase font-bold truncate">
                    {item.label}
                  </span>
                </div>

                {item.badge && (
                  <span className={`text-xs font-mono px-2 py-0.5 rounded-full font-bold shrink-0 ${item.badgeColor}`}>
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Sidebar Footer: Vibrant Telemetry Line */}
      <div className="p-3.5 border-t border-[#1e293b]/90 bg-[#091322]/80">
        <div className="flex items-center justify-between text-xs font-mono uppercase tracking-wider">
          <span className="flex items-center gap-2 text-[#34d399] font-semibold">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            ORBITAL LINK
          </span>
          <span className="text-[#38bdf8] font-bold bg-[#38bdf8]/10 px-2.5 py-0.5 rounded border border-[#38bdf8]/30">
            28 MS // 10HZ
          </span>
        </div>
      </div>
    </aside>
  );
};

