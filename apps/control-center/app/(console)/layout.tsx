import { ConsoleHeader } from "@/components/ConsoleHeader";
import { Sidebar } from "@/components/command-center/Sidebar";

export default function ConsoleLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="lg:flex">
      <Sidebar />
      <div className="min-w-0 flex-1">
        <ConsoleHeader />
        <main id="main" className="mx-auto w-full max-w-[110rem] px-4 py-6">
          {children}
        </main>
      </div>
    </div>
  );
}
