import { BarChart3, BookOpen, Newspaper, Users, Swords } from "lucide-react";
import { Link } from "wouter";
import { ResearchTag } from "@/components/research-tag";
import {
  researchDestinations,
  researchHubStructuredData,
  StructuredData,
} from "@/lib/structured-data";

const destinationIcons = {
  Players: Users,
  Matchups: Swords,
  "Season outlook": BarChart3,
  Wire: Newspaper,
} as const;

const destinations = researchDestinations.map((destination) => ({
  ...destination,
  icon: destinationIcons[destination.label as keyof typeof destinationIcons],
}));

export default function ResearchHub() {
  return (
    <>
      <StructuredData data={researchHubStructuredData(destinations)} />
      <main className="page-wrap">
        <div className="page-heading">
          <div>
            <div className="eyebrow">Go deeper without losing the thread</div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Research</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Start with a player, matchup, season, or wire note. These surfaces provide context and receipts around the daily model view.
            </p>
          </div>
          <BookOpen className="hidden h-10 w-10 text-primary/70 sm:block" aria-hidden="true" />
        </div>
        <div className="research-grid">
          {destinations.map(({ href, label, description, icon: Icon }) => (
            <Link href={href} key={href} className="research-card" data-testid={`link-research-${label.toLowerCase().replace(/\s+/g, "-")}`}>
              <div className="research-card-icon"><Icon aria-hidden="true" /></div>
              <div>
                <h2>{label}</h2>
                <p>{description}</p>
              </div>
              <span className="research-card-arrow" aria-hidden="true">→</span>
            </Link>
          ))}
        </div>
        <div className="research-note">
          <span className="status-label status-label-neutral">Research rule</span>
          <span>Wire, pulse, and injury information is context only. It does not silently move the team price.</span>
        </div>
        <ResearchTag />
      </main>
    </>
  );
}
