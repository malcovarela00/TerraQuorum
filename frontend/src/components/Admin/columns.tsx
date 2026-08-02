import type { ColumnDef } from "@tanstack/react-table"

import type { UserPublic } from "@/client"
import { Badge } from "@/components/ui/badge"
import type { useI18n } from "@/i18n"
import { cn } from "@/lib/utils"
import { UserActionsMenu } from "./UserActionsMenu"

export type UserTableData = UserPublic & {
  isCurrentUser: boolean
}

type TFunction = ReturnType<typeof useI18n>["t"]

export function getUserColumns(t: TFunction): ColumnDef<UserTableData>[] {
  return [
    {
      accessorKey: "full_name",
      header: t("auth.fullName"),
      cell: ({ row }) => {
        const fullName = row.original.full_name
        return (
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "font-medium",
                !fullName && "text-muted-foreground",
              )}
            >
              {fullName || t("common.na")}
            </span>
            {row.original.isCurrentUser && (
              <Badge variant="outline" className="text-xs">
                {t("common.you")}
              </Badge>
            )}
          </div>
        )
      },
    },
    {
      accessorKey: "email",
      header: t("common.email"),
      cell: ({ row }) => (
        <span className="text-muted-foreground">{row.original.email}</span>
      ),
    },
    {
      accessorKey: "is_superuser",
      header: t("common.role"),
      cell: ({ row }) => (
        <Badge variant={row.original.is_superuser ? "default" : "secondary"}>
          {row.original.is_superuser ? t("common.superuser") : t("common.user")}
        </Badge>
      ),
    },
    {
      accessorKey: "is_active",
      header: t("common.status"),
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "size-2 rounded-full",
              row.original.is_active
                ? "bg-emerald-500 ring-3 ring-emerald-500/20"
                : "bg-muted-foreground/40 ring-3 ring-muted-foreground/10",
            )}
          />
          <span
            className={row.original.is_active ? "" : "text-muted-foreground"}
          >
            {row.original.is_active ? t("common.active") : t("common.inactive")}
          </span>
        </div>
      ),
    },
    {
      id: "actions",
      header: () => <span className="sr-only">{t("common.actions")}</span>,
      cell: ({ row }) => (
        <div className="flex justify-end">
          <UserActionsMenu user={row.original} />
        </div>
      ),
    },
  ]
}
