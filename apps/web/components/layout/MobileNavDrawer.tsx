import Link from "next/link";
import { useRouter } from "next/router";
import {
  ArrowUpRight,
  BookOpen,
  ChevronRight,
  Info,
  Menu,
  Search,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { type ReactNode, useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";

import styles from "./MobileNavDrawer.module.css";

type NavItem = {
  label: string;
  href: string;
  active?: boolean;
  external?: boolean;
};

type Props = {
  items: NavItem[];
};

const itemDescriptions: Record<string, string> = {
  Browse: "Explore synced trials and filters.",
  Patients: "Save patient profiles and match history.",
  Match: "Run a match with structured checks.",
  About: "Data sources, limits, and safety notes.",
  "API Docs": "OpenAPI / Swagger reference.",
};

const itemIcons: Record<string, ReactNode> = {
  Browse: <Search size={18} />,
  Patients: <Users size={18} />,
  Match: <Sparkles size={18} />,
  About: <Info size={18} />,
  "API Docs": <BookOpen size={18} />,
};

export function MobileNavDrawer({ items }: Props) {
  const router = useRouter();
  const drawerId = useId();
  const [open, setOpen] = useState(false);
  const [portalTarget, setPortalTarget] = useState<HTMLElement | null>(null);
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.matchMedia("(max-width: 720px)").matches;
  });

  useEffect(() => {
    setPortalTarget(document.body);
  }, []);

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
      setOpen(false);
    }
  }, [isMobile, open]);

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
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, isMobile]);

  useEffect(() => {
    const close = () => setOpen(false);
    router.events.on("routeChangeStart", close);
    return () => {
      router.events.off("routeChangeStart", close);
    };
  }, [router.events]);

  const showOverlay = open && isMobile;
  const shouldRenderOverlay = showOverlay && portalTarget;

  return (
    <>
      <button
        type="button"
        className="ui-button ui-button--ghost ui-button--sm topnavToggle"
        aria-haspopup="dialog"
        aria-controls={drawerId}
        aria-expanded={showOverlay}
        onClick={() => setOpen(true)}
      >
        <span className="ui-button__icon" aria-hidden="true">
          <Menu size={18} />
        </span>
        Menu
      </button>

      {shouldRenderOverlay
        ? createPortal(
            <>
              <div className={styles.backdrop} onClick={() => setOpen(false)} />
              <aside
                id={drawerId}
                role="dialog"
                aria-modal="true"
                aria-label="Navigation"
                className={styles.drawer}
              >
                <div className={styles.header}>
                  <div className={styles.headerLeft}>
                    <div className={styles.brandMark} aria-hidden="true">
                      <div className={styles.brandDot} />
                    </div>
                    <div>
                      <div className={styles.title}>CTMatch</div>
                      <div className={styles.subtitle}>Menu</div>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="ui-button ui-button--ghost ui-button--sm"
                    aria-label="Close navigation"
                    onClick={() => setOpen(false)}
                  >
                    <span className="ui-button__icon" aria-hidden="true">
                      <X size={18} />
                    </span>
                    Close
                  </button>
                </div>

                <nav className={styles.body}>
                  {items.map((item) => {
                    const className = `${styles.link} ${
                      item.active ? styles.linkActive : ""
                    }`;
                    const description = itemDescriptions[item.label] ?? "";
                    const icon = itemIcons[item.label] ?? <ChevronRight size={18} />;
                    const suffix = item.external ? (
                      <ArrowUpRight size={16} />
                    ) : (
                      <ChevronRight size={16} />
                    );
                    if (item.external) {
                      return (
                        <a
                          key={item.label}
                          className={className}
                          href={item.href}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={item.label}
                          onClick={() => setOpen(false)}
                        >
                          <span className={styles.linkIcon} aria-hidden="true">
                            {icon}
                          </span>
                          <span className={styles.linkText}>
                            <span className={styles.linkLabel}>{item.label}</span>
                            {description ? (
                              <span className={styles.linkDescription} aria-hidden="true">
                                {description}
                              </span>
                            ) : null}
                          </span>
                          <span className={styles.linkSuffix} aria-hidden="true">
                            {suffix}
                          </span>
                        </a>
                      );
                    }
                    return (
                      <Link
                        key={item.label}
                        className={className}
                        href={item.href}
                        aria-label={item.label}
                        onClick={() => setOpen(false)}
                      >
                        <span className={styles.linkIcon} aria-hidden="true">
                          {icon}
                        </span>
                        <span className={styles.linkText}>
                          <span className={styles.linkLabel}>{item.label}</span>
                          {description ? (
                            <span className={styles.linkDescription} aria-hidden="true">
                              {description}
                            </span>
                          ) : null}
                        </span>
                        <span className={styles.linkSuffix} aria-hidden="true">
                          {suffix}
                        </span>
                      </Link>
                    );
                  })}
                </nav>

                <div className={styles.footer} />
              </aside>
            </>,
            portalTarget
          )
        : null}
    </>
  );
}
