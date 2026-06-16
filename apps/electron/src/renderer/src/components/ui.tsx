import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ComponentType,
  type ReactNode,
  type SVGProps,
} from "react";
import { CheckCircle, Sparks, WarningCircle, WarningTriangle } from "iconoir-react";

export type IconType = ComponentType<SVGProps<SVGSVGElement>>;

export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

type Accent = "blue" | "mint" | "grape" | "lemon" | "pink" | "red";

/* ------------------------------------------------------------------ Button */

type ButtonVariant = Accent | "ghost";

const BUTTON_COLORS: Record<ButtonVariant, string> = {
  blue: "bg-blue border-blue-ring text-white",
  mint: "bg-mint border-mint-ring text-white",
  grape: "bg-grape border-grape-ring text-white",
  lemon: "bg-lemon border-lemon-ring text-ink",
  pink: "bg-pink border-pink-ring text-white",
  red: "bg-red border-red-ring text-white",
  ghost: "bg-cloud border-ink/10 text-ink",
};

export function Button({
  children,
  icon: Icon,
  onClick,
  disabled,
  variant = "blue",
  className,
  title,
}: {
  children: ReactNode;
  icon?: IconType;
  onClick?: () => void;
  disabled?: boolean;
  variant?: ButtonVariant;
  className?: string;
  title?: string;
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "group inline-flex select-none items-center justify-center gap-2 rounded-full border-[5px] px-5 py-2.5 text-sm font-extrabold transition-all duration-200",
        "hover:-translate-y-0.5 active:translate-y-0 active:scale-95",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "focus:outline-none focus-visible:ring-4 focus-visible:ring-blue/40",
        BUTTON_COLORS[variant],
        className,
      )}
    >
      {Icon && <Icon className="h-[1.15rem] w-[1.15rem] group-hover:animate-jello" strokeWidth={2.2} />}
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------- Panel */

export function Panel({
  children,
  className,
  hover,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-blob border-[3px] border-ink/10 bg-cloud p-5 shadow-puff",
        hover && "transition-transform duration-200 hover:-translate-y-1",
        className,
      )}
    >
      {children}
    </div>
  );
}

/* -------------------------------------------------------------------- Tile */
/* Selection motif (corner dot pops in on hover, locks on select), soft skin. */

const TILE_BORDER: Record<Accent, string> = {
  blue: "border-blue-ring",
  mint: "border-mint-ring",
  grape: "border-grape-ring",
  lemon: "border-lemon-ring",
  pink: "border-pink-ring",
  red: "border-red-ring",
};
const TILE_TINT: Record<Accent, string> = {
  blue: "bg-blue/10",
  mint: "bg-mint/10",
  grape: "bg-grape/10",
  lemon: "bg-lemon/15",
  pink: "bg-pink/10",
  red: "bg-red/10",
};
const TILE_DOT: Record<Accent, string> = {
  blue: "bg-blue",
  mint: "bg-mint",
  grape: "bg-grape",
  lemon: "bg-lemon",
  pink: "bg-pink",
  red: "bg-red",
};

export function Tile({
  selected = false,
  onClick,
  accent = "blue",
  className,
  children,
  title,
}: {
  selected?: boolean;
  onClick?: () => void;
  accent?: Accent;
  className?: string;
  children: ReactNode;
  title?: string;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        "group relative rounded-chunk border-[3px] bg-cloud shadow-puff-sm transition-all duration-200",
        "hover:-translate-y-1 hover:shadow-puff active:scale-[0.98]",
        "focus:outline-none focus-visible:ring-4 focus-visible:ring-blue/40",
        selected ? cn(TILE_BORDER[accent], TILE_TINT[accent]) : "border-ink/10",
        className,
      )}
    >
      <span
        className={cn(
          "pointer-events-none absolute left-3 top-3 h-3.5 w-3.5 rounded-full transition-all duration-200",
          selected
            ? cn("scale-100 opacity-100", TILE_DOT[accent])
            : "scale-0 bg-ink/20 opacity-0 group-hover:scale-100 group-hover:opacity-100",
        )}
      />
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------- Badge */

type BadgeTone = "neutral" | "mint" | "lemon" | "blue" | "grape" | "pink" | "red";

const BADGE_COLORS: Record<BadgeTone, string> = {
  neutral: "bg-ink/8 border-ink/15 text-ink",
  mint: "bg-mint/15 border-mint-ring text-ink",
  lemon: "bg-lemon/20 border-lemon-ring text-ink",
  blue: "bg-blue/12 border-blue-ring text-ink",
  grape: "bg-grape/14 border-grape-ring text-ink",
  pink: "bg-pink/14 border-pink-ring text-ink",
  red: "bg-red/14 border-red-ring text-ink",
};

export function Badge({
  children,
  tone = "neutral",
  icon: Icon,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  icon?: IconType;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border-2 px-2.5 py-0.5 text-xs font-bold",
        BADGE_COLORS[tone],
      )}
    >
      {Icon && <Icon className="h-3.5 w-3.5" strokeWidth={2.2} />}
      {children}
    </span>
  );
}

/* ----------------------------------------------------------------- Spinner */

export function Spinner({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-end gap-1", className)} role="status" aria-label="loading">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-2.5 w-2.5 rounded-full bg-blue animate-bounce-soft"
          style={{ animationDelay: `${i * 0.12}s` }}
        />
      ))}
    </span>
  );
}

/* --------------------------------------------------------------------- Row */

export function Row({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-ink/8 pb-1.5 last:border-none last:pb-0">
      <span className="font-semibold text-ink-soft">{label}</span>
      <span className="truncate font-bold text-ink">{value ?? "—"}</span>
    </div>
  );
}

/* --------------------------------------------------------- Toast + Confirm */

type ToastKind = "info" | "success" | "error";
interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
}
interface ConfirmOptions {
  title: string;
  body?: string;
  confirmLabel?: string;
  danger?: boolean;
  preview?: ReactNode;
}

interface UiContextValue {
  notify: (kind: ToastKind, text: string) => void;
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

const TOAST_ICON: Record<ToastKind, IconType> = {
  info: Sparks,
  success: CheckCircle,
  error: WarningCircle,
};
const TOAST_ICON_COLOR: Record<ToastKind, string> = {
  info: "text-blue",
  success: "text-mint",
  error: "text-red",
};

const UiContext = createContext<UiContextValue | null>(null);

export function useUi(): UiContextValue {
  const ctx = useContext(UiContext);
  if (!ctx) {
    throw new Error("useUi must be used within a UiProvider");
  }
  return ctx;
}

export function UiProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [confirmState, setConfirmState] = useState<
    { options: ConfirmOptions; resolve: (value: boolean) => void } | null
  >(null);

  const notify = useCallback((kind: ToastKind, text: string) => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, kind, text }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, 4500);
  }, []);

  const confirm = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => {
        setConfirmState({ options, resolve });
      }),
    [],
  );

  const closeConfirm = useCallback((value: boolean) => {
    setConfirmState((prev) => {
      prev?.resolve(value);
      return null;
    });
  }, []);

  useEffect(() => {
    if (!confirmState) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      closeConfirm(false);
    }
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [closeConfirm, confirmState]);

  const value = useMemo(() => ({ notify, confirm }), [notify, confirm]);

  return (
    <UiContext.Provider value={value}>
      {children}

      <div className="pointer-events-none fixed bottom-5 right-5 z-50 flex flex-col gap-2.5">
        {toasts.map((toast) => {
          const Icon = TOAST_ICON[toast.kind];
          return (
            <div
              key={toast.id}
              className="pointer-events-auto flex max-w-sm items-center gap-2 rounded-full border-[3px] border-ink/10 bg-cloud px-4 py-2.5 text-sm font-bold text-ink shadow-puff animate-slide-up"
            >
              <Icon className={cn("h-5 w-5 shrink-0", TOAST_ICON_COLOR[toast.kind])} strokeWidth={2.2} />
              {toast.text}
            </div>
          );
        })}
      </div>

      {confirmState && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-blob border-[3px] border-ink/10 bg-cloud p-6 shadow-puff animate-pop-in">
            <span
              className={cn(
                "mb-3 inline-grid h-14 w-14 place-items-center rounded-full border-[3px]",
                confirmState.options.danger ? "border-red-ring bg-red/10 text-red" : "border-grape-ring bg-grape/10 text-grape",
              )}
            >
              {confirmState.options.danger ? (
                <WarningTriangle className="h-7 w-7" strokeWidth={2.2} />
              ) : (
                <Sparks className="h-7 w-7" strokeWidth={2.2} />
              )}
            </span>
            <h2 className="text-xl font-black text-ink">{confirmState.options.title}</h2>
            {confirmState.options.body && (
              <p className="mt-2 font-semibold leading-snug text-ink-soft">{confirmState.options.body}</p>
            )}
            {confirmState.options.preview && <div className="mt-3">{confirmState.options.preview}</div>}
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="ghost" onClick={() => closeConfirm(false)}>
                Nope
              </Button>
              <Button
                variant={confirmState.options.danger ? "red" : "blue"}
                onClick={() => closeConfirm(true)}
              >
                {confirmState.options.confirmLabel ?? "Do it!"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </UiContext.Provider>
  );
}
