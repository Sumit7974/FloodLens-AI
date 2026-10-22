"use client";

import * as React from "react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  ChevronRight,
  LayoutDashboard,
  Layers,
  Activity,
  Bell,
  Settings,
  LogOut,
  PanelLeftClose,
  PanelLeft,
  ShieldAlert,
} from "lucide-react";

interface NavItem {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  href?: string;
  badge?: string;
  subItems?: { title: string; href: string }[];
}

const navItems: NavItem[] = [
  {
    title: "Overview",
    icon: LayoutDashboard,
    href: "#overview",
  },
  {
    title: "Intelligence & Data",
    icon: Layers,
    subItems: [
      { title: "Satellite Analysis", href: "#satellite" },
      { title: "Terrain & Elevation", href: "#terrain" },
      { title: "Inflow Predictions", href: "#predictions" },
    ],
  },
  {
    title: "Incidents & Reports",
    icon: ShieldAlert,
    badge: "14",
    subItems: [
      { title: "Active Reports", href: "#active-reports" },
      { title: "Citizen Queue", href: "#queue" },
      { title: "Critical Dispatches", href: "#dispatches" },
    ],
  },
  {
    title: "Model Analytics",
    icon: Activity,
    href: "#analytics",
  },
  {
    title: "Settings",
    icon: Settings,
    href: "#settings",
  },
];

export default function PlatformSidebar() {
  const [isOpen, setIsOpen] = useState(true);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    "Intelligence & Data": true,
  });

  const toggleSection = (title: string) => {
    setOpenSections((prev) => ({
      ...prev,
      [title]: !prev[title],
    }));
  };

  return (
    <aside
      className={`relative flex flex-col h-screen border-r border-zinc-800 bg-zinc-950 text-zinc-100 transition-all duration-300 ease-in-out ${
        isOpen ? "w-64" : "w-[68px]"
      }`}
    >
      <div className="flex h-16 items-center justify-between px-3 border-b border-zinc-800/80">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-cyan-600 text-white font-bold">
            FL
          </div>
          {isOpen && (
            <div className="flex flex-col truncate">
              <span className="text-sm font-semibold tracking-wide text-white">
                FloodLens AI
              </span>
              <span className="text-[11px] text-zinc-400 uppercase tracking-wider">
                EOC Operations
              </span>
            </div>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-zinc-400 hover:text-white"
          onClick={() => setIsOpen(!isOpen)}
        >
          {isOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeft className="h-4 w-4" />}
        </Button>
      </div>

      <ScrollArea className="flex-1 px-2 py-3">
        <nav className="flex flex-col gap-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const hasSub = !!item.subItems?.length;
            const isSectionOpen = openSections[item.title];

            if (hasSub) {
              return (
                <Collapsible
                  key={item.title}
                  open={isOpen && isSectionOpen}
                  onOpenChange={() => toggleSection(item.title)}
                >
                  <CollapsibleTrigger asChild>
                    <Button
                      variant="ghost"
                      className={`w-full justify-start ${
                        !isOpen ? "px-2 justify-center" : "px-3"
                      } h-10 hover:bg-zinc-800/60 hover:text-white text-zinc-300`}
                      title={!isOpen ? item.title : undefined}
                    >
                      <Icon className="h-4 w-4 shrink-0 text-cyan-400" />
                      {isOpen && (
                        <>
                          <span className="ml-3 text-sm font-medium flex-1 text-left truncate">
                            {item.title}
                          </span>
                          {item.badge && (
                            <span className="ml-auto mr-1 rounded-full bg-red-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-red-400">
                              {item.badge}
                            </span>
                          )}
                          <ChevronRight
                            className={`h-4 w-4 shrink-0 text-zinc-400 transition-transform duration-200 ${
                              isSectionOpen ? "rotate-90" : ""
                            }`}
                          />
                        </>
                      )}
                    </Button>
                  </CollapsibleTrigger>
                  {isOpen && (
                    <CollapsibleContent className="space-y-0.5 pl-9 pr-1 py-1">
                      {item.subItems?.map((sub) => (
                        <a
                          key={sub.title}
                          href={sub.href}
                          className="flex h-8 items-center rounded-md px-2 text-xs font-normal text-zinc-400 hover:bg-zinc-800/50 hover:text-white transition-colors"
                        >
                          {sub.title}
                        </a>
                      ))}
                    </CollapsibleContent>
                  )}
                </Collapsible>
              );
            }

            return (
              <Button
                key={item.title}
                asChild
                variant="ghost"
                className={`w-full justify-start ${
                  !isOpen ? "px-2 justify-center" : "px-3"
                } h-10 hover:bg-zinc-800/60 hover:text-white text-zinc-300`}
                title={!isOpen ? item.title : undefined}
              >
                <a href={item.href || "#"} className="flex items-center">
                  <Icon className="h-4 w-4 shrink-0 text-cyan-400" />
                  {isOpen && (
                    <span className="ml-3 text-sm font-medium flex-1 text-left truncate">
                      {item.title}
                    </span>
                  )}
                </a>
              </Button>
            );
          })}
        </nav>
      </ScrollArea>

      <Separator className="bg-zinc-800" />

      <div className="p-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              className={`w-full ${
                isOpen ? "justify-start px-2" : "justify-center px-0"
              } h-12 hover:bg-zinc-800/60`}
            >
              <Avatar className="h-8 w-8">
                <AvatarImage src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&h=100&fit=crop" />
                <AvatarFallback>EO</AvatarFallback>
              </Avatar>
              {isOpen && (
                <div className="ml-3 flex flex-col text-left truncate">
                  <span className="text-xs font-semibold leading-tight text-white truncate">
                    Operations Lead
                  </span>
                  <span className="text-[11px] text-zinc-400 truncate">
                    commander@eoc.gov.np
                  </span>
                </div>
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            side="right"
            sideOffset={10}
            className="w-56 bg-zinc-900 border-zinc-800 text-zinc-200"
          >
            <DropdownMenuLabel>Operator Console</DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-zinc-800" />
            <DropdownMenuItem className="hover:bg-zinc-800 cursor-pointer">
              <Bell className="mr-2 h-4 w-4" /> Notifications
            </DropdownMenuItem>
            <DropdownMenuItem className="hover:bg-zinc-800 cursor-pointer">
              <Settings className="mr-2 h-4 w-4" /> Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator className="bg-zinc-800" />
            <DropdownMenuItem className="text-red-400 hover:bg-zinc-800 cursor-pointer">
              <LogOut className="mr-2 h-4 w-4" /> Exit Session
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </aside>
  );
}
