"use client";

import { motion } from "framer-motion";
import AnimatedSection from "./AnimatedSection";

interface PipelineStage {
  name: string;
  label: string;
  description: string;
}

const stages: PipelineStage[] = [
  { name: "PDD", label: "Poneglyphs", description: "Navigator drafts the encoded instructions" },
  { name: "TDD", label: "Health Checks", description: "Doctor writes tests before code exists" },
  { name: "Implement", label: "Build", description: "Shipwrights code following Poneglyphs" },
  { name: "Review", label: "Validate", description: "Doctor runs tests and verifies output" },
  { name: "Deploy", label: "Set Sail", description: "Helmsman deploys across three tiers" },
];

const stageVariants = {
  hidden: { opacity: 0, x: -20 },
  visible: (i: number) => ({
    opacity: 1,
    x: 0,
    transition: { duration: 0.4, delay: i * 0.15, ease: "easeOut" as const },
  }),
};

export default function PipelineSection() {
  return (
    <section id="pipeline" className="bg-ocean-900/30 px-6 py-24">
      <div className="mx-auto max-w-7xl">
        <AnimatedSection className="mb-16 text-center">
          <h2 className="mb-4 text-3xl font-bold text-ocean-50 sm:text-4xl">
            The Voyage Pipeline
          </h2>
          <p className="mx-auto max-w-2xl text-ocean-300">
            Every task flows through this structured pipeline. No shortcuts. No skipping stages.
          </p>
        </AnimatedSection>

        {/* Pipeline visualization */}
        <div className="mb-12 flex flex-col items-center gap-4 md:flex-row md:justify-center md:gap-0">
          {stages.map((stage, i) => (
            <motion.div
              key={stage.name}
              custom={i}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-30px" }}
              variants={stageVariants}
              className="flex items-center"
            >
              <div className="flex flex-col items-center text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-full border-2 border-ocean-500 bg-ocean-900 text-sm font-bold text-ocean-300 sm:h-20 sm:w-20">
                  {stage.name}
                </div>
                <p className="mt-3 text-sm font-semibold text-ocean-200">
                  {stage.label}
                </p>
                <p className="mt-1 max-w-[140px] text-xs text-ocean-400">
                  {stage.description}
                </p>
              </div>

              {/* Arrow connector */}
              {i < stages.length - 1 && (
                <div className="mx-2 hidden h-px w-8 bg-ocean-600 md:block lg:w-12">
                  <div className="relative top-[-3px] left-full h-0 w-0 border-t-4 border-b-4 border-l-6 border-t-transparent border-b-transparent border-l-ocean-600" />
                </div>
              )}
              {i < stages.length - 1 && (
                <div className="h-6 w-px bg-ocean-600 md:hidden" />
              )}
            </motion.div>
          ))}
        </div>

        <AnimatedSection className="text-center" delay={0.5}>
          <p className="text-lg italic text-ocean-400">
            &ldquo;PDD and TDD aren&apos;t optional — they&apos;re the{" "}
            <span className="font-semibold text-ocean-300">Log Pose</span>.
            Without them, the crew doesn&apos;t sail.&rdquo;
          </p>
        </AnimatedSection>
      </div>
    </section>
  );
}
