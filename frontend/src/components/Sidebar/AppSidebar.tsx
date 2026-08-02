import { Briefcase, Home, Users } from "lucide-react"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { SidebarLanguageSwitcher } from "@/components/Common/LanguageSwitcher"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarSeparator,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { useI18n } from "@/i18n"
import { type Item, Main } from "./Main"
import { User } from "./User"

export function AppSidebar() {
  const { user: currentUser } = useAuth()
  const { t } = useI18n()
  const baseItems: Item[] = [
    { icon: Home, title: t("dashboard.nav"), path: "/" },
    { icon: Briefcase, title: t("countries.pageTitle"), path: "/items" },
  ]

  const items = currentUser?.is_superuser
    ? [...baseItems, { icon: Users, title: "Admin", path: "/admin" }]
    : baseItems

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border/60">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:items-center group-data-[collapsible=icon]:px-0">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <Main items={items} label={t("nav.platform")} />
      </SidebarContent>
      <SidebarFooter className="gap-1.5 pb-3">
        <SidebarMenu className="gap-1">
          <SidebarLanguageSwitcher />
          <SidebarAppearance />
        </SidebarMenu>
        <SidebarSeparator className="mx-0 bg-sidebar-border/70" />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
