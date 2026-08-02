import { FaGithub } from "react-icons/fa"

const socialLinks = [
  {
    icon: FaGithub,
    href: "https://github.com/malcovarela00/TerraQuorum",
    label: "GitHub",
  },
]

export function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="mt-auto border-t border-border/60 bg-muted/10 py-5 px-6">
      <div className="flex flex-col items-center justify-between gap-4 sm:flex-row sm:px-2">
        <p className="text-muted-foreground text-sm tracking-wide">
          TerraQuorum <span className="mx-1 text-border">·</span> {currentYear}
        </p>
        <div className="flex items-center gap-4">
          {socialLinks.map(({ icon: Icon, href, label }) => (
            <a
              key={label}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={label}
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              <Icon className="h-5 w-5" />
            </a>
          ))}
        </div>
      </div>
    </footer>
  )
}
