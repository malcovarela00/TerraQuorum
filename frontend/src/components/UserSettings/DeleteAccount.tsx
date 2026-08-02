import { useI18n } from "@/i18n"
import DeleteConfirmation from "./DeleteConfirmation"

const DeleteAccount = () => {
  const { t } = useI18n()

  return (
    <div className="max-w-md rounded-2xl border border-destructive/40 bg-destructive/5 p-6 shadow-sm">
      <h3 className="font-semibold text-destructive">
        {t("settings.deleteAccount")}
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">
        {t("settings.deleteAccountDescription")}
      </p>
      <DeleteConfirmation />
    </div>
  )
}

export default DeleteAccount
