import React from 'react';
import {
  BrainCircuit,
  LayoutDashboard,
  LifeBuoy,
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
}) => {
  const navItems = [
    {
      id: 'command-overview' as NavigationItemId,
      label: 'Command Overview',
      icon: LayoutDashboard,
    },
    {
      id: 'prediction-centre' as NavigationItemId,
      label: 'Prediction Centre',
      icon: TrendingUp,
    },
    {
      id: 'satellite-intel' as NavigationItemId,
      label: 'Satellite Intelligence',
      icon: Satellite,
    },
    {
      id: 'response-ops' as NavigationItemId,
      label: 'Response Operations',
      icon: LifeBuoy,
    },
    {
      id: 'alert-dispatcher' as NavigationItemId,
      label: 'Alert Dispatcher',
      icon: Send,
    },
    {
      id: 'model-analytics' as NavigationItemId,
      label: 'Model Analytics',
      icon: BrainCircuit,
    },
  ];

  return (
    <aside className="w-full md:w-60 lg:w-64 flex-shrink-0 border-r border-[#27272a] bg-[#000000] flex flex-col justify-between">
      {/* Top Nav Section */}
      <div className="p-3 space-y-3">
        {/* Navigation Category Label */}
        <div className="px-3 pt-2 pb-1 flex items-center justify-between">
          <span className="font-micro text-[10px] uppercase tracking-[1.4px] text-[#5a5a5f]">
            CONSOLE NAVIGATION
          </span>
          <span className="inline-flex items-center gap-1.5 text-[10px] text-[#a0a0aa] font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            NOMINAL
          </span>
        </div>

        {/* Navigation List: Clean, single-line uppercase typography with generous vertical spacing (py-3) */}
        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;

            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`w-full group flex items-center gap-3 px-3 py-3 text-left transition-colors ${
                  isActive
                    ? 'bg-[#0a0a0a] text-white border-l-2 border-white pl-3.5'
                    : 'text-[#888890] hover:text-white hover:bg-[#0a0a0a] border-l-2 border-transparent'
                }`}
              >
                <Icon
                  className={`w-4 h-4 transition-colors ${
                    isActive ? 'text-white' : 'text-[#5a5a5f] group-hover:text-white'
                  }`}
                />
                <span className="font-display text-xs tracking-[1.4px] uppercase font-bold truncate">
                  {item.label}
                </span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Sidebar Footer: Clean Telemetry Line */}
      <div className="p-4 border-t border-[#27272a] bg-[#000000]">
        <div className="flex items-center justify-between text-[10px] font-mono text-[#5a5a5f] uppercase tracking-wider">
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            ORBITAL LINK
          </span>
          <span className="text-white font-bold">28 MS // 10HZ</span>
        </div>
      </div>
    </aside>
  );
};

