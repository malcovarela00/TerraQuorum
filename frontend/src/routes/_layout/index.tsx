import { createFileRoute } from "@tanstack/react-router"

import DashboardAiChat from "@/components/Chat/DashboardAiChat"
import WorldMapCard from "@/components/Map/WorldMapCard"
import { useSidebar } from "@/components/ui/sidebar"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [
      {
        title: "Dashboard - TerraQuorum",
      },
    ],
  }),
})

function Dashboard() {
  const { isMobile, state } = useSidebar()
  const isSidebarCollapsed = !isMobile && state === "collapsed"

  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-6 xl:gap-8",
        isSidebarCollapsed
          ? "xl:grid-cols-[minmax(0,2fr)_minmax(420px,1fr)]"
          : "xl:grid-cols-[minmax(0,1.85fr)_minmax(420px,1fr)]",
      )}
    >
      <WorldMapCard />
      <DashboardAiChat />
    </div>
  )
}
