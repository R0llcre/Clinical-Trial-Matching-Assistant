import Link from "next/link";
import { useRouter } from "next/router";
import { Menu, X } from "lucide-react";
import { useEffect, useId, useState } from "react";

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

export function MobileNavDrawer({ items }: Props) {
  const router = useRouter();
  const drawerId = useId();
  const [open, setOpen] = useState(false);
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

      {showOverlay ? (
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
              <div className={styles.title}>Navigation</div>
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
                const className = `${styles.link} ${item.active ? styles.linkActive : ""}`;
                if (item.external) {
                  return (
                    <a
                      key={item.label}
                      className={className}
                      href={item.href}
                      target="_blank"
                      rel="noreferrer"
                      onClick={() => setOpen(false)}
                    >
                      {item.label}
                    </a>
                  );
                }
                return (
                  <Link
                    key={item.label}
                    className={className}
                    href={item.href}
                    onClick={() => setOpen(false)}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>

            <div className={styles.footer} />
          </aside>
        </>
      ) : null}
    </>
  );
}

