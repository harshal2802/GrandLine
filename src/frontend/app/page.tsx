export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="text-center">
        <h1 className="mb-4 text-5xl font-bold tracking-tight text-ocean-100">
          GrandLine
        </h1>
        <p className="mb-8 text-xl text-ocean-300">
          Multi-Agent Orchestration Platform
        </p>
        <div className="rounded-lg border border-ocean-700 bg-ocean-900/50 px-8 py-6">
          <p className="text-ocean-400">
            Observation Deck coming soon.
          </p>
          <p className="mt-2 text-sm text-ocean-500">
            Assemble your crew. Navigate the GrandLine.
          </p>
        </div>
      </div>
    </main>
  );
}
