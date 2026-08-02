import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { useMemo, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { CountriesService, type CountryCreate } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
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
}

const AddItem = () => {
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
      }),
    [t],
  )

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      countryName: "",
      alpha2: "",
      isoNumeric: "",
    },
  })

  const mutation = useMutation({
    mutationFn: (data: CountryCreate) =>
      CountriesService.createCountry({ requestBody: data }),
    onSuccess: () => {
      showSuccessToast(t("countries.countryCreated"))
      form.reset()
      setIsOpen(false)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["countries"] })
    },
  })

  const onSubmit = (data: FormData) => {
    const payload = {
      name: data.countryName,
      ...(data.alpha2 ? { alpha_2: data.alpha2.trim().toUpperCase() } : {}),
      ...(data.isoNumeric
        ? { iso_numeric: data.isoNumeric.padStart(3, "0") }
        : {}),
    }

    mutation.mutate(payload as CountryCreate)
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button className="my-4">
          <Plus className="mr-2" />
          {t("actions.addCountry")}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("countries.addTitle")}</DialogTitle>
          <DialogDescription>{t("countries.addDescription")}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
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
                      <Input
                        placeholder="Bolivia"
                        type="text"
                        {...field}
                        required
                      />
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

export default AddItem
