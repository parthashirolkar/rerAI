import { useState, useEffect } from "react";
import { useAuthActions } from "@convex-dev/auth/react";
import {
  ArrowRight,
  BookOpen,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock,
  FileCheck,
  FileText,
  LayoutDashboard,
  Loader2,
  MessageSquare,
  Search,
  Sparkles,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Google } from "@/components/icons/Google";

export function AuthScreen() {
  const { signIn } = useAuthActions();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

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

  const navLinks = [
    { label: "Product", href: "#product" },
    { label: "Agents", href: "#agents" },
    { label: "Capabilities", href: "#capabilities" },
    { label: "Use cases", href: "#use-cases" },
    { label: "Pricing", href: "#pricing" },
  ];

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-background">
      {/* Navigation */}
      <nav
        className={`fixed top-0 right-0 left-0 z-50 transition-all duration-300 ${
          scrolled
            ? "border-b bg-background/80 shadow-sm backdrop-blur-md"
            : "bg-transparent"
        }`}
      >
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <a href="/" className="font-serif text-2xl font-semibold tracking-tight text-foreground">
            rerAI
          </a>

          <div className="hidden items-center gap-8 md:flex">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {link.label}
              </a>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <a
              href="#docs"
              className="hidden text-sm text-muted-foreground transition-colors hover:text-foreground sm:inline"
            >
              Docs
            </a>
            <button
              onClick={() => void onSignIn()}
              disabled={busy}
              className="text-sm font-medium text-foreground transition-opacity hover:opacity-70 disabled:opacity-50"
            >
              {busy ? <Loader2 className="size-4 animate-spin" /> : "Sign in"}
            </button>
            <Button
              className="gap-2 rounded-lg bg-primary px-5 text-primary-foreground hover:bg-primary/90"
              disabled={busy}
              onClick={() => void onSignIn()}
            >
              {busy ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Google className="size-4 opacity-90" />
              )}
              Get started
            </Button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative px-6 pt-32 pb-20 lg:pt-40 lg:pb-28">
        <div className="mx-auto grid max-w-7xl items-center gap-12 lg:grid-cols-2 lg:gap-16">
          {/* Left Column */}
          <div className="relative max-w-xl space-y-8">
            
            {/* Blended Artwork Seamlessly Integrated into Background Layer */}
            <div className="relative h-56 w-full sm:h-64 lg:h-72 -mt-12 mb-4 group select-none">
                {/* Base texture: Blueprints floating seamlessly */}
                <div 
                  className="absolute -inset-16 opacity-40 mix-blend-multiply dark:opacity-60 dark:mix-blend-screen transition-transform duration-1000 ease-out group-hover:scale-105"
                  style={{
                    backgroundImage: 'url(/assets/blueprint_line_art.png)',
                    backgroundSize: 'cover',
                    backgroundPosition: 'center',
                    maskImage: 'radial-gradient(ellipse at center, black 20%, transparent 70%)',
                    WebkitMaskImage: 'radial-gradient(ellipse at center, black 20%, transparent 70%)'
                  }}
                />

                {/* Hero subject: 3D Isometric building */}
                <div 
                  className="absolute inset-y-0 -inset-x-8 opacity-[0.85] transition-transform duration-1000 ease-out group-hover:scale-105 group-hover:-translate-y-1"
                  style={{
                    backgroundImage: 'url(/assets/saas_3d_isometric.png)',
                    backgroundSize: 'contain',
                    backgroundRepeat: 'no-repeat',
                    backgroundPosition: 'center bottom',
                    maskImage: 'radial-gradient(circle at center, black 50%, transparent 90%)',
                    WebkitMaskImage: 'radial-gradient(circle at center, black 50%, transparent 90%)'
                  }}
                />

                {/* Ambient glow */}
                <div className="absolute top-1/2 left-1/2 -z-10 size-64 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 blur-[80px] transition-opacity duration-1000 group-hover:opacity-100 opacity-60" />
            </div>

            <div className="space-y-6 relative z-10">
              <h1 className="font-serif text-5xl leading-[1.1] font-semibold tracking-tight text-foreground lg:text-6xl">
                Permitting intelligence for Pune real estate
              </h1>
              <p className="text-lg leading-relaxed text-muted-foreground">
                Autonomous agents that read regulations, track filings, and surface next actions.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-4">
              <Button
                className="group h-12 gap-2 rounded-xl bg-primary px-6 text-base text-primary-foreground shadow-lg shadow-primary/20 transition-all hover:bg-primary/90 hover:shadow-xl hover:shadow-primary/25"
                disabled={busy}
                onClick={() => void onSignIn()}
              >
                {busy ? (
                  <Loader2 className="size-5 animate-spin" />
                ) : (
                  <>
                    Start review
                    <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
                  </>
                )}
              </Button>
              <Button
                variant="outline"
                className="h-12 gap-2 rounded-xl border-border px-6 text-base transition-all hover:bg-accent"
                disabled={busy}
                onClick={() => void onSignIn()}
              >
                View workflow
              </Button>
            </div>

            {error ? (
              <p className="text-sm text-destructive">{error}</p>
            ) : null}

            <div className="space-y-4 pt-4">
              <FeatureItem
                icon={<BookOpen className="size-5 text-primary" />}
                title="Regulation aware"
                description="RERA, PCMC, PDR, UDCP and more."
              />
              <FeatureItem
                icon={<Clock className="size-5 text-primary" />}
                title="Always up to date"
                description="Continuously ingests and monitors changes."
              />
              <FeatureItem
                icon={<CheckCircle2 className="size-5 text-primary" />}
                title="Action oriented"
                description="Clear next steps with timelines and forms."
              />
            </div>
          </div>

          {/* Right Column — Product Mockup */}
          <div className="relative lg:pl-4">
            <div className="relative rounded-2xl border border-border/60 bg-card shadow-2xl shadow-foreground/5">
              {/* Mockup Header */}
              <div className="flex items-center justify-between border-b px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <LayoutDashboard className="size-4 text-muted-foreground" />
                    <span className="text-xs font-medium">Chats</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Kumar Hill View</span>
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                    RERA filing
                  </span>
                  <ChevronDown className="size-3 text-muted-foreground" />
                </div>
              </div>

              <div className="grid grid-cols-[200px_1fr_220px] overflow-hidden rounded-b-2xl">
                {/* Sidebar */}
                <div className="border-r bg-muted/30 p-3">
                  <div className="mb-3 flex items-center gap-2 rounded-md bg-background px-2 py-1.5 text-xs text-muted-foreground">
                    <Search className="size-3" />
                    Search chats...
                  </div>
                  <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Today
                  </div>
                  <div className="space-y-1">
                    <div className="rounded-md bg-primary/5 p-2">
                      <div className="text-xs font-medium">Kumar Hill View</div>
                      <div className="mt-0.5 flex items-center gap-1 text-[10px] text-primary">
                        <span className="size-1.5 rounded-full bg-primary" />
                        RERA filing • Just now
                      </div>
                    </div>
                    <div className="rounded-md p-2 opacity-60">
                      <div className="text-xs font-medium">Sai Developers</div>
                      <div className="mt-0.5 text-[10px] text-muted-foreground">Building permit • 2h ago</div>
                    </div>
                    <div className="rounded-md p-2 opacity-60">
                      <div className="text-xs font-medium">Green Valley Phase 2</div>
                      <div className="mt-0.5 text-[10px] text-muted-foreground">Compliance check • 4h ago</div>
                    </div>
                  </div>
                  <div className="mb-2 mt-4 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Yesterday
                  </div>
                  <div className="space-y-1">
                    <div className="rounded-md p-2 opacity-60">
                      <div className="text-xs font-medium">Lotus Residency</div>
                      <div className="mt-0.5 text-[10px] text-muted-foreground">RERA filing • 1d ago</div>
                    </div>
                    <div className="rounded-md p-2 opacity-60">
                      <div className="text-xs font-medium">Maple Heights</div>
                      <div className="mt-0.5 text-[10px] text-muted-foreground">Building permit • 1d ago</div>
                    </div>
                  </div>
                </div>

                {/* Main Chat Area */}
                <div className="flex flex-col gap-3 p-4">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Bot className="size-3.5" />
                    <span className="font-medium text-foreground">Thinking</span>
                    <ChevronDown className="size-3" />
                    <span className="ml-auto">2m 34s</span>
                  </div>

                  <div className="rounded-lg border bg-muted/20 p-3 text-xs leading-relaxed text-muted-foreground">
                    <p className="mb-2 text-foreground">
                      I'll review the project details against MahaRERA requirements and applicable circulars.
                    </p>
                    <ul className="space-y-1">
                      {[
                        "Reading project summary",
                        "Checking RERA registration requirements",
                        "Verifying document checklist",
                        "Reviewing timeline and fees",
                        "Summarizing next actions",
                      ].map((item, i) => (
                        <li key={i} className="flex items-center gap-1.5">
                          <CheckCircle2 className="size-3 text-primary/70" />
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="flex items-start gap-2">
                    <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-bold text-primary">
                      PK
                    </div>
                    <div className="rounded-2xl rounded-tl-sm bg-primary px-3 py-2 text-xs text-primary-foreground">
                      What are the pending documents for registration?
                    </div>
                    <span className="mt-2 text-[10px] text-muted-foreground">10:42 AM</span>
                  </div>

                  <div className="flex items-start gap-2">
                    <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-bold">
                      AI
                    </div>
                    <div className="rounded-2xl rounded-tl-sm border bg-card px-3 py-2 text-xs leading-relaxed">
                      You're missing the land title search report and the architect certificate. I've listed the exact formats and links.
                      <div className="mt-1.5 flex items-center gap-2 text-[10px] text-muted-foreground">
                        <span>10:43 AM</span>
                        <Check className="size-3" />
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2 pt-2">
                    {["RERA filing", "Building permit", "Compliance check", "Timeline"].map((tag) => (
                      <span
                        key={tag}
                        className="rounded-md border px-2.5 py-1 text-[10px] text-muted-foreground"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>

                  <div className="mt-auto flex items-center gap-2 rounded-xl border bg-background px-3 py-2">
                    <span className="text-xs text-muted-foreground">
                      Ask anything about permits, regulations, or documents...
                    </span>
                    <div className="ml-auto flex items-center gap-1.5">
                      <div className="flex size-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
                        <ArrowRight className="size-3" />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right Panel */}
                <div className="border-l bg-muted/20 p-4">
                  <div className="mb-4 text-xs font-semibold">Report</div>
                  <div className="mb-4">
                    <div className="text-sm font-medium">Kumar Hill View</div>
                    <div className="text-[10px] text-muted-foreground">RERA registration review</div>
                  </div>

                  <div className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Project overview
                  </div>
                  <div className="mb-4 space-y-2">
                    {[
                      { label: "Location", value: "Baner, Pune" },
                      { label: "Developer", value: "Kumar Developers" },
                      { label: "Project type", value: "Residential" },
                      { label: "Land area", value: "2,450 sqm" },
                    ].map((item) => (
                      <div key={item.label} className="flex justify-between text-xs">
                        <span className="text-muted-foreground">{item.label}</span>
                        <span className="font-medium">{item.value}</span>
                      </div>
                    ))}
                  </div>

                  <div className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Compliance status
                  </div>
                  <div className="mb-4 space-y-2">
                    {[
                      { label: "RERA registration", status: "In progress", color: "bg-yellow-400" },
                      { label: "Land title", status: "Pending", color: "bg-red-400" },
                      { label: "Architect certificate", status: "Pending", color: "bg-red-400" },
                      { label: "CA certificate", status: "Complete", color: "bg-green-400" },
                      { label: "Layout approvals", status: "In progress", color: "bg-yellow-400" },
                    ].map((item) => (
                      <div key={item.label} className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">{item.label}</span>
                        <span className="flex items-center gap-1.5">
                          <span className={`size-1.5 rounded-full ${item.color}`} />
                          <span className="text-[10px]">{item.status}</span>
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className="rounded-lg border bg-background p-3">
                    <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Next action
                    </div>
                    <div className="flex items-start gap-2">
                      <Clock className="mt-0.5 size-3.5 text-primary" />
                      <div>
                        <div className="text-xs font-medium">Upload land title search report</div>
                        <div className="text-[10px] text-muted-foreground">Due in 3 days • 27 Apr 2025</div>
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 flex items-center justify-center gap-1 rounded-lg border py-2 text-[10px] text-muted-foreground">
                    View full report
                    <ArrowRight className="size-3" />
                  </div>
                </div>
              </div>
            </div>

            {/* Decorative blur behind mockup */}
            <div className="absolute -top-10 -right-10 -z-10 size-72 rounded-full bg-primary/5 blur-3xl" />
            <div className="absolute -bottom-10 -left-10 -z-10 size-72 rounded-full bg-ring/5 blur-3xl" />
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="border-t bg-secondary/30 px-6 py-20">
        <div className="mx-auto max-w-7xl">
          <h2 className="mb-16 text-center font-serif text-3xl font-semibold tracking-tight">
            How rerAI works
          </h2>

          <div className="grid gap-8 md:grid-cols-4">
            {[
              {
                icon: <MessageSquare className="size-6 text-primary" />,
                title: "Ask in natural language",
                description: "Share your project details or ask about any permit or regulation.",
              },
              {
                icon: <Sparkles className="size-6 text-primary" />,
                title: "Agents do the heavy lifting",
                description: "Our agents read regulations, check requirements, and verify documents.",
              },
              {
                icon: <FileText className="size-6 text-primary" />,
                title: "Get clear answers",
                description: "Receive a structured report with risks, timelines, and references.",
              },
              {
                icon: <CheckCircle2 className="size-6 text-primary" />,
                title: "Take the next step",
                description: "Download forms, track progress, and stay compliant.",
              },
            ].map((step, index) => (
              <div key={step.title} className="relative">
                <div className="rounded-2xl border bg-card p-6 shadow-sm transition-all hover:shadow-md">
                  <div className="mb-4 flex size-12 items-center justify-center rounded-xl bg-primary/5">
                    {step.icon}
                  </div>
                  <h3 className="mb-2 text-sm font-semibold">{step.title}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">{step.description}</p>
                </div>
                {index < 3 && (
                  <div className="absolute top-1/2 -right-4 hidden -translate-y-1/2 md:block">
                    <ArrowRight className="size-4 text-muted-foreground/30" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Audience Banner */}
      <section className="border-t px-6 py-12">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-8 md:flex-row">
          <div className="text-center md:text-left">
            <p className="font-serif text-xl font-semibold tracking-tight">
              Built for professionals who build Pune.
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-6 md:gap-10">
            {[
              { icon: <Users className="size-4" />, label: "Developers" },
              { icon: <LayoutDashboard className="size-4" />, label: "Architects" },
              { icon: <FileCheck className="size-4" />, label: "Consultants" },
              { icon: <BookOpen className="size-4" />, label: "Legal teams" },
              { icon: <CheckCircle2 className="size-4" />, label: "Compliance officers" },
            ].map((item) => (
              <div key={item.label} className="flex items-center gap-2 text-sm text-muted-foreground">
                {item.icon}
                <span>{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t px-6 py-8">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 md:flex-row">
          <p className="text-sm text-muted-foreground">
            © 2025 rerAI. Permitting intelligence for Maharashtra.
          </p>
          <div className="flex gap-6">
            {["Privacy", "Terms", "Contact"].map((link) => (
              <a
                key={link}
                href="#"
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {link}
              </a>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}

function FeatureItem({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex items-start gap-4">
      <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/5">
        {icon}
      </div>
      <div>
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}
