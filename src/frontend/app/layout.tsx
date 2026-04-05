import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GrandLine — Multi-Agent Orchestration Platform",
  description:
    "Assemble your crew of AI agents. Navigate the GrandLine with PDD and TDD.",
  openGraph: {
    title: "GrandLine",
    description: "Multi-agent orchestration platform for building, testing, and deploying software.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-ocean-950 text-white antialiased">
        {children}
      </body>
    </html>
  );
}
