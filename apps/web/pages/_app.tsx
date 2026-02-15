import type { AppProps } from "next/app";
import Link from "next/link";
import { useRouter } from "next/router";
import { Fraunces, Space_Grotesk } from "next/font/google";
import "../styles/globals.css";
import { MobileNavDrawer } from "../components/layout/MobileNavDrawer";

const displayFont = Fraunces({
  subsets: ["latin"],
  weight: ["600", "700"],
  variable: "--font-display",
  display: "swap",
});

const bodyFont = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-body",
  display: "swap",
});

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter();
  const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
  // Normalize trailing slashes so links are stable across env values.
  const docsHref = `${apiBase.replace(/\/+$/, "")}/docs`;

  const isBrowse = router.pathname === "/";
  const isPatients = router.pathname.startsWith("/patients");
  const isMatch =
    router.pathname === "/match" || router.pathname.startsWith("/matches");
  const isAbout = router.pathname === "/about";

  const navItems = [
    { label: "Browse", href: "/", active: isBrowse },
    { label: "Patients", href: "/patients", active: isPatients },
    { label: "Match", href: "/match", active: isMatch },
    { label: "About", href: "/about", active: isAbout },
    { label: "API Docs", href: docsHref, external: true },
  ];

  return (
    <div className={`${displayFont.variable} ${bodyFont.variable} app-root`}>
      <header className="topbar">
        <div className="topbar-inner">
          <Link href="/" className="brand">
            <span className="brand-mark" aria-hidden="true">
              <span className="brand-mark-dot" />
            </span>
            <span className="brand-text">
              <span className="brand-name">CTMatch</span>
              <span className="brand-subtitle">clinical trial explorer</span>
            </span>
          </Link>
          <nav className="topnav">
            {navItems.map((item) => {
              if (item.external) {
                return (
                  <a
                    key={item.label}
                    className="topnav-link"
                    href={item.href}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {item.label}
                  </a>
                );
              }
              return (
                <Link
                  key={item.label}
                  href={item.href}
                  className={`topnav-link ${item.active ? "active" : ""}`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <MobileNavDrawer items={navItems} />
        </div>
      </header>
      <Component {...pageProps} />
      <footer className="site-footer">
        <div className="footer-inner">
          <div className="footer-blurb">
            <span className="footer-brand">CTMatch</span>
            <p className="footer-note">
              Preview app for exploring public trial listings. Not medical
              advice. Always confirm eligibility with your care team and the
              official study record.
            </p>
          </div>
          <div className="footer-links">
            <Link href="/patients">Patients</Link>
            <Link href="/about">About</Link>
            <a href={docsHref} target="_blank" rel="noreferrer">
              API docs
            </a>
            <a href="https://clinicaltrials.gov/" target="_blank" rel="noreferrer">
              ClinicalTrials.gov
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
