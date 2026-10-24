import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[FloodLens ErrorBoundary Caught Error]:', error, errorInfo);
  }

  public handleReload = () => {
    window.location.reload();
  };

  public handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#030712] text-white flex items-center justify-center p-6 font-mono">
          <div className="max-w-lg w-full bg-[#071326] border border-rose-500/40 rounded-xl p-6 shadow-[0_0_30px_rgba(244,63,94,0.15)] space-y-4">
            <div className="flex items-center gap-3 border-b border-[#1e3a5f] pb-4">
              <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400">
                <AlertTriangle className="w-6 h-6 animate-pulse" />
              </div>
              <div>
                <h2 className="font-display text-base font-bold text-white uppercase tracking-wider">
                  Operational Console Interrupted
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  An interface component encountered an unhandled exception.
                </p>
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-black/60 border border-[#1e3a5f] text-xs text-rose-300 overflow-x-auto">
              <code>{this.state.error?.message || 'Unknown runtime error'}</code>
            </div>

            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={this.handleReload}
                className="flex-1 py-2.5 px-4 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-bold text-xs uppercase tracking-wider flex items-center justify-center gap-2 transition-all shadow-md"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Reload Console
              </button>
              <button
                onClick={this.handleReset}
                className="py-2.5 px-4 rounded-lg bg-[#0c1d38] hover:bg-[#14284d] border border-[#1e3a5f] text-slate-300 font-bold text-xs uppercase tracking-wider transition-all"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
