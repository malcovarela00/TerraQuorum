import { Appearance } from "@/components/Common/Appearance"
import { LanguageSwitcher } from "@/components/Common/LanguageSwitcher"
import { LoginNeuralBackground } from "@/components/Common/LoginNeuralBackground"
import { Logo } from "@/components/Common/Logo"
import { Footer } from "./Footer"

interface AuthLayoutProps {
  children: React.ReactNode
  showNeuralBackground?: boolean
}

export function AuthLayout({
  children,
  showNeuralBackground = false,
}: AuthLayoutProps) {
  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      <div className="bg-muted dark:bg-zinc-900 relative hidden overflow-hidden lg:flex lg:items-center lg:justify-center">
        {showNeuralBackground ? (
          <>
            <LoginNeuralBackground />
            <div className="relative z-10 rounded-2xl border border-white/15 bg-black/20 px-6 py-4 shadow-2xl shadow-black/40 backdrop-blur-md">
              <Logo variant="full" className="h-16 text-white" asLink={false} />
            </div>
          </>
        ) : (
          <Logo variant="full" className="h-16" asLink={false} />
        )}
      </div>
      <div className="app-ambient flex flex-col gap-4 p-6 md:p-10">
        <div className="flex justify-end gap-2">
          <LanguageSwitcher />
          <Appearance />
        </div>
        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-sm rounded-2xl border border-border/70 bg-card/80 p-6 shadow-lg shadow-black/[0.06] backdrop-blur-sm sm:p-8 dark:bg-card/60 dark:shadow-black/30">
            {children}
          </div>
        </div>
        <Footer />
      </div>
    </div>
  )
}
