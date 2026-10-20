import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { BenchmarkScene } from '../types';
import { FloodLensLogo } from './FloodLensLogo';

interface HeaderProps {
  benchmarkScenes: BenchmarkScene[];
  currentScene: BenchmarkScene;
  onSelectScene: (scene: BenchmarkScene) => void;
  activeAlertCount: number;
  pendingRescueCount: number;
  criticalZoneCount: number;
  lastUpdatedText: string;
  isLiveSimulation: boolean;
  onToggleLiveSimulation: () => void;
  onTriggerSimulationEvent: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  benchmarkScenes,
  currentScene,
  onSelectScene,
  pendingRescueCount,
  isLiveSimulation,
  onTriggerSimulationEvent,
}) => {
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const regionName = currentScene.region?.toUpperCase() || 'KOSHI BASIN';

  return (
    <header className="sticky top-0 z-40 w-full border-b border-[#1e293b]/90 bg-[#060d1b]/90 backdrop-blur-xl px-4 lg:px-6 py-2.5 shadow-[0_4px_20px_rgba(0,0,0,0.5)]">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        {/* Left Section: Branding & Subtle Eyebrow Benchmark Selector */}
        <div className="flex flex-wrap items-center gap-4 lg:gap-6">
          {/* Project Branding: Orbital FloodLens Logo */}
          <div className="flex items-center">
            <FloodLensLogo variant="horizontal" className="h-10 sm:h-11 w-auto" />
          </div>

          <div className="h-6 w-px bg-[#1e293b] hidden md:block" />

          {/* Benchmark Metadata as Discrete Eyebrow Text */}
          <div className="relative">
            <span className="font-micro text-[10px] uppercase tracking-[1.2px] text-[#38bdf8] font-bold block">
              EVENT BENCHMARK
            </span>
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-1.5 text-xs font-mono uppercase text-[#e2e8f0] hover:text-[#38bdf8] transition-colors text-left group"
            >
              <span className="truncate max-w-[220px] sm:max-w-[320px] font-bold tracking-wide group-hover:underline">
                {currentScene.name}
              </span>
              <ChevronDown className="w-3.5 h-3.5 text-[#38bdf8] transition-transform duration-200 group-hover:translate-y-0.5" />
            </button>

            {dropdownOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setDropdownOpen(false)}
                />
                <div className="absolute left-0 mt-2 w-80 z-50 bg-[#0b1528] border border-[#1e3a5f] py-1.5 shadow-[0_10px_30px_rgba(0,0,0,0.8)] rounded-md backdrop-blur-xl">
                  <div className="px-3 py-1.5 border-b border-[#1e3a5f]/80">
                    <p className="font-micro text-[10px] uppercase tracking-[1px] text-[#38bdf8] font-bold">
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
                      className={`w-full text-left px-3 py-2 text-xs transition-colors flex flex-col gap-0.5 hover:bg-[#13233e] ${currentScene.id === scene.id
                          ? 'bg-[#0e2a4a] text-[#38bdf8] font-bold border-l-2 border-[#38bdf8]'
                          : 'text-[#94a3b8]'
                        }`}
                    >
                      <span className="font-bold uppercase tracking-wider text-white">{scene.name}</span>
                      <span className="font-mono text-[10px] text-[#64748b] uppercase">
                        {scene.district} // {scene.event_type}
                      </span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Right Section: Luminous Status Strip & Vibrant Emergency Surge Button */}
        <div className="flex items-center justify-between md:justify-end gap-3 lg:gap-5">
          {/* Status Indicators with Rich Color Accents */}
          <div className="font-mono text-xs uppercase tracking-wider text-[#94a3b8] flex items-center gap-3">
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#10b981]/15 border border-[#10b981]/40 text-[#34d399] font-semibold text-[11px]">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span>{regionName}</span>
            </span>

            <span className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#ef4444]/15 border border-[#ef4444]/40 text-[#fca5a5] font-semibold text-[11px]">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse"></span>
              <span>{pendingRescueCount} ACTIVE RESCUE</span>
            </span>
          </div>

          {/* Energetic High-Intent Safety Orange Emergency Action Button */}
          <button
            onClick={onTriggerSimulationEvent}
            className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 bg-gradient-to-r from-[#e86e25] via-[#f97316] to-[#ea580c] text-white text-xs font-bold font-mono tracking-wider uppercase border border-[#ff9d5c] shadow-[0_0_15px_rgba(232,110,37,0.45)] hover:shadow-[0_0_25px_rgba(232,110,37,0.7)] hover:scale-[1.02] active:scale-95 transition-all duration-200 cursor-pointer"
            title={isLiveSimulation ? "Simulation active - Trigger surge" : "Trigger flood surge event"}
          >
            <span className="w-2 h-2 rounded-full bg-white animate-pulse"></span>
            <span>TRIGGER SURGE</span>
          </button>
        </div>
      </div>
    </header>
  );
};
