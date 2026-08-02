import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Pencil } from "lucide-react"
import { useMemo, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import {
  CountriesService,
  type CountryPublic,
  type CountryUpdate,
} from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { useI18n } from "@/i18n"
import { handleError } from "@/utils"

type FormData = {
  countryName: string
  alpha2: string
  isoNumeric: string
  customData: { key: string; value: string }[]
}

type CustomDataEntry = FormData["customData"][number]

interface EditItemProps {
  item: CountryPublic
  onSuccess: () => void
}

function formatCustomDataLabel(key: string): string {
  const spaced = key.replace(/_/g, " ").trim()
  if (!spaced) {
    return key
  }
  const lower = spaced.toLowerCase()
  return lower.charAt(0).toUpperCase() + lower.slice(1)
}

function stringifyCustomDataValue(value: unknown): string {
  if (value === null || value === undefined) {
    return ""
  }
  if (typeof value === "object") {
    return JSON.stringify(value)
  }
  return String(value)
}

function parseCustomDataValue(value: string, originalValue: unknown): unknown {
  if (typeof originalValue === "number") {
    const parsed = Number(value.replace(",", "."))
    return Number.isFinite(parsed) ? parsed : value
  }
  if (typeof originalValue === "boolean") {
    const normalized = value.trim().toLowerCase()
    if (normalized === "true") {
      return true
    }
    if (normalized === "false") {
      return false
    }
  }
  if (
    originalValue !== null &&
    typeof originalValue === "object" &&
    value.trim()
  ) {
    try {
      return JSON.parse(value)
    } catch {
      return value
    }
  }
  return value
}

function getCustomDataEntries(
  customData: Record<string, unknown> | undefined,
): CustomDataEntry[] {
  return Object.entries(customData ?? {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => ({
      key,
      value: stringifyCustomDataValue(value),
    }))
}

const EditItem = ({ item, onSuccess }: EditItemProps) => {
  const itemWithName = item as CountryPublic & {
    name?: string | null
    country_name?: string | null
  }
  const customData = item.custom_data ?? {}
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { t } = useI18n()
  const formSchema = useMemo(
    () =>
      z.object({
        countryName: z
          .string()
          .min(1, { message: t("validation.countryNameRequired") }),
        alpha2: z
          .string()
          .trim()
          .refine((v) => v === "" || /^[A-Za-z]{2}$/.test(v), {
            message: t("validation.alpha2"),
          }),
        isoNumeric: z
          .string()
          .trim()
          .refine((v) => v === "" || /^[0-9]{1,3}$/.test(v), {
            message: t("validation.isoNumeric"),
          }),
        customData: z.array(
          z.object({
            key: z.string(),
            value: z.string(),
          }),
        ),
      }),
    [t],
  )

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      countryName: itemWithName.name ?? itemWithName.country_name ?? "",
      alpha2: item.alpha_2 ?? "",
      isoNumeric: item.iso_numeric ?? "",
      customData: getCustomDataEntries(customData),
    },
  })

  const mutation = useMutation({
    mutationFn: (data: CountryUpdate) =>
      CountriesService.updateCountry({ id: item.id, requestBody: data }),
    onSuccess: () => {
      showSuccessToast(t("countries.countryUpdated"))
      setIsOpen(false)
      onSuccess()
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["countries"] })
    },
  })

  const onSubmit = (data: FormData) => {
    const nextCustomData = data.customData.reduce<Record<string, unknown>>(
      (acc, entry) => {
        acc[entry.key] = parseCustomDataValue(
          entry.value,
          customData[entry.key],
        )
        return acc
      },
      {},
    )
    const payload = {
      name: data.countryName,
      alpha_2: data.alpha2 ? data.alpha2.trim().toUpperCase() : null,
      iso_numeric: data.isoNumeric ? data.isoNumeric.padStart(3, "0") : null,
      custom_data: nextCustomData,
    }
    mutation.mutate(payload as CountryUpdate)
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        setIsOpen(open)
        if (open) {
          form.reset({
            countryName: itemWithName.name ?? itemWithName.country_name ?? "",
            alpha2: item.alpha_2 ?? "",
            isoNumeric: item.iso_numeric ?? "",
            customData: getCustomDataEntries(customData),
          })
        }
      }}
    >
      <DropdownMenuItem
        onSelect={(e) => e.preventDefault()}
        onClick={() => setIsOpen(true)}
      >
        <Pencil />
        {t("countries.editMenu")}
      </DropdownMenuItem>
      <DialogContent className="sm:max-w-md">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <DialogHeader>
              <DialogTitle>{t("countries.editTitle")}</DialogTitle>
              <DialogDescription>
                {t("countries.editDescription")}
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <FormField
                control={form.control}
                name="countryName"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      {t("countries.countryName")}{" "}
                      <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="Bolivia" type="text" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="alpha2"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("countries.alpha2")}</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="BO"
                        type="text"
                        maxLength={2}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="isoNumeric"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("countries.isoNumeric")}</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="068"
                        type="text"
                        inputMode="numeric"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {form.watch("customData").length > 0 && (
                <div className="grid gap-4">
                  <div>
                    <h4 className="text-sm font-medium">
                      {t("countries.customData")}
                    </h4>
                    <p className="text-xs text-muted-foreground">
                      {t("countries.customDataDescription")}
                    </p>
                  </div>
                  {form.watch("customData").map((entry, index) => (
                    <FormField
                      key={entry.key}
                      control={form.control}
                      name={`customData.${index}.value`}
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>
                            {formatCustomDataLabel(entry.key)}
                          </FormLabel>
                          <FormControl>
                            <Input type="text" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  ))}
                </div>
              )}
            </div>

            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" disabled={mutation.isPending}>
                  {t("actions.cancel")}
                </Button>
              </DialogClose>
              <LoadingButton type="submit" loading={mutation.isPending}>
                {t("actions.save")}
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

export default EditItem
