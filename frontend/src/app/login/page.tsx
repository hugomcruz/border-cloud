import Image from "next/image";
import { LoginForm } from "@/components/LoginForm";

export default function LoginPage() {
  return (
    <main className="flex min-h-screen w-full">
      {/* Left panel — branding */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-[#0f1221] px-14 py-14 relative overflow-hidden">
        {/* Subtle background glow */}
        <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-blue-500/10 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -left-24 w-72 h-72 rounded-full bg-blue-500/5 blur-3xl pointer-events-none" />

        {/* Logo */}
        <div className="relative z-10">
          <Image
            src="/border-logo.svg"
            alt="Border Innovation"
            width={300}
            height={35}
            className="[filter:brightness(0)_invert(1)]"
          />
          <p className="mt-2 text-xs font-semibold tracking-widest uppercase text-blue-400">Cloud</p>
        </div>

        {/* Main content */}
        <div className="relative z-10">
          <div className="mb-6 h-1 w-10 bg-blue-500 rounded-full" />
          <h1 className="text-4xl font-bold leading-tight tracking-tight text-white">
            Intelligent solutions<br />for complex<br />IT environments.
          </h1>
          <p className="mt-6 text-sm text-white/50 leading-relaxed max-w-sm">
            Multi-cloud VM management. Archive, restore, and control your infrastructure from one place.
          </p>
        </div>

        {/* Footer attribution */}
        <p className="relative z-10 text-xs text-white/20 tracking-widest uppercase">
          border-innovation.com
        </p>
      </div>

      {/* Right panel — login form */}
      <div className="flex flex-1 flex-col items-center justify-center bg-background px-6">
        {/* Mobile brand */}
        <div className="flex lg:hidden flex-col items-center mb-8">
          <Image
            src="/border-logo.svg"
            alt="Border Innovation"
            width={180}
            height={21}
            className="[filter:brightness(0)_invert(1)]"
          />
          <p className="mt-1 text-[10px] font-bold tracking-widest uppercase text-blue-600">Cloud</p>
        </div>

        <LoginForm />
      </div>
    </main>
  );
}
