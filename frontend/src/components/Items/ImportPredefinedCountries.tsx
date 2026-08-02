import { useMutation, useQueryClient } from "@tanstack/react-query"
import { ListPlus, Search } from "lucide-react"
import { useMemo, useState } from "react"

import {
  CountriesService,
  type CountryCreate,
  type CountryPublic,
} from "@/client"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { useI18n } from "@/i18n"
import { cn } from "@/lib/utils"
import { handleError } from "@/utils"
import { PREDEFINED_COUNTRIES } from "./predefinedCountries"

type CountryWithName = CountryPublic & {
  country_name?: string | null
}

interface ImportPredefinedCountriesProps {
  existingCountries: CountryPublic[]
}

function getCountryName(country: CountryCreate | CountryWithName): string {
  if (country.name) {
    return country.name
  }
  return "country_name" in country ? (country.country_name ?? "") : ""
}

function getCountryKey(country: CountryCreate): string {
  return country.alpha_2 ?? `${country.name}-${country.iso_numeric}`
}

const ImportPredefinedCountries = ({
  existingCountries,
}: ImportPredefinedCountriesProps) => {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { t } = useI18n()

  const existingAlpha2 = useMemo(
    () =>
      new Set(
        existingCountries
          .map((country) => country.alpha_2)
          .filter((value): value is string => Boolean(value)),
      ),
    [existingCountries],
  )
  const existingIsoNumeric = useMemo(
    () =>
      new Set(
        existingCountries
          .map((country) => country.iso_numeric)
          .filter((value): value is string => Boolean(value)),
      ),
    [existingCountries],
  )

  const availableCountryKeys = useMemo(
    () =>
      PREDEFINED_COUNTRIES.filter(
        (country) =>
          !existingAlpha2.has(country.alpha_2 ?? "") &&
          !existingIsoNumeric.has(country.iso_numeric ?? ""),
      ).map(getCountryKey),
    [existingAlpha2, existingIsoNumeric],
  )

  const filteredCountries = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase()
    if (!normalizedSearch) {
      return PREDEFINED_COUNTRIES
    }
    return PREDEFINED_COUNTRIES.filter((country) =>
      [country.name, country.alpha_2, country.iso_numeric]
        .filter(Boolean)
        .some((value) =>
          String(value).toLocaleLowerCase().includes(normalizedSearch),
        ),
    )
  }, [search])

  const selectedCountries = useMemo(
    () =>
      PREDEFINED_COUNTRIES.filter((country) =>
        selectedKeys.has(getCountryKey(country)),
      ),
    [selectedKeys],
  )

  const allAvailableSelected =
    availableCountryKeys.length > 0 &&
    availableCountryKeys.every((key) => selectedKeys.has(key))

  const mutation = useMutation({
    mutationFn: (countries: CountryCreate[]) =>
      CountriesService.createCountriesBulk({
        requestBody: { countries },
      }),
    onSuccess: (result) => {
      showSuccessToast(
        t("countries.predefinedImportSuccess", {
          created: result.created.length,
          skipped: result.skipped.length,
        }),
      )
      setSelectedKeys(new Set())
      setSearch("")
      setIsOpen(false)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["countries"] })
    },
  })

  const toggleCountry = (country: CountryCreate, checked: boolean) => {
    const key = getCountryKey(country)
    setSelectedKeys((current) => {
      const next = new Set(current)
      if (checked) {
        next.add(key)
      } else {
        next.delete(key)
      }
      return next
    })
  }

  const toggleAllAvailable = () => {
    if (allAvailableSelected) {
      setSelectedKeys(new Set())
      return
    }

    setSelectedKeys(new Set(availableCountryKeys))
  }

  const clearSelection = () => {
    setSelectedKeys(new Set())
  }

  const importSelected = () => {
    if (selectedCountries.length > 0) {
      mutation.mutate(selectedCountries)
    }
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        setIsOpen(open)
        if (!open) {
          setSearch("")
          setSelectedKeys(new Set())
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="destructive" className="my-4">
          <ListPlus className="mr-2" />
          {t("countries.importPredefined")}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t("countries.importPredefinedTitle")}</DialogTitle>
          <DialogDescription>
            {t("countries.importPredefinedDescription")}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative sm:max-w-sm sm:flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t("countries.searchPredefined")}
                className="pl-9"
              />
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={toggleAllAvailable}
                disabled={availableCountryKeys.length === 0}
              >
                {t(
                  allAvailableSelected
                    ? "countries.clearSelection"
                    : "countries.selectAll",
                )}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={clearSelection}
                disabled={selectedKeys.size === 0}
              >
                {t("countries.clearSelection")}
              </Button>
            </div>
          </div>

          <div className="rounded-md border">
            <div className="grid grid-cols-[2.5rem_1fr_5rem_6rem] gap-3 border-b bg-muted/40 px-4 py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <span />
              <span>{t("countries.countryName")}</span>
              <span>{t("countries.alpha2")}</span>
              <span>{t("countries.isoNumeric")}</span>
            </div>
            <div className="max-h-[420px] overflow-y-auto">
              {filteredCountries.map((country) => {
                const key = getCountryKey(country)
                const isAlreadyAdded =
                  existingAlpha2.has(country.alpha_2 ?? "") ||
                  existingIsoNumeric.has(country.iso_numeric ?? "")
                const checkboxId = `predefined-country-${key}`

                return (
                  <div
                    key={`${key}-${country.iso_numeric}`}
                    className={cn(
                      "grid grid-cols-[2.5rem_1fr_5rem_6rem] items-center gap-3 border-b px-4 py-2 last:border-b-0",
                      isAlreadyAdded && "bg-muted/30 text-muted-foreground",
                    )}
                  >
                    <Checkbox
                      id={checkboxId}
                      checked={selectedKeys.has(key)}
                      disabled={isAlreadyAdded || mutation.isPending}
                      onCheckedChange={(checked) =>
                        toggleCountry(country, checked === true)
                      }
                    />
                    <Label
                      htmlFor={checkboxId}
                      className={cn(
                        "cursor-pointer font-normal",
                        isAlreadyAdded && "cursor-not-allowed",
                      )}
                    >
                      {getCountryName(country)}
                      {isAlreadyAdded && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          {t("countries.alreadyAdded")}
                        </span>
                      )}
                    </Label>
                    <span className="font-mono text-sm">{country.alpha_2}</span>
                    <span className="font-mono text-sm">
                      {country.iso_numeric}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        <DialogFooter className="gap-2 sm:justify-between">
          <p className="text-sm text-muted-foreground">
            {t("countries.selectedCount", { count: selectedCountries.length })}
          </p>
          <LoadingButton
            type="button"
            loading={mutation.isPending}
            disabled={selectedCountries.length === 0}
            onClick={importSelected}
          >
            {t("countries.importSelected")}
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default ImportPredefinedCountries
