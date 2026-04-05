export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-ocean-950">
      <nav className="border-b border-ocean-800 bg-ocean-900 px-6 py-3">
        <span className="text-lg font-semibold text-ocean-200">
          Observation Deck
        </span>
      </nav>
      <main className="p-6">{children}</main>
    </div>
  );
}
