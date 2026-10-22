import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle, CardToolbar } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge-2";
import { Button } from "@/components/ui/button-1";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { 
  AlertTriangle, 
  Users, 
  LifeBuoy, 
  Activity, 
  MoreHorizontal, 
  ExternalLink, 
  RefreshCw 
} from "lucide-react";
import type { MetricSummary } from "@/types";

interface TelemetryMetric {
  title: string;
  icon: React.ReactNode;
  value: string;
  badgeText: string;
  badgeVariant?: "warning" | "destructive" | "success" | "info" | "outline";
  badgePulse?: boolean;
  subtext: string;
  bgGradient: string;
  svgDecor: React.ReactNode;
}

interface TelemetryCommandCardsProps {
  metrics?: MetricSummary;
}

export function TelemetryCommandCards({ metrics }: TelemetryCommandCardsProps = {}) {
  const telemetryData: TelemetryMetric[] = [
    {
      title: "SURGE THREAT LEVEL",
      icon: <AlertTriangle className="size-4 text-amber-400"/>,
      value: metrics?.floodThreat?.level 
        ? (metrics.floodThreat.level.includes("LEVEL") ? metrics.floodThreat.level : `LEVEL ${metrics.floodThreat.level}`) 
        : "ELEVATED THREAT / LEVEL 3",
      badgeText: metrics?.floodThreat?.levelCode ? `LEVEL ${metrics.floodThreat.levelCode}` : "LEVEL 3",
      badgeVariant: "warning",
      badgePulse: true,
      subtext: metrics?.floodThreat?.description || "Chatara: 8.18m / Danger: 8.00m — Elevated",
      bgGradient: "bg-gradient-to-br from-amber-950/40 via-slate-900 to-slate-950 border-amber-500/30",
      svgDecor: (
        <svg className="absolute right-0 top-0 h-full w-2/3 pointer-events-none" viewBox="0 0 300 200" fill="none">
          <circle cx="220" cy="80" r="80" fill="#f59e0b" fillOpacity="0.06" />
          <circle cx="260" cy="50" r="50" fill="#f59e0b" fillOpacity="0.08" />
          <circle cx="180" cy="140" r="40" fill="#f59e0b" fillOpacity="0.04" />
        </svg>
      ),
    },
    {
      title: "EXPOSED POPULATION",
      icon: <Users className="size-4 text-cyan-400"/>,
      value: metrics?.populationAtRisk?.total ? `~${metrics.populationAtRisk.total.toLocaleString()}` : "~18,420",
      badgeText: "ACTIVE",
      badgeVariant: "info",
      subtext: "DEM flood envelope overlay onto census",
      bgGradient: "bg-gradient-to-br from-cyan-950/40 via-slate-900 to-slate-950 border-cyan-500/30",
      svgDecor: (
        <svg className="absolute right-0 top-0 w-48 h-48 pointer-events-none" viewBox="0 0 200 200" fill="none">
          <rect x="110" y="20" width="70" height="70" rx="35" fill="#06b6d4" fillOpacity="0.06" />
          <circle cx="170" cy="90" r="24" fill="#06b6d4" fillOpacity="0.08" />
          <polygon points="140,0 200,0 200,60" fill="#06b6d4" fillOpacity="0.04" />
        </svg>
      ),
    },
    {
      title: "ASSISTANCE REPORTS",
      icon: <LifeBuoy className="size-4 text-rose-400"/>,
      value: metrics?.openRequests?.total !== undefined ? `${metrics.openRequests.total} LOGGED` : "14 LOGGED",
      badgeText: metrics?.openRequests?.critical !== undefined ? `${metrics.openRequests.critical} CRITICAL` : "3 CRITICAL",
      badgeVariant: "destructive",
      subtext: metrics?.openRequests 
        ? `${metrics.openRequests.total} Reports · ${metrics.openRequests.critical} Critical Risk`
        : "14 Reports · 3 Critical Risk",
      bgGradient: "bg-gradient-to-br from-rose-950/40 via-slate-900 to-slate-950 border-rose-500/30",
      svgDecor: (
        <svg className="absolute right-0 top-0 w-48 h-48 pointer-events-none" viewBox="0 0 200 200" fill="none">
          <polygon points="120,0 200,0 200,80" fill="#f43f5e" fillOpacity="0.05" />
          <circle cx="160" cy="50" r="30" fill="#f43f5e" fillOpacity="0.07" />
          <rect x="130" y="70" width="50" height="20" rx="6" fill="#f43f5e" fillOpacity="0.05" />
        </svg>
      ),
    },
    {
      title: "TELEMETRY UPLINK",
      icon: <Activity className="size-4 text-emerald-400"/>,
      value: metrics?.sensorHealth 
        ? `${metrics.sensorHealth.reporting}/${metrics.sensorHealth.total} ACTIVE` 
        : "12/12 ACTIVE",
      badgeText: "ONLINE",
      badgeVariant: "success",
      subtext: metrics?.sensorHealth 
        ? `${metrics.sensorHealth.reporting}/${metrics.sensorHealth.total} Gauges Online · LoRa & Gov Hydro` 
        : "12/12 Gauges Online · LoRa & Gov Hydro",
      bgGradient: "bg-gradient-to-br from-emerald-950/40 via-slate-900 to-slate-950 border-emerald-500/30",
      svgDecor: (
        <svg className="absolute right-0 top-0 w-48 h-48 pointer-events-none" viewBox="0 0 200 200" fill="none">
          <circle cx="160" cy="40" r="35" fill="#10b981" fillOpacity="0.06" />
          <ellipse cx="150" cy="80" rx="40" ry="15" fill="#10b981" fillOpacity="0.05" />
          <line x1="110" y1="10" x2="190" y2="90" stroke="#10b981" strokeOpacity="0.08" strokeWidth="4" />
        </svg>
      ),
    },
  ];

  return (
    <div className="w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 p-2 mb-2">
      {telemetryData.map((item, index) => (
        <Card
          key={index}
          className={`relative overflow-hidden backdrop-blur-md border shadow-lg text-slate-100 transition-all hover:border-slate-500/50 ${item.bgGradient}`}
        >
          {item.svgDecor}

          <CardHeader className="border-0 z-10 relative pb-1 pt-4 px-4 flex flex-row items-center justify-between">
            <div className="flex items-center gap-2">
              {item.icon}
              <CardTitle className="text-slate-300 text-xs font-semibold tracking-wider uppercase">
                {item.title}
              </CardTitle>
            </div>

            <CardToolbar>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button className="size-7 text-slate-400 hover:text-white hover:bg-white/10" size="icon" variant="ghost">
                    <MoreHorizontal className="size-3.5"/>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="bg-slate-900 text-slate-200 border-slate-800">
                  <DropdownMenuItem className="text-xs flex gap-2 cursor-pointer">
                    <RefreshCw className="size-3.5"/> Force Sync
                  </DropdownMenuItem>
                  <DropdownMenuItem className="text-xs flex gap-2 cursor-pointer">
                    <ExternalLink className="size-3.5"/> Sensor Feed
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </CardToolbar>
          </CardHeader>

          <CardContent className="space-y-3 z-10 relative px-4 pb-4">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xl lg:text-2xl font-bold tracking-tight text-white font-mono">
                {item.value}
              </span>
              <Badge appearance="light" className="font-mono text-[10px] tracking-wider uppercase shrink-0" size="sm" variant={item.badgeVariant}>
                {item.badgePulse && (
                  <span className="size-1.5 rounded-full bg-amber-400 animate-ping mr-1" />
                )}
                {item.badgeText}
              </Badge>
            </div>

            <div className="text-[11px] text-slate-400 border-t border-white/10 pt-2.5 line-clamp-1 font-mono">
              {item.subtext}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export { TelemetryCommandCards as MetricCards };
