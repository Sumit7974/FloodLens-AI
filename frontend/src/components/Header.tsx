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
    <header className="sticky top-0 z-40 w-full border-b border-[#27272a]/80 bg-[#000000]/80 backdrop-blur-md px-4 lg:px-6 py-2.5">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        {/* Left Section: Branding & Subtle Eyebrow Benchmark Selector */}
        <div className="flex flex-wrap items-center gap-4 lg:gap-6">
          {/* Project Branding: Orbital FloodLens Logo */}
          <div className="flex items-center">
            <FloodLensLogo variant="horizontal" className="h-10 sm:h-11 w-auto" />
          </div>

          <div className="h-6 w-px bg-[#27272a] hidden md:block" />

          {/* Benchmark Metadata as Discrete Eyebrow Text (No heavy boxes) */}
          <div className="relative">
            <span className="font-micro text-[10px] uppercase tracking-[1.2px] text-[#5a5a5f] block">
              EVENT BENCHMARK
            </span>
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-1.5 text-xs font-mono uppercase text-[#f0f0fa] hover:text-white transition-colors text-left"
            >
              <span className="truncate max-w-[220px] sm:max-w-[320px] font-bold tracking-wide">
                {currentScene.name}
              </span>
              <ChevronDown className="w-3 h-3 text-[#5a5a5f]" />
            </button>

            {dropdownOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setDropdownOpen(false)}
                />
                <div className="absolute left-0 mt-2 w-80 z-50 bg-[#0a0a0a] border border-[#27272a] py-1 shadow-2xl">
                  <div className="px-3 py-1.5 border-b border-[#27272a]">
                    <p className="font-micro text-[10px] uppercase tracking-[1px] text-[#5a5a5f]">
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
                      className={`w-full text-left px-3 py-2 text-xs transition-colors flex flex-col gap-0.5 hover:bg-[#141416] ${
                        currentScene.id === scene.id
                          ? 'bg-[#141416] text-white font-bold border-l-2 border-white'
                          : 'text-[#888890]'
                      }`}
                    >
                      <span className="font-bold uppercase tracking-wider">{scene.name}</span>
                      <span className="font-mono text-[10px] text-[#5a5a5f] uppercase">
                        {scene.district} // {scene.event_type}
                      </span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Right Section: Single Calm Status Line & ONE Ghost-Pill Button */}
        <div className="flex items-center justify-between md:justify-end gap-4 lg:gap-6">
          {/* Single Calm Status Line */}
          <div className="font-mono text-xs uppercase tracking-[1.4px] text-[#a0a0aa] flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            <span>
              {regionName} // HIGH SURGE // {pendingRescueCount} ACTIVE RESCUE
            </span>
          </div>

          {/* Only ONE ghost-pill button in the header */}
          <button
            onClick={onTriggerSimulationEvent}
            className="btn-ghost-pill text-xs !py-1.5 !px-4 tracking-[1.2px]"
            title={isLiveSimulation ? "Simulation active - Trigger surge" : "Trigger flood surge"}
          >
            TRIGGER SURGE
          </button>
        </div>
      </div>
    </header>
  );
};
