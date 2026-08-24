import { usePresentationPreferences, DetailLevel } from "@/components/presentation-preferences";

export default function SettingsPage() {
  const { preferences, updatePreferences } = usePresentationPreferences();

  return (
    <main className="page-wrap">
      <div className="page-heading">
        <div>
          <div className="eyebrow">This device only</div>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Settings</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Presentation preferences change what is expanded and how much explanation is shown. They never change model numbers, thresholds, or data availability.
          </p>
        </div>
      </div>
      <section className="settings-card" aria-labelledby="settings-presentation">
        <div>
          <p className="eyebrow">Presentation</p>
          <h2 id="settings-presentation" className="mt-2 text-lg font-semibold">Make Today fit your reading style</h2>
        </div>
        <label className="settings-field" htmlFor="detail-level">
          <span>
            <strong>Default detail level</strong>
            <small>Compact shows the answer only; Standard keeps layers closed; Expanded opens them.</small>
          </span>
          <select
            id="detail-level"
            value={preferences.detailLevel}
            onChange={(event) => updatePreferences({ detailLevel: event.target.value as DetailLevel })}
            data-testid="select-detail-level"
          >
            <option value="compact">Compact</option>
            <option value="standard">Standard</option>
            <option value="expanded">Expanded</option>
          </select>
        </label>
        <label className="settings-toggle" htmlFor="explain-terms">
          <span>
            <strong>Explain model terms</strong>
            <small>Keep short definitions beside probabilities, fair prices, and context labels.</small>
          </span>
          <input
            id="explain-terms"
            type="checkbox"
            checked={preferences.explainTerms}
            onChange={(event) => updatePreferences({ explainTerms: event.target.checked })}
            data-testid="checkbox-explain-terms"
          />
        </label>
        <button type="button" className="quiet-button w-fit" onClick={() => updatePreferences({ ...preferences, detailLevel: "standard", explainTerms: true, guideDismissed: false })} data-testid="button-reset-preferences">
          Reset presentation preferences
        </button>
      </section>
    </main>
  );
}