"use client";

import { useEffect, useState } from "react";
import { CommandPalette } from "@/components/CommandPalette";

/** Mount once in the app shell so the quick-add shortcut works on every route. */
export function CommandPaletteHost() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const openPalette = () => setOpen(true);
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "k") return;
      // Don't hijack ⌘K when the user is already typing in a form
      // field — browsers and other apps use it for their own palette
      // and we should defer to them.
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      const isTyping =
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        target?.isContentEditable === true;
      if (isTyping && !event.altKey) return;
      event.preventDefault();
      setOpen((value) => !value);
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("dnload:quick-add", openPalette);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("dnload:quick-add", openPalette);
    };
  }, []);

  return (
    <>
      {/* The floating "Thêm nhanh" pill was removed from the header. The
          palette itself is still reachable with ⌘K / Ctrl+K and from the
          dashboard's own button. */}
      <CommandPalette open={open} onOpenChange={setOpen} />
    </>
  );
}
