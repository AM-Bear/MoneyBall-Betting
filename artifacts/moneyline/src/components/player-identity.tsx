import { cn } from "@/lib/utils";

/** Mono-caps identity with an initial-block avatar — no headshots, no logos. */
export function PlayerIdentity({
  name,
  team,
  position,
  size = "md",
  className,
}: {
  name: string;
  team?: string | null;
  position?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className={cn("flex items-center gap-3 font-mono", className)}>
      <div
        aria-hidden
        className={cn(
          "shrink-0 flex items-center justify-center border border-primary/40 bg-primary/10 text-primary font-bold tracking-tight",
          size === "lg" ? "w-12 h-12 text-lg" : size === "sm" ? "w-7 h-7 text-[10px]" : "w-9 h-9 text-sm",
        )}
      >
        {initials}
      </div>
      <div className="flex flex-col min-w-0">
        <span
          className={cn(
            "font-bold uppercase tracking-wider truncate",
            size === "lg" ? "text-xl" : size === "sm" ? "text-xs" : "text-sm",
          )}
        >
          {name}
        </span>
        {(team || position) && (
          <span className="text-[10px] uppercase text-muted-foreground tracking-widest truncate">
            {[team, position].filter(Boolean).join(" · ")}
          </span>
        )}
      </div>
    </div>
  );
}
