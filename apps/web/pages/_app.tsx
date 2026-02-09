import type { AppProps } from "next/app";
import Link from "next/link";
import { Fraunces, Space_Grotesk } from "next/font/google";
import "../styles/globals.css";

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
  const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
  // Normalize trailing slashes so links are stable across env values.
  const docsHref = `${apiBase.replace(/\/+$/, "")}/docs`;

  return (
    <div className={`${displayFont.variable} ${bodyFont.variable} app-root`}>
      <header className="topbar">
        <div className="topbar-inner">
          <Link href="/" className="brand">
            CTMatch
          </Link>
          <nav className="topnav">
            <Link href="/" className="topnav-link">
              Browse
            </Link>
            <Link href="/match" className="topnav-link">
              Match
            </Link>
            <a
              className="topnav-link"
              href={docsHref}
              target="_blank"
              rel="noreferrer"
            >
              API Docs
            </a>
          </nav>
        </div>
      </header>
      <Component {...pageProps} />
    </div>
  );
}
