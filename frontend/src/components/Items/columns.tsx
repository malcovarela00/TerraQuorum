import type { ColumnDef } from "@tanstack/react-table"
import { Check, Copy } from "lucide-react"

import type { CountryPublic } from "@/client"
import { Button } from "@/components/ui/button"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import { useI18n } from "@/i18n"
import { cn } from "@/lib/utils"
import { ItemActionsMenu } from "./ItemActionsMenu"

type CountryWithCustomData = CountryPublic & {
  custom_data?: Record<string, unknown> | null
}

/** Sufijos reservados para metadatos internos en custom_data (no se muestran en la UI). */
const INTERNAL_DATA_SUFFIXES = ["__rationale", "__meta"] as const

function isInternalDataKey(key: string): boolean {
  return INTERNAL_DATA_SUFFIXES.some((suffix) => key.endsWith(suffix))
}

/** Etiqueta legible para claves de custom_data (sin prefijo, espacios, solo mayúscula inicial). */
function formatCustomDataColumnLabel(key: string): string {
  const spaced = key.replace(/_/g, " ").trim()
  if (!spaced) {
    return key
  }
  const lower = spaced.toLowerCase()
  return lower.charAt(0).toUpperCase() + lower.slice(1)
}

type TFunction = ReturnType<typeof useI18n>["t"]

function formatCustomDataValue(
  value: unknown,
  notAvailableLabel: string,
): string {
  if (value === null || value === undefined) {
    return notAvailableLabel
  }

  if (typeof value === "string") {
    return value.trim() ? value : notAvailableLabel
  }

  if (Array.isArray(value)) {
    return value.length
      ? value.map((item) => String(item)).join(", ")
      : notAvailableLabel
  }

  if (typeof value === "object") {
    return JSON.stringify(value)
  }

  return String(value)
}

function CopyId({ item }: { item: CountryPublic }) {
  const [copiedText, copy] = useCopyToClipboard()
  const { t } = useI18n()
  const isCopied = copiedText === item.id
  const shortId = item.id.slice(0, 4)

  return (
    <div className="flex items-center gap-1.5 group">
      <ItemActionsMenu
        item={item}
        trigger={
          <Button
            variant="link"
            className="h-auto p-0 font-mono text-xs text-muted-foreground"
          >
            {shortId}
          </Button>
        }
      />
      <Button
        variant="ghost"
        size="icon"
        className="size-6 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={() => copy(item.id)}
      >
        {isCopied ? (
          <Check className="size-3 text-green-500" />
        ) : (
          <Copy className="size-3" />
        )}
        <span className="sr-only">{t("common.copyId")}</span>
      </Button>
    </div>
  )
}

export function getColumns(
  customDataKeys: string[],
  t: TFunction,
): ColumnDef<CountryPublic>[] {
  const notAvailableLabel = t("common.notAvailable")
  const baseColumns: ColumnDef<CountryPublic>[] = [
    {
      accessorKey: "id",
      header: "ID",
      cell: ({ row }) => <CopyId item={row.original} />,
    },
    {
      id: "country_name",
      header: t("countries.countryName"),
      accessorFn: (row) => {
        const rowWithName = row as CountryPublic & {
          name?: string | null
          country_name?: string | null
        }
        return rowWithName.name ?? rowWithName.country_name ?? ""
      },
      cell: ({ row }) => {
        const rowWithName = row.original as CountryPublic & {
          name?: string | null
          country_name?: string | null
        }
        const countryName = rowWithName.name ?? rowWithName.country_name ?? ""
        return (
          <span className={cn(!countryName && "italic text-muted-foreground")}>
            {countryName || t("countries.noName")}
          </span>
        )
      },
    },
    {
      accessorKey: "alpha_2",
      header: t("countries.alpha2"),
      cell: ({ row }) => {
        const alpha2 = (
          row.original as CountryPublic & { alpha_2?: string | null }
        ).alpha_2
        return (
          <span className={cn(!alpha2 && "italic text-muted-foreground")}>
            {alpha2 || notAvailableLabel}
          </span>
        )
      },
    },
    {
      accessorKey: "iso_numeric",
      header: t("countries.isoNumeric"),
      cell: ({ row }) => {
        const iso = (
          row.original as CountryPublic & { iso_numeric?: string | null }
        ).iso_numeric
        return (
          <span className={cn(!iso && "italic text-muted-foreground")}>
            {iso || notAvailableLabel}
          </span>
        )
      },
    },
  ]

  const visibleCustomDataKeys = customDataKeys.filter(
    (key) => !isInternalDataKey(key),
  )

  const customDataColumns: ColumnDef<CountryPublic>[] =
    visibleCustomDataKeys.map((key) => ({
      id: `custom_data.${key}`,
      header: () => (
        <span className="normal-case">{formatCustomDataColumnLabel(key)}</span>
      ),
      accessorFn: (row) => {
        const item = row as CountryWithCustomData
        return item.custom_data?.[key]
      },
      cell: ({ row }) => {
        const item = row.original as CountryWithCustomData
        const value = item.custom_data?.[key]
        const formattedValue = formatCustomDataValue(value, notAvailableLabel)
        return (
          <span
            className={cn(
              formattedValue === notAvailableLabel &&
                "italic text-muted-foreground",
            )}
          >
            {formattedValue}
          </span>
        )
      },
    }))

  return [...baseColumns, ...customDataColumns]
}
