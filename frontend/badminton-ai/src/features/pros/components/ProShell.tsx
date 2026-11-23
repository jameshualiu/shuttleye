import type { ReactNode } from "react";
import { ProAttribution } from "./ProAttribution";

// Content frame only: these pages render inside PrivateLayout, which owns the Sidebar.
export function ProShell({
  children,
  source,
}: {
  children: ReactNode;
  source?: "singles" | "doubles" | "both";
}) {
  return (
    <div className="mx-auto w-full max-w-[1600px] px-4 py-8 min-[760px]:px-12">
      <main>{children}</main>
      <footer className="pt-10">
        {source === "both" ? (
          <div className="grid gap-3">
            <ProAttribution source="singles" />
            <ProAttribution source="doubles" />
          </div>
        ) : (
          <ProAttribution source={source} />
        )}
      </footer>
    </div>
  );
}
