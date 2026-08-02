import { Link } from "@tanstack/react-router"
import { Compass } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useI18n } from "@/i18n"

const NotFound = () => {
  const { t } = useI18n()

  return (
    <div
      className="app-ambient flex min-h-screen flex-col items-center justify-center gap-4 p-4"
      data-testid="not-found"
    >
      <span className="flex size-16 items-center justify-center rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/15 to-chart-3/15 text-primary shadow-sm">
        <Compass className="size-8" />
      </span>
      <span className="text-gradient text-7xl font-bold leading-none tracking-tight md:text-8xl">
        404
      </span>
      <span className="text-2xl font-bold">{t("common.oops")}</span>
      <p className="max-w-md text-center text-lg text-muted-foreground">
        {t("errors.notFoundMessage")}
      </p>
      <Link to="/">
        <Button size="lg" className="mt-2">
          {t("actions.goBack")}
        </Button>
      </Link>
    </div>
  )
}

export default NotFound
