import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Globe, Search } from "lucide-react"
import { Suspense } from "react"

import { CountriesService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import AddItem from "@/components/Items/AddItem"
import { getColumns } from "@/components/Items/columns"
import ImportPredefinedCountries from "@/components/Items/ImportPredefinedCountries"
import PendingItems from "@/components/Pending/PendingItems"
import { useI18n } from "@/i18n"

const COUNTRIES_PAGE_SIZE = 200

async function fetchAllCountries() {
  const firstPage = await CountriesService.readCountries({
    skip: 0,
    limit: COUNTRIES_PAGE_SIZE,
  })

  if (firstPage.count <= firstPage.data.length) {
    return firstPage
  }

  const allCountries = [...firstPage.data]
  let skip = firstPage.data.length

  while (skip < firstPage.count) {
    const page = await CountriesService.readCountries({
      skip,
      limit: COUNTRIES_PAGE_SIZE,
    })
    allCountries.push(...page.data)
    skip += page.data.length
    if (page.data.length === 0) {
      break
    }
  }

  return {
    ...firstPage,
    data: allCountries,
    count: allCountries.length,
  }
}

function getCountriesQueryOptions() {
  return {
    queryFn: fetchAllCountries,
    queryKey: ["countries"],
  }
}

export const Route = createFileRoute("/_layout/items")({
  component: Items,
  head: () => ({
    meta: [
      {
        title: "Countries - TerraQuorum",
      },
    ],
  }),
})

function ItemsTableContent() {
  const { t } = useI18n()
  const { data: countries } = useSuspenseQuery(getCountriesQueryOptions())
  const customDataKeys = Array.from(
    new Set(
      countries.data.flatMap((country) =>
        Object.keys(
          (country as { custom_data?: Record<string, unknown> | null })
            .custom_data ?? {},
        ),
      ),
    ),
  ).sort((a, b) => a.localeCompare(b))
  const columns = getColumns(customDataKeys, t)

  if (countries.data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/80 bg-muted/20 px-6 py-16 text-center">
        <div className="mb-4 flex size-16 items-center justify-center rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/15 to-chart-3/15 text-primary shadow-sm">
          <Search className="size-7" />
        </div>
        <h3 className="text-lg font-semibold">{t("countries.emptyTitle")}</h3>
        <p className="text-muted-foreground">
          {t("countries.emptyDescription")}
        </p>
      </div>
    )
  }

  return (
    <DataTable
      columns={columns}
      data={countries.data}
      initialSorting={[{ id: "country_name", desc: false }]}
    />
  )
}

function ItemsTable() {
  return (
    <Suspense fallback={<PendingItems />}>
      <ItemsTableContent />
    </Suspense>
  )
}

function ItemsActions() {
  const { data: countries } = useSuspenseQuery(getCountriesQueryOptions())

  return (
    <div className="flex flex-wrap items-center gap-2">
      <ImportPredefinedCountries existingCountries={countries.data} />
      <AddItem />
    </div>
  )
}

function Items() {
  const { t } = useI18n()

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3.5">
          <span className="icon-chip size-11 rounded-xl">
            <Globe className="size-5.5" />
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              {t("countries.pageTitle")}
            </h1>
            <p className="text-muted-foreground">
              {t("countries.pageDescription")}
            </p>
          </div>
        </div>
        <Suspense fallback={<AddItem />}>
          <ItemsActions />
        </Suspense>
      </div>
      <ItemsTable />
    </div>
  )
}
