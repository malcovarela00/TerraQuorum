import {
  createFileRoute,
  Outlet,
  redirect,
  useRouterState,
} from "@tanstack/react-router"

import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { useI18n } from "@/i18n"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/_layout")({
  component: Layout,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }
  },
})

function Layout() {
  const router = useRouterState()
  const { user: currentUser } = useAuth()
  const { t, locale } = useI18n()
  const isDashboard = router.location.pathname === "/"

  const todayLabel = new Date().toLocaleDateString(
    locale === "es" ? "es-ES" : "en-US",
    { weekday: "long", day: "numeric", month: "long" },
  )

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="app-ambient">
        <header className="glass-panel sticky top-0 z-10 shrink-0 rounded-none border-x-0 border-t-0">
          <div
            className={cn(
              "mx-auto flex w-full items-center gap-3 px-4",
              isDashboard ? "min-h-20 max-w-[1600px] py-3" : "h-16 max-w-7xl",
            )}
          >
            <SidebarTrigger className="-ml-1 text-muted-foreground hover:text-foreground" />
            {isDashboard ? (
              <div className="flex min-w-0 flex-1 items-center justify-between gap-3">
                <div className="min-w-0">
                  <h1 className="text-gradient truncate text-2xl font-semibold tracking-tight lg:text-3xl">
                    {t("dashboard.greeting", {
                      name: currentUser?.full_name || currentUser?.email || "",
                    })}
                  </h1>
                  <p className="mt-0.5 text-sm text-muted-foreground lg:text-base">
                    {t("dashboard.welcomeBack")}
                  </p>
                </div>
                <span className="hidden shrink-0 items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-3.5 py-1.5 text-xs font-medium capitalize text-muted-foreground md:inline-flex">
                  <span className="size-1.5 rounded-full bg-primary" />
                  {todayLabel}
                </span>
              </div>
            ) : null}
          </div>
        </header>
        <main className="flex-1 p-6 md:p-8">
          <div
            className={cn(
              "animate-page-in mx-auto w-full",
              isDashboard ? "max-w-[1600px]" : "max-w-7xl",
            )}
          >
            <Outlet />
          </div>
        </main>
        <Footer />
      </SidebarInset>
    </SidebarProvider>
  )
}
