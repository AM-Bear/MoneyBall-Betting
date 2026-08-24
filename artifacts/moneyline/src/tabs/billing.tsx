import { Check, LockKeyhole, RefreshCw } from "lucide-react";
import { useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { useBillingCatalog, useBillingCheckout, useBillingPortal, useBillingStatus } from "@/api";

const labels: Record<string, string> = {
  today: "Today", desk: "Desk", track_record: "Track record", players: "Players",
  matchups: "Matchups", wire: "Wire", parlay: "Parlay lab", season: "Season outlook",
};

export default function BillingPage() {
  const [, navigate] = useLocation();
  const catalog = useBillingCatalog();
  const status = useBillingStatus();
  const checkout = useBillingCheckout();
  const portal = useBillingPortal();
  const activeTier = status.data?.entitlement?.tier || catalog.data?.entitlement?.tier || "free";
  const error = catalog.error || status.error;

  const startCheckout = async (tier: "analyst" | "pro") => {
    try {
      const result = await checkout.mutateAsync(tier);
      window.location.assign(result.url);
    } catch { /* the API error is rendered below */ }
  };

  return (
    <main className="page-wrap">
      <div className="page-heading">
        <div>
          <div className="eyebrow">Research access</div>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Choose your desk</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            The free floor stays useful. Paid tiers unlock deeper research, and access is checked on the server for every premium request.
          </p>
        </div>
      </div>
      {new URLSearchParams(window.location.search).get("billing") === "success" && (
        <div className="research-note" role="status"><RefreshCw aria-hidden="true" /> Payment returned successfully. Access updates as Stripe confirms the subscription.</div>
      )}
      {error && <div className="research-note" role="alert">Sign in to view billing and research access. Your login session is supplied by the authentication flow.</div>}
      <div className="billing-grid" aria-label="MONEYLINE tiers">
        {(catalog.data?.tiers || []).map((tier) => {
          const current = activeTier === tier.id;
          return (
            <section key={tier.id} className={`billing-card ${current ? "billing-card-current" : ""}`}>
              <div className="flex items-start justify-between gap-3">
                <div><div className="eyebrow">{tier.name}</div><h2 className="mt-2 text-xl font-semibold">{tier.description}</h2></div>
                {current ? <span className="status-label status-label-success">Current</span> : <LockKeyhole className="text-primary/70" aria-hidden="true" />}
              </div>
              <p className="billing-price">{tier.price_monthly === 0 ? "Free" : `$${tier.price_monthly}`}<small>{tier.price_monthly ? " / month" : " forever"}</small></p>
              <ul className="billing-features">
                {tier.features.map((feature) => <li key={feature}><Check aria-hidden="true" /> {labels[feature] || feature}</li>)}
              </ul>
              {tier.id !== "free" && !current && tier.configured && (
                <Button className="w-full" onClick={() => startCheckout(tier.id as "analyst" | "pro")} disabled={checkout.isPending}>
                  {checkout.isPending ? "Opening checkout…" : `Upgrade to ${tier.name}`}
                </Button>
              )}
              {tier.id !== "free" && !tier.configured && <p className="text-xs text-muted-foreground">Coming soon — this tier is not configured yet.</p>}
            </section>
          );
        })}
      </div>
      <div className="mt-6 flex flex-wrap gap-3">
        {activeTier !== "free" && <Button variant="outline" onClick={() => portal.mutateAsync().then((result) => window.location.assign(result.url))} disabled={portal.isPending}>Manage billing</Button>}
        <Button variant="ghost" onClick={() => { catalog.refetch(); status.refetch(); }}>Refresh access</Button>
        <Button variant="link" onClick={() => navigate("/research")}>Browse the free research floor</Button>
      </div>
      <p className="mt-8 text-xs leading-5 text-muted-foreground">Canceled, past-due, incomplete, or expired subscriptions return to Free access until Stripe reports an active subscription. Card details never touch MONEYLINE.</p>
    </main>
  );
}