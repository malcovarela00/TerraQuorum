import { createFileRoute } from "@tanstack/react-router"
import { Settings2 } from "lucide-react"

import ChangePassword from "@/components/UserSettings/ChangePassword"
import DeleteAccount from "@/components/UserSettings/DeleteAccount"
import UserInformation from "@/components/UserSettings/UserInformation"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useAuth from "@/hooks/useAuth"
import { useI18n } from "@/i18n"

const tabsConfig = [
  {
    value: "my-profile",
    titleKey: "settings.myProfile",
    component: UserInformation,
  },
  {
    value: "password",
    titleKey: "settings.password",
    component: ChangePassword,
  },
  {
    value: "danger-zone",
    titleKey: "settings.dangerZone",
    component: DeleteAccount,
  },
]

export const Route = createFileRoute("/_layout/settings")({
  component: UserSettings,
  head: () => ({
    meta: [
      {
        title: "Settings - TerraQuorum",
      },
    ],
  }),
})

function UserSettings() {
  const { user: currentUser } = useAuth()
  const { t } = useI18n()
  const finalTabs = currentUser?.is_superuser
    ? tabsConfig.slice(0, 3)
    : tabsConfig

  if (!currentUser) {
    return null
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3.5">
        <span className="icon-chip size-11 rounded-xl">
          <Settings2 className="size-5.5" />
        </span>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t("settings.pageTitle")}
          </h1>
          <p className="text-muted-foreground">{t("settings.description")}</p>
        </div>
      </div>

      <Tabs defaultValue="my-profile" className="gap-4">
        <TabsList className="h-10 rounded-xl p-1">
          {finalTabs.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value} className="px-4">
              {t(tab.titleKey)}
            </TabsTrigger>
          ))}
        </TabsList>
        {finalTabs.map((tab) => (
          <TabsContent key={tab.value} value={tab.value}>
            <tab.component />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
