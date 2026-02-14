import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";

import { Pill } from "../../components/ui/Pill";
import { TrialPreviewPanel } from "./TrialPreviewPanel";
import type { MatchResultItem, MatchTier } from "./types";
import styles from "./MobileTrialPreviewDock.module.css";

type Props = {
  selectedResult: MatchResultItem | null;
  patientProfileId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onShowChecklist: () => void;
};

type VerdictCounts = {
  pass: number;
  fail: number;
  unknown: number;
  missing: number;
};

const computeCounts = (item: MatchResultItem): VerdictCounts => {
  const summary = item.match_summary;
  if (summary) {
    return {
      pass: summary.pass,
      fail: summary.fail,
      unknown: summary.unknown,
      missing: summary.missing,
    };
  }
  const allRules = item.checklist.inclusion.concat(item.checklist.exclusion);
  const pass = allRules.filter((rule) => rule.verdict === "PASS").length;
  const fail = allRules.filter((rule) => rule.verdict === "FAIL").length;
  const unknown = allRules.filter((rule) => rule.verdict === "UNKNOWN").length;
  const missing = item.checklist.missing_info.length;
  return { pass, fail, unknown, missing };
};

const tierFromItem = (item: MatchResultItem): MatchTier => {
  const tier = item.match_summary?.tier;
  if (tier === "ELIGIBLE" || tier === "POTENTIAL" || tier === "INELIGIBLE") {
    return tier;
  }
  const counts = computeCounts(item);
  if (counts.fail > 0) {
    return "INELIGIBLE";
  }
  if (counts.unknown > 0 || counts.missing > 0) {
    return "POTENTIAL";
  }
  return "ELIGIBLE";
};

const tierLabel: Record<MatchTier, string> = {
  ELIGIBLE: "Strong match",
  POTENTIAL: "Potential",
  INELIGIBLE: "Not eligible",
};

const tierTone: Record<MatchTier, "success" | "warning" | "danger"> = {
  ELIGIBLE: "success",
  POTENTIAL: "warning",
  INELIGIBLE: "danger",
};

export function MobileTrialPreviewDock({
  selectedResult,
  patientProfileId,
  open,
  onOpenChange,
  onShowChecklist,
}: Props) {
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.matchMedia("(max-width: 720px)").matches;
  });

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const media = window.matchMedia("(max-width: 720px)");
    const handler = () => setIsMobile(media.matches);
    handler();

    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", handler);
      return () => {
        media.removeEventListener("change", handler);
      };
    }

    // Safari < 14 fallback
    const legacy = media as unknown as {
      addListener?: (cb: () => void) => void;
      removeListener?: (cb: () => void) => void;
    };
    legacy.addListener?.(handler);
    return () => {
      legacy.removeListener?.(handler);
    };
  }, []);

  useEffect(() => {
    if (!isMobile && open) {
      onOpenChange(false);
    }
  }, [isMobile, open, onOpenChange]);

  const nctId = selectedResult?.nct_id ?? "";
  const title = selectedResult?.title || nctId || "Trial preview";

  const tier = useMemo(
    () => (selectedResult ? tierFromItem(selectedResult) : null),
    [selectedResult]
  );
  const counts = useMemo(
    () => (selectedResult ? computeCounts(selectedResult) : null),
    [selectedResult]
  );

  useEffect(() => {
    if (!open || !isMobile) {
      return;
    }
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open, isMobile]);

  useEffect(() => {
    if (!open || !isMobile) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onOpenChange(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, isMobile, onOpenChange]);

  if (!isMobile || !selectedResult) {
    return null;
  }

  const handleShowChecklist = () => {
    onOpenChange(false);
    onShowChecklist();
  };

  return (
    <>
      <button
        type="button"
        className={styles.dock}
        aria-label="Open trial preview"
        onClick={() => onOpenChange(true)}
      >
        <div className={styles.dockRow}>
          {tier ? <Pill tone={tierTone[tier]}>{tierLabel[tier]}</Pill> : null}
          <div className={styles.dockTitle} title={title}>
            {title}
          </div>
          {counts && (counts.fail > 0 || counts.unknown > 0) ? (
            <div className={styles.dockMeta}>
              {counts.fail > 0 ? <span className={styles.fail}>fail {counts.fail}</span> : null}
              {counts.unknown > 0 ? (
                <span className={styles.unknown}>unknown {counts.unknown}</span>
              ) : null}
            </div>
          ) : null}
        </div>
      </button>

      {open ? (
        <>
          <div className={styles.backdrop} onClick={() => onOpenChange(false)} />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Trial preview"
            className={styles.drawer}
          >
            <div className={styles.drawerHeader}>
              <div className={styles.drawerTitle}>Trial preview</div>
              <button
                type="button"
                className="ui-button ui-button--ghost ui-button--sm"
                aria-label="Close trial preview"
                onClick={() => onOpenChange(false)}
              >
                <span className="ui-button__icon" aria-hidden="true">
                  <X size={18} />
                </span>
                Close
              </button>
            </div>
            <div className={styles.drawerBody}>
              <TrialPreviewPanel
                selectedResult={selectedResult}
                patientProfileId={patientProfileId}
                onShowChecklist={handleShowChecklist}
              />
            </div>
          </div>
        </>
      ) : null}
    </>
  );
}
