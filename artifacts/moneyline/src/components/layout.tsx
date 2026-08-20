import { cn } from "@/lib/utils";
import { Badge } from "./ui/badge";
import { Loader2 } from "lucide-react";
import { useLiveSeason } from "@/api";

export function TerminalBoot({ loaded, error }: { loaded: boolean; error?: Error | null }) {
  const liveSeason = useLiveSeason();
  if (loaded) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background text-primary font-mono text-sm">
      <div className="flex flex-col gap-2 max-w-md w-full p-6">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-success animate-pulse">◆</span>
          <span className="font-bold tracking-widest uppercase">Moneyline Terminal</span>
        </div>
        
        {error ? (
          <div className="text-destructive">
            <div>ERR: BOOT_SEQUENCE_FAILED</div>
            <div>{error.message}</div>
            <div className="mt-4 text-muted-foreground animate-pulse">Retrying...</div>
          </div>
        ) : (
          <>
            <div className="flex justify-between">
              <span>LOADING MODELS...</span>
              <span className="text-success">OK</span>
            </div>
            <div className="flex justify-between animate-in fade-in fill-mode-forwards duration-500 delay-300">
              <span>FITTING 1962–2001...</span>
              <span className="text-success">OK</span>
            </div>
            <div className="flex justify-between animate-in fade-in fill-mode-forwards duration-500 delay-500">
              <span>SYNCING {liveSeason ?? "LIVE"} FEEDS...</span>
              <span className="text-success">OK</span>
            </div>
            <div className="flex justify-between animate-in fade-in fill-mode-forwards duration-500 delay-700">
              <span className="flex items-center gap-2"><Loader2 className="w-3 h-3 animate-spin" /> PRICING SLATE...</span>
              <span className="text-muted-foreground">WAIT</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export function PanelSkeleton() {
  return (
    <div className="moneyline-panel animate-pulse flex-1 min-h-[200px]">
      <div className="moneyline-section-header w-1/3 bg-muted h-3" />
      <div className="flex-1 bg-muted/50 mt-4 rounded-none" />
    </div>
  );
}

export function PanelError({ message }: { message: string }) {
  return (
    <div className="moneyline-panel flex-1 min-h-[200px] border-destructive/30 bg-destructive/5 justify-center items-center text-center p-6">
      <Badge variant="destructive" className="mb-2">ERROR</Badge>
      <div className="text-destructive font-mono text-sm max-w-sm">{message}</div>
    </div>
  );
}
