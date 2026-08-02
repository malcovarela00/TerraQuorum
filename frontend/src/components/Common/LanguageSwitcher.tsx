import { Languages } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { type Locale, useI18n } from "@/i18n"

const LOCALES: Locale[] = ["es", "en"]

export function SidebarLanguageSwitcher() {
  const { isMobile } = useSidebar()
  const { locale, setLocale, t } = useI18n()

  return (
    <SidebarMenuItem>
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <SidebarMenuButton tooltip={t("app.language")}>
            <Languages className="size-4 text-muted-foreground" />
            <span>{t("app.language")}</span>
          </SidebarMenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          side={isMobile ? "top" : "right"}
          align="end"
          className="w-(--radix-dropdown-menu-trigger-width) min-w-56"
        >
          {LOCALES.map((item) => (
            <DropdownMenuItem key={item} onClick={() => setLocale(item)}>
              <span className="w-6 font-mono text-xs uppercase">{item}</span>
              {t(`language.${item}`)}
              {locale === item ? (
                <span className="ml-auto text-xs text-muted-foreground">✓</span>
              ) : null}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem>
  )
}

export function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n()

  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="icon" aria-label={t("app.language")}>
          <Languages className="h-[1.2rem] w-[1.2rem]" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {LOCALES.map((item) => (
          <DropdownMenuItem key={item} onClick={() => setLocale(item)}>
            <span className="w-6 font-mono text-xs uppercase">{item}</span>
            {t(`language.${item}`)}
            {locale === item ? (
              <span className="ml-auto text-xs text-muted-foreground">✓</span>
            ) : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
