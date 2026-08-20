export function ResearchTag({ className = "" }: { className?: string }) {
  return (
    <div
      className={`inline-flex w-fit tracking-widest uppercase text-warning opacity-80 border border-warning/30 px-2 py-0.5 bg-warning/5 text-[10px] font-mono ${className}`}
    >
      STATISTICAL RESEARCH · NOT WAGERING ADVICE
    </div>
  );
}
