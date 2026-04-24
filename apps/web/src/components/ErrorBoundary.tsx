import { Component, type ReactNode } from "react";
import { AlertTriangle, MessageSquarePlus } from "lucide-react";

import { Button } from "@/components/ui/button";

type ErrorBoundaryProps = {
  children: ReactNode;
  onReset?: () => void;
};

type ErrorBoundaryState = {
  hasError: boolean;
  error: Error | null;
};

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("AuthenticatedApp error:", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-background px-6">
          <div className="w-full max-w-md space-y-4 rounded-2xl border bg-card p-6 shadow-sm">
            <div className="flex items-start gap-3">
              <div className="rounded-full bg-destructive/10 p-2 text-destructive">
                <AlertTriangle className="size-5" />
              </div>
              <div>
                <h2 className="text-sm font-semibold">Something went wrong</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  The app encountered an unexpected error. You can start a new chat to recover.
                </p>
              </div>
            </div>
            {this.state.error ? (
              <div className="rounded-md bg-muted p-3">
                <p className="font-mono text-[11px] text-muted-foreground">
                  {this.state.error.message}
                </p>
              </div>
            ) : null}
            <Button onClick={this.handleReset} className="w-full gap-2">
              <MessageSquarePlus className="size-4" />
              Start blank chat
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
