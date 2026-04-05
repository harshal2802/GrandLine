"use client";

import { motion } from "framer-motion";
import AnimatedSection from "./AnimatedSection";

interface DeckView {
  name: string;
  subtitle: string;
  description: string;
  visual: string;
}

const views: DeckView[] = [
  {
    name: "Sea Chart",
    subtitle: "Board View",
    description: "Tasks flowing through waters: PDD → TDD → Implement → Review → Deployed. Kanban-style columns for every pipeline stage.",
    visual: "▓▓░░ → ▓▓▓░ → ▓▓▓▓",
  },
  {
    name: "Crew Map",
    subtitle: "Graph View",
    description: "Live DAG showing agents communicating via Den Den Mushi. See who's talking to whom in real time.",
    visual: "◉─── ◉ ───◉\n │       │\n ◉ ─── ◉",
  },
  {
    name: "Ship's Log",
    subtitle: "Timeline View",
    description: "Chronological record of every agent action. Filter by crew member, search by keyword, trace any decision.",
    visual: "09:41 ◆ Captain\n09:42 ◆ Navigator\n09:43 ◆ Doctor",
  },
];

const cardVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, delay: i * 0.15, ease: "easeOut" as const },
  }),
};

export default function ObservationDeckPreview() {
  return (
    <section id="observation-deck" className="px-6 py-24">
      <div className="mx-auto max-w-7xl">
        <AnimatedSection className="mb-16 text-center">
          <h2 className="mb-4 text-3xl font-bold text-ocean-50 sm:text-4xl">
            The Observation Deck
          </h2>
          <p className="mx-auto max-w-2xl text-ocean-300">
            Watch the voyage unfold in real time. Three views, one war room.
          </p>
        </AnimatedSection>

        <div className="grid gap-8 md:grid-cols-3">
          {views.map((view, i) => (
            <motion.div
              key={view.name}
              custom={i}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-30px" }}
              variants={cardVariants}
              className="overflow-hidden rounded-xl border border-ocean-800 bg-ocean-900/50"
            >
              {/* Visual preview area */}
              <div className="flex h-40 items-center justify-center bg-ocean-900 p-4 font-mono text-xs text-ocean-500">
                <pre className="text-center">{view.visual}</pre>
              </div>

              <div className="p-6">
                <h3 className="mb-1 text-lg font-bold text-ocean-100">
                  {view.name}
                </h3>
                <p className="mb-3 text-sm font-medium text-ocean-400">
                  {view.subtitle}
                </p>
                <p className="text-sm leading-relaxed text-ocean-300">
                  {view.description}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
