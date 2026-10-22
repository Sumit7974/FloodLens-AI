import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { BenchmarkScene } from '../types';
import { FloodLensLogo } from './FloodLensLogo';

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
            <FloodLensLogo variant="horizontal" className="h-9 sm:h-10 w-auto" />
          </div>

          <div className="h-5 w-px bg-zinc-800 hidden md:block" />

          {/* Benchmark Metadata as Discrete Eyebrow Text */}
          <div className="relative">
            <span className="text-[10px] uppercase tracking-wider text-zinc-400 font-medium block">
              EVENT BENCHMARK
            </span>
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-1.5 text-sm font-semibold text-white hover:text-zinc-200 transition-colors text-left group"
            >
              <span className="truncate max-w-[220px] sm:max-w-[340px] tracking-normal">
                {currentScene.name}
              </span>
              <ChevronDown className="w-3.5 h-3.5 text-zinc-400 transition-transform duration-200 group-hover:translate-y-0.5" />
            </button>

            {dropdownOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setDropdownOpen(false)}
                />
                <div className="absolute left-0 mt-2 w-80 z-50 bg-[#0d1117] border border-zinc-800 py-1.5 shadow-2xl rounded-md backdrop-blur-xl">
                  <div className="px-3 py-1.5 border-b border-zinc-800">
                    <p className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold">
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
                      className={`w-full text-left px-3 py-2 text-xs transition-colors flex flex-col gap-0.5 hover:bg-zinc-900 ${
                        currentScene.id === scene.id
                          ? 'bg-zinc-900 text-cyan-400 font-semibold border-l-2 border-cyan-400'
                          : 'text-zinc-300'
                      }`}
                    >
                      <span className="font-medium text-white">{scene.name}</span>
                      <span className="font-mono text-[10px] text-zinc-500 uppercase">
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
        <div className="flex items-center justify-between md:justify-end gap-3 lg:gap-5 flex-wrap">
          {/* Consolidated Minimalist Status Row (Dots / Lines instead of capsule pills) */}
          <div className="font-mono text-xs uppercase tracking-wider text-zinc-400 flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 font-medium text-zinc-300">
              <span
                className={`w-2 h-2 rounded-full ${
                  isBackendConnected ? 'bg-emerald-500' : 'bg-zinc-500'
                }`}
              />
              <span>{isBackendConnected ? 'LIVE BACKEND' : 'DEMO BENCHMARK'}</span>
            </span>

            <span className="text-zinc-700 font-light select-none">|</span>

            <span className="font-medium text-zinc-300">{regionName}</span>

            <span className="text-zinc-700 font-light select-none hidden sm:inline">|</span>

            <span
              className={`hidden sm:inline-flex items-center gap-1.5 font-medium ${
                openCount > 0 ? 'text-rose-400' : 'text-zinc-400'
              }`}
            >
              {openCount > 0 && <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />}
              <span>{openCount} OPEN SOS</span>
            </span>
          </div>

          {/* Clean High-Intent Emergency Action Button */}
          <button
            onClick={onTriggerSimulationEvent}
            className="inline-flex items-center gap-2 rounded-md px-3.5 py-1.5 bg-amber-600 hover:bg-amber-500 active:bg-amber-700 text-white text-xs font-mono font-bold tracking-wider uppercase border border-amber-500/40 shadow-sm transition-all cursor-pointer"
            title={isLiveSimulation ? 'Simulation active - Trigger surge' : 'Trigger flood surge event'}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
            <span>TRIGGER SURGE</span>
          </button>
        </div>
      </div>
    </header>
  );
};
