import { Component, type ErrorInfo, type ReactNode } from "react";
import { WarningTriangle } from "iconoir-react";

import { Button } from "./ui";

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface it for the devtools console; the UI shows a friendly fallback.
    console.error("Renderer error boundary caught:", error, info);
  }

  private readonly reset = (): void => this.setState({ error: null });

  render(): ReactNode {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
        <span className="grid h-16 w-16 place-items-center rounded-full border-[3px] border-red-ring bg-red/10 text-red">
          <WarningTriangle className="h-8 w-8" strokeWidth={2.2} />
        </span>
        <div className="text-xl font-black">Something hiccuped</div>
        <p className="max-w-md break-words font-semibold text-ink-soft">{error.message}</p>
        <Button variant="blue" onClick={this.reset}>
          Try again
        </Button>
      </div>
    );
  }
}
