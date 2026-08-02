import { Link } from "@tanstack/react-router"
import { TriangleAlert } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useI18n } from "@/i18n"

const ErrorComponent = () => {
  const { t } = useI18n()

  return (
    <div
      className="app-ambient flex min-h-screen flex-col items-center justify-center gap-4 p-4"
      data-testid="error-component"
    >
      <span className="flex size-16 items-center justify-center rounded-2xl border border-destructive/25 bg-destructive/10 text-destructive shadow-sm">
        <TriangleAlert className="size-8" />
      </span>
      <span className="text-gradient text-5xl font-bold leading-none tracking-tight md:text-7xl">
        {t("common.error")}
      </span>
      <span className="text-2xl font-bold">{t("common.oops")}</span>
      <p className="max-w-md text-center text-lg text-muted-foreground">
        {t("errors.tryAgain")}
      </p>
      <Link to="/">
        <Button size="lg" className="mt-2">
          {t("actions.goHome")}
        </Button>
      </Link>
    </div>
  )
}

export default ErrorComponent
