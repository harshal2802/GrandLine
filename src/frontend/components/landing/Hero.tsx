"use client";

import { motion } from "framer-motion";

export default function Hero() {
  return (
    <section className="relative flex min-h-screen items-center justify-center overflow-hidden px-6">
      {/* Animated gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-ocean-950 via-ocean-900 to-ocean-950">
        <div className="absolute inset-0 animate-pulse-slow bg-[radial-gradient(ellipse_at_30%_20%,rgba(14,165,233,0.08),transparent_50%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_70%_80%,rgba(56,189,248,0.05),transparent_50%)]" />
      </div>

      <div className="relative z-10 mx-auto max-w-4xl text-center">
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="mb-6 text-4xl font-bold leading-tight tracking-tight text-ocean-50 sm:text-5xl md:text-6xl"
        >
          Assemble your crew.{" "}
          <span className="text-ocean-400">Navigate the GrandLine.</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
          className="mx-auto mb-10 max-w-2xl text-lg text-ocean-300 sm:text-xl"
        >
          A multi-agent orchestration platform where AI agents voyage through a
          disciplined pipeline to build, test, and deploy software.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.4, ease: "easeOut" }}
        >
          <a
            href="#crew"
            className="inline-block rounded-lg bg-ocean-500 px-8 py-3 font-semibold text-ocean-950 transition-colors hover:bg-ocean-400"
          >
            Get Started
          </a>
        </motion.div>
      </div>

      {/* Scroll indicator */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.2 }}
        className="absolute bottom-8 left-1/2 -translate-x-1/2"
      >
        <div className="flex flex-col items-center gap-2 text-ocean-500">
          <span className="text-xs uppercase tracking-widest">Scroll</span>
          <div className="h-8 w-px animate-bounce bg-ocean-500/50" />
        </div>
      </motion.div>
    </section>
  );
}
