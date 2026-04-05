const footerLinks = [
  { label: "GitHub", href: "https://github.com/harshal2802/GrandLine" },
  { label: "Docs", href: "/docs" },
  { label: "API Reference", href: "/api/docs" },
];

export default function Footer() {
  return (
    <footer className="border-t border-ocean-800 bg-ocean-950 px-6 py-12">
      <div className="mx-auto max-w-7xl text-center">
        <p className="mb-6 text-lg font-semibold text-ocean-200">
          Assemble your crew. Navigate the GrandLine.
        </p>

        <div className="mb-8 flex justify-center gap-8">
          {footerLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="text-sm text-ocean-400 transition-colors hover:text-ocean-200"
            >
              {link.label}
            </a>
          ))}
        </div>

        <p className="text-xs text-ocean-600">
          &copy; {new Date().getFullYear()} GrandLine. MIT License.
        </p>
      </div>
    </footer>
  );
}
