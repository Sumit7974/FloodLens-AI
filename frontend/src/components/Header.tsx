import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { BenchmarkScene } from '../types';
import { FloodLensLogo } from './FloodLensLogo';
import { InteractiveHoverButton } from '@/components/ui/interactive-hover-button';

interface HeaderProps {
  benchmarkScenes: BenchmarkScene[];
  currentScene: BenchmarkScene;
  onSelectScene: (scene: BenchmarkScene) => void;
  activeAlertCount: number;
  openReportsCount?: number;
  pendingRescueCount?: number;
  criticalZoneCount: number;
  lastUpdatedText: string;
  isLiveSimulation: boolean;
  isBackendConnected?: boolean;
  onToggleLiveSimulation: () => void;
  onTriggerSimulationEvent: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  benchmarkScenes,
  currentScene,
  onSelectScene,
  openReportsCount,
  pendingRescueCount,
  isLiveSimulation,
  isBackendConnected = false,
  onTriggerSimulationEvent,
}) => {
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const regionName = currentScene.region?.toUpperCase() || 'KOSHI BASIN';
  const openCount = openReportsCount !== undefined ? openReportsCount : pendingRescueCount || 0;

  return (
    <header className="sticky top-0 z-40 w-full border-b border-zinc-800 bg-[#0a0a0a]/95 backdrop-blur-md px-4 lg:px-6 py-2.5 shadow-sm">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        {/* Left Section: Branding & Subtle Eyebrow Benchmark Selector */}
        <div className="flex flex-wrap items-center gap-4 lg:gap-6">
          {/* Project Branding: Orbital FloodLens Logo */}
          <div className="flex items-center">
            <FloodLensLogo variant="horizontal" className="h-10 sm:h-12 w-auto" />
          </div>

          <div className="h-6 w-px bg-zinc-800 hidden md:block" />

          {/* Benchmark Metadata as Discrete Eyebrow Text */}
          <div className="relative">
            <span className="text-xs uppercase tracking-wider text-zinc-400 font-semibold block">
              EVENT BENCHMARK
            </span>
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-2 text-base font-bold text-white hover:text-cyan-300 transition-colors text-left group"
            >
              <span className="truncate max-w-[240px] sm:max-w-[360px] tracking-normal">
                {currentScene.name}
              </span>
              <ChevronDown className="w-4 h-4 text-zinc-400 transition-transform duration-200 group-hover:translate-y-0.5" />
            </button>

            {dropdownOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setDropdownOpen(false)}
                />
                <div className="absolute left-0 mt-2 w-84 z-50 bg-[#0d1117] border border-zinc-800 py-2 shadow-2xl rounded-md backdrop-blur-xl">
                  <div className="px-3.5 py-2 border-b border-zinc-800">
                    <p className="text-xs uppercase tracking-wider text-zinc-400 font-bold">
                      SELECT BENCHMARK SCENARIO
                    </p>
                  </div>
                  {benchmarkScenes.map((scene) => (
                    <button
                      key={scene.id}
                      onClick={() => {
                        onSelectScene(scene);
                        setDropdownOpen(false);
                      }}
                      className={`w-full text-left px-3.5 py-2.5 text-sm transition-colors flex flex-col gap-1 hover:bg-zinc-900 ${
                        currentScene.id === scene.id
                          ? 'bg-zinc-900 text-cyan-400 font-bold border-l-2 border-cyan-400'
                          : 'text-zinc-300'
                      }`}
                    >
                      <span className="font-semibold text-white text-sm">{scene.name}</span>
                      <span className="font-mono text-xs text-zinc-400 uppercase">
                        {scene.district} // {scene.event_type}
                      </span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Right Section: Minimalist Status Row & Intentional Emergency Action */}
        <div className="flex items-center justify-between md:justify-end gap-3.5 lg:gap-6 flex-wrap">
          {/* Consolidated Status Row with high-visibility indicators */}
          <div className="font-mono text-sm uppercase tracking-wider text-zinc-300 flex items-center gap-3.5">
            <span className="inline-flex items-center gap-2 font-bold text-white">
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  isBackendConnected ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]' : 'bg-zinc-500'
                }`}
              />
              <span className={isBackendConnected ? 'text-emerald-400 font-bold' : 'text-zinc-300'}>
                {isBackendConnected ? 'LIVE BACKEND' : 'DEMO BENCHMARK'}
              </span>
            </span>

            <span className="text-zinc-600 font-light select-none">|</span>

            <span className="font-bold text-zinc-200">{regionName}</span>

            <span className="text-zinc-600 font-light select-none hidden sm:inline">|</span>

            <span
              className={`hidden sm:inline-flex items-center gap-2 font-bold ${
                openCount > 0 ? 'text-rose-400' : 'text-zinc-400'
              }`}
            >
              {openCount > 0 && <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse shadow-[0_0_8px_rgba(244,63,94,0.6)]" />}
              <span>{openCount} OPEN SOS</span>
            </span>
          </div>

          {/* High-Intent Emergency Action Button */}
          <InteractiveHoverButton
            text="TRIGGER SURGE"
            onClick={onTriggerSimulationEvent}
            title={isLiveSimulation ? 'Simulation active - Trigger surge' : 'Trigger flood surge event'}
            className="w-48 sm:w-52 border-amber-500/60 bg-amber-950/50 text-amber-300 font-mono text-sm font-bold uppercase tracking-wider shadow-[0_0_15px_rgba(245,158,11,0.3)] hover:border-amber-400 py-2"
            dotColor="bg-amber-500 group-hover:bg-amber-500"
          />
        </div>
      </div>
    </header>
  );
};
