import Image from "next/image";
import { LoginForm } from "@/components/LoginForm";

export default function LoginPage() {
  const logoSrc = process.env.LOGO_URL ?? "/border-logo.svg";
  const isLight = process.env.THEME === "light";

  return (
    <main className="flex min-h-screen w-full">
      {/* Left panel — branding */}
      <div className={`hidden lg:flex lg:w-1/2 flex-col justify-between ${isLight ? "bg-card" : "bg-[#0f1221]"} px-14 py-14 relative overflow-hidden`}>
        {/* Subtle background glow */}
        <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-blue-500/10 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -left-24 w-72 h-72 rounded-full bg-blue-500/5 blur-3xl pointer-events-none" />

        {/* Logo */}
        <div className="relative z-10">
          <Image
            src={logoSrc}
            unoptimized
            alt="Border Innovation"
            width={300}
            height={35}
            className={isLight ? "[filter:brightness(0)]" : "[filter:brightness(0)_invert(1)]"}
          />
          <p className={`mt-2 text-xs font-semibold tracking-widest uppercase ${isLight ? "text-blue-600" : "text-blue-400"}`}>Cloud</p>
        </div>

        {/* Main content */}
        <div className="relative z-10">
          <div className="mb-6 h-1 w-10 bg-blue-500 rounded-full" />
          <h1 className={`text-4xl font-bold leading-tight tracking-tight ${isLight ? "text-foreground" : "text-white"}`}>
            Intelligent solutions<br />for complex<br />IT environments.
          </h1>
          <p className={`mt-6 text-sm leading-relaxed max-w-sm ${isLight ? "text-foreground/60" : "text-white/50"}`}>
            Multi-cloud VM management. Archive, restore, and control your infrastructure from one place.
          </p>
        </div>


      </div>

      {/* Right panel — login form */}
      <div className="flex flex-1 flex-col items-center justify-center bg-background px-6">
        {/* Mobile brand */}
        <div className="flex lg:hidden flex-col items-center mb-8">
          <Image
            src={logoSrc}
            unoptimized
            alt="Border Innovation"
            width={180}
            height={21}
            className={isLight ? "" : "[filter:brightness(0)_invert(1)]"}
          />
          <p className="mt-1 text-[10px] font-bold tracking-widest uppercase text-blue-600">Cloud</p>
        </div>

        <LoginForm />
      </div>
    </main>
  );
}
