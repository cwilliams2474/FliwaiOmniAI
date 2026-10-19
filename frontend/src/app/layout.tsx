import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "OmniAI", description: "Self-hosted AI and IT operations platform" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Optional web fonts; the system font stack is used when Google Fonts is unreachable. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=Schibsted+Grotesk:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
