"use client";

import { useEffect, useState } from "react";

const navLinks = [
  { label: "Crew", href: "#crew" },
  { label: "Pipeline", href: "#pipeline" },
  { label: "Observation Deck", href: "#observation-deck" },
  { label: "GitHub", href: "https://github.com/harshal2802/GrandLine", external: true },
];

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 50);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <nav
      className={`fixed top-0 z-50 w-full transition-colors duration-300 ${
        scrolled ? "bg-ocean-900/95 backdrop-blur-sm border-b border-ocean-800" : "bg-transparent"
      }`}
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        <a href="#" className="text-xl font-bold text-ocean-100">
          GrandLine
        </a>

        <div className="hidden items-center gap-8 md:flex">
          {navLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="text-sm text-ocean-300 transition-colors hover:text-ocean-100"
              {...(link.external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
            >
              {link.label}
            </a>
          ))}
          <span
            className="cursor-default rounded-lg bg-ocean-700/50 px-4 py-2 text-sm text-ocean-400"
            title="Coming soon"
          >
            Chart a Course
          </span>
        </div>
      </div>
    </nav>
  );
}
