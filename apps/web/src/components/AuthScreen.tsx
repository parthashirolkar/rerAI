import { useState } from "react";
import { useAuthActions } from "@convex-dev/auth/react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Google } from "@/components/icons/Google";

export function AuthScreen() {
  const { signIn } = useAuthActions();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSignIn = async () => {
    try {
      setBusy(true);
      setError(null);
      await signIn("google");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_hsl(154_24%_95%),_transparent_42%),linear-gradient(180deg,_hsl(42_30%_97%),_hsl(38_18%_94%))] px-6">
      <div className="w-full max-w-md rounded-3xl border bg-background/90 p-8 shadow-[0_20px_60px_-24px_hsl(155_25%_25%/0.35)] backdrop-blur">
        <div className="space-y-3 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-ring">
            rerAI
          </p>
          <h1 className="font-serif text-3xl font-semibold tracking-tight">
            Sign in to continue
          </h1>
          <p className="text-sm text-muted-foreground">
            Authenticate with Google to access your conversation history and synced workspace state.
          </p>
        </div>

        <div className="mt-8 space-y-4">
          <Button className="w-full gap-2" disabled={busy} onClick={() => void onSignIn()}>
            {busy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Google className="size-4 opacity-90" />
            )}
            Continue with Google
          </Button>
          {error ? (
            <p className="text-center text-xs text-destructive">{error}</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
