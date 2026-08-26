import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import "./globals.css";
import { AuroraBackground } from "@/components/AuroraBackground";

// Display face for headlines/nav/buttons only — body copy keeps the system
// stack (--font-sans, a Track 0 token) untouched. Exposed as --font-display,
// a new CSS variable, so .font-display in globals.css can opt in per element.
const outfit = Outfit({
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "LaunchPad",
  description: "Your personal job-search command center.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`h-full antialiased ${outfit.variable}`}>
      <body className="min-h-full flex flex-col bg-bg text-foreground">
        <AuroraBackground />
        {children}
      </body>
    </html>
  );
}
