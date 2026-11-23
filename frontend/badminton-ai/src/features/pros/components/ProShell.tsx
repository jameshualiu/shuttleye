import type { ReactNode } from "react";
import { ProAttribution } from "./ProAttribution";

// Content frame only: these pages render inside PrivateLayout, which owns the Navbar.
export function ProShell({
  children,
  source,
}: {
  children: ReactNode;
  source?: "singles" | "doubles";
}) {
  return (
    <div className="mx-auto w-full max-w-[1600px] px-4 py-8 min-[760px]:px-12">
      <main>{children}</main>
      <footer className="pt-10">
        <ProAttribution source={source} />
      </footer>
    </div>
  );
}
