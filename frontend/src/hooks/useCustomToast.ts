import { toast } from "sonner"
import { useI18n } from "@/i18n"

const useCustomToast = () => {
  const { t } = useI18n()

  const showSuccessToast = (description: string) => {
    toast.success(t("common.success"), {
      description,
    })
  }

  const showErrorToast = (description: string) => {
    toast.error(t("errors.genericToast"), {
      description,
    })
  }

  return { showSuccessToast, showErrorToast }
}

export default useCustomToast
