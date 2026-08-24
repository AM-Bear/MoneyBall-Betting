import { useEffect, useState } from "react";

export type DetailLevel = "compact" | "standard" | "expanded";

export interface PresentationPreferences {
  detailLevel: DetailLevel;
  explainTerms: boolean;
  guideDismissed: boolean;
}

const STORAGE_KEY = "moneyline-presentation-preferences";

const DEFAULTS: PresentationPreferences = {
  detailLevel: "standard",
  explainTerms: true,
  guideDismissed: false,
};

function readPreferences(): PresentationPreferences {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    return {
      ...DEFAULTS,
      ...saved,
      detailLevel: ["compact", "standard", "expanded"].includes(saved.detailLevel)
        ? saved.detailLevel
        : DEFAULTS.detailLevel,
      explainTerms: saved.explainTerms !== false,
      guideDismissed: saved.guideDismissed === true,
    };
  } catch {
    return DEFAULTS;
  }
}

export function usePresentationPreferences() {
  const [preferences, setPreferences] = useState<PresentationPreferences>(() => readPreferences());

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  }, [preferences]);

  const updatePreferences = (patch: Partial<PresentationPreferences>) => {
    setPreferences((current) => ({ ...current, ...patch }));
  };

  return { preferences, updatePreferences };
}

export function WelcomeGuide({ onDismiss }: { onDismiss: () => void }) {
  return (
    <section className="today-guide" aria-labelledby="guide-title" data-testid="onboarding-guide">
      <div className="today-guide-mark" aria-hidden="true">01</div>
      <div className="flex-1">
        <p className="eyebrow">A quick orientation</p>
        <h2 id="guide-title" className="text-lg font-semibold tracking-tight">Start with the model, then add your own price</h2>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
          MONEYLINE shows a season-based probability and its fair price. It does not receive sportsbook prices.
          Enter a price you have in hand when you want to compare it, and treat injuries, wire notes, and pulse as context—not model inputs.
        </p>
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
          <span className="guide-pill">Probability = model estimate</span>
          <span className="guide-pill">Fair price = model translation</span>
          <span className="guide-pill">Book price = your manual input</span>
        </div>
      </div>
      <button type="button" onClick={onDismiss} className="quiet-button shrink-0" data-testid="button-dismiss-guide">
        Skip guide
      </button>
    </section>
  );
}