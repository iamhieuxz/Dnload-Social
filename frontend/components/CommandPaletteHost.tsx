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
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Thêm nhanh (Ctrl hoặc Command + K)"
        className="fixed top-5 right-5 z-30 inline-flex h-11 items-center gap-2 rounded-full bg-accent px-4 text-sm font-medium text-background shadow-float transition-transform hover:scale-[1.02] active:scale-[0.98]"
      >
        <span aria-hidden="true">+</span>
        Thêm nhanh
        <kbd className="rounded border border-black/15 bg-black/10 px-1.5 py-0.5 font-mono text-[10px]">⌘K</kbd>
      </button>
      <CommandPalette open={open} onOpenChange={setOpen} />
    </>
  );
}
