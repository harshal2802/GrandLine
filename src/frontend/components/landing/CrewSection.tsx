"use client";

import { motion } from "framer-motion";
import AnimatedSection from "./AnimatedSection";

interface CrewMember {
  name: string;
  role: string;
  description: string;
  icon: string;
}

const crew: CrewMember[] = [
  {
    name: "Captain",
    role: "Project Manager",
    description: "Decomposes user tasks into voyage plans. Assigns work to crew. Manages priorities and sequencing.",
    icon: "⚓",
  },
  {
    name: "Navigator",
    role: "Architect",
    description: "Drafts the Poneglyphs — the encoded PDD instructions that guide every step of the voyage.",
    icon: "🧭",
  },
  {
    name: "Shipwrights",
    role: "Developers",
    description: "Build the actual code. Follow Poneglyphs precisely. Work on per-agent git branches.",
    icon: "🔨",
  },
  {
    name: "Doctor",
    role: "QA Engineer",
    description: "Writes health checks (tests) BEFORE any code is written. Validates after Shipwrights build.",
    icon: "🩺",
  },
  {
    name: "Helmsman",
    role: "DevOps Engineer",
    description: "Handles deployment across three tiers. Manages containers, pipelines, and infrastructure.",
    icon: "��",
  },
];

const cardVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, delay: i * 0.1, ease: "easeOut" as const },
  }),
};

export default function CrewSection() {
  return (
    <section id="crew" className="px-6 py-24">
      <div className="mx-auto max-w-7xl">
        <AnimatedSection className="mb-16 text-center">
          <h2 className="mb-4 text-3xl font-bold text-ocean-50 sm:text-4xl">
            The Crew
          </h2>
          <p className="mx-auto max-w-2xl text-ocean-300">
            Five specialized AI agents, each with a distinct role in the voyage pipeline.
            No god agents. No freestyle. Every crew member knows their job.
          </p>
        </AnimatedSection>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {crew.map((member, i) => (
            <motion.div
              key={member.name}
              custom={i}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-30px" }}
              variants={cardVariants}
              className="rounded-xl border border-ocean-800 bg-ocean-900/50 p-6 transition-colors hover:border-ocean-600"
            >
              <div className="mb-4 text-4xl">{member.icon}</div>
              <h3 className="mb-1 text-xl font-bold text-ocean-100">
                {member.name}
              </h3>
              <p className="mb-3 text-sm font-medium text-ocean-400">
                {member.role}
              </p>
              <p className="text-sm leading-relaxed text-ocean-300">
                {member.description}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
