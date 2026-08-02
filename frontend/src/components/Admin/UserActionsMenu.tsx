import { EllipsisVertical, Trash2 } from "lucide-react"
import { useState } from "react"

import type { UserPublic } from "@/client"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import useAuth from "@/hooks/useAuth"
import { useI18n } from "@/i18n"
import DeleteUser from "./DeleteUser"
import EditUser from "./EditUser"

interface UserActionsMenuProps {
  user: UserPublic
}

export const UserActionsMenu = ({ user }: UserActionsMenuProps) => {
  const [open, setOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const { user: currentUser } = useAuth()
  const { t } = useI18n()

  if (user.id === currentUser?.id) {
    return null
  }

  return (
    <>
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon">
            <EllipsisVertical />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <EditUser user={user} onSuccess={() => setOpen(false)} />
          <DropdownMenuItem
            variant="destructive"
            onSelect={() => {
              setOpen(false)
              setDeleteOpen(true)
            }}
          >
            <Trash2 />
            {t("admin.deleteMenu")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <DeleteUser
        id={user.id}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onSuccess={() => setOpen(false)}
      />
    </>
  )
}
