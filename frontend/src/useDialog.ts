import { useEffect, useRef } from "react";

/** Keep keyboard focus within the active dialog and restore it on close. */
export function useDialog(open: boolean, onClose: () => void) {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const frame = requestAnimationFrame(() => {
      const dialog = [
        ...document.querySelectorAll<HTMLElement>('[role="dialog"]'),
      ].at(-1);
      if (!dialog?.contains(document.activeElement)) {
        dialog
          ?.querySelector<HTMLElement>(
            "button:not(:disabled), input, textarea, select",
          )
          ?.focus();
      }
    });
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close.current();
        return;
      }
      if (event.key !== "Tab") return;
      const dialog = [
        ...document.querySelectorAll<HTMLElement>('[role="dialog"]'),
      ].at(-1);
      const items = [
        ...(dialog?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled):not([type="hidden"]), textarea, select, a[href]',
        ) || []),
      ].filter((item) => item.getClientRects().length);
      const first = items[0],
        last = items.at(-1);
      if (!first || !last) return;
      if (
        event.shiftKey &&
        (document.activeElement === first ||
          !dialog?.contains(document.activeElement))
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last ||
          !dialog?.contains(document.activeElement))
      ) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("keydown", keydown);
      previous?.focus();
    };
  }, [open]);
}
