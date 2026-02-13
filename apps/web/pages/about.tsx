import { AlertTriangle, Database, ShieldCheck, Stethoscope } from "lucide-react";

import { Shell } from "../components/layout/Shell";
import { Card } from "../components/ui/Card";

export default function AboutPage() {
  return (
    <Shell
      kicker="About"
      title="Clinical Trial Matching Assistant"
      subtitle="Scope, safety boundaries, and known limitations for this preview environment."
    >
      <div className="detail-grid">
        <section className="detail-main">
          <Card className="detail-card">
            <h2 className="detail-section__title">
              <Database size={18} aria-hidden="true" />
              Data sources
            </h2>
            <p className="detail-section__body">
              Trial data is sourced from public ClinicalTrials.gov records. Demo patient
              profiles use synthetic values for illustration only.
            </p>
          </Card>

          <Card className="detail-card">
            <h2 className="detail-section__title">
              <Stethoscope size={18} aria-hidden="true" />
              Not medical advice
            </h2>
            <p className="detail-section__body">
              This application is an informational aid and does not provide diagnosis,
              treatment, or medical recommendations. Always confirm eligibility with your
              clinician and official study coordinators.
            </p>
          </Card>

          <Card className="detail-card">
            <h2 className="detail-section__title">
              <ShieldCheck size={18} aria-hidden="true" />
              Privacy boundary
            </h2>
            <p className="detail-section__body">
              Do not enter real personal identifiers or protected health information. This
              preview is designed for synthetic or manually curated non-identifying inputs.
            </p>
          </Card>

          <Card className="detail-card">
            <h2 className="detail-section__title">
              <AlertTriangle size={18} aria-hidden="true" />
              Model and parser limitations
            </h2>
            <p className="detail-section__body">
              Match tiers and parsed criteria can contain false positives, false negatives, and
              unknown fields. Results should be treated as triage signals and manually reviewed
              before any real-world decision.
            </p>
          </Card>
        </section>
      </div>
    </Shell>
  );
}
