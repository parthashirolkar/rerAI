import { useEffect, useMemo, useState } from "react"
import { AlertTriangle, Check, FileWarning, MessageSquarePlus, PencilLine, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Textarea } from "@/components/ui/textarea"

type InterruptLike = {
  id?: string
  value?: unknown
  when?: string
}

type ReviewDecision = "approve" | "reject" | "edit"

type HitlActionRequest = {
  action?: string
  name?: string
  args?: Record<string, unknown>
  description?: string
}

type HitlReviewConfig = {
  allowedDecisions?: ReviewDecision[]
}

type HitlRequest = {
  actionRequests?: HitlActionRequest[]
  reviewConfigs?: HitlReviewConfig[]
}

type ActionDraft = {
  mode: ReviewDecision
  rejectReason: string
  editText: string
}

type GenericDraft = {
  responseText: string
}

type MiddlewareDecision =
  | { type: "approve" }
  | { type: "reject"; message?: string }
  | { type: "edit"; edited_action: { name: string; args: Record<string, unknown> } }

type InterruptDialogProps = {
  interrupts: InterruptLike[]
  busy: boolean
  onResume: (resumeValue: unknown) => Promise<void>
  onDismiss?: () => void
}

import { isHitlRequest, isRecord } from "./interruptHelpers"

function prettyJson(value: unknown) {
  return JSON.stringify(value, null, 2)
}

function getInterruptKey(interrupt: InterruptLike, index: number) {
  return interrupt.id ?? `${interrupt.when ?? "interrupt"}-${index}`
}

export function InterruptDialog({
  interrupts,
  busy,
  onResume,
  onDismiss,
}: InterruptDialogProps) {
  const open = interrupts.length > 0
  const [actionDrafts, setActionDrafts] = useState<Record<string, ActionDraft[]>>({})
  const [genericDrafts, setGenericDrafts] = useState<Record<string, GenericDraft>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)

  const signature = useMemo(
    () => interrupts.map((interrupt, index) => getInterruptKey(interrupt, index)).join("|"),
    [interrupts]
  )

  useEffect(() => {
    if (!open) {
      setActionDrafts({})
      setGenericDrafts({})
      setSubmitError(null)
      return
    }

    const nextActionDrafts: Record<string, ActionDraft[]> = {}
    const nextGenericDrafts: Record<string, GenericDraft> = {}

    interrupts.forEach((interrupt, index) => {
      const key = getInterruptKey(interrupt, index)
      if (isHitlRequest(interrupt.value)) {
        nextActionDrafts[key] =
          interrupt.value.actionRequests?.map((request) => ({
            mode: "approve",
            rejectReason: "",
            editText: prettyJson(request.args ?? {}),
          })) ?? []
      } else {
        nextGenericDrafts[key] = {
          responseText: interrupt.value === undefined ? "true" : "true",
        }
      }
    })

    setActionDrafts(nextActionDrafts)
    setGenericDrafts(nextGenericDrafts)
    setSubmitError(null)
  }, [interrupts, open, signature])

  const buildResumeValue = () => {
    const responses = interrupts.map((interrupt, interruptIndex) => {
      const interruptKey = getInterruptKey(interrupt, interruptIndex)

      if (isHitlRequest(interrupt.value)) {
        const actions = interrupt.value.actionRequests ?? []
        const drafts = actionDrafts[interruptKey] ?? []
        const decisions: MiddlewareDecision[] = actions.map((action, actionIndex) => {
          const draft = drafts[actionIndex]
          if (!draft || draft.mode === "approve") {
            return { type: "approve" }
          }

          if (draft.mode === "reject") {
            return {
              type: "reject",
              message: draft.rejectReason.trim() || undefined,
            }
          }

          return {
            type: "edit",
            edited_action: {
              name: action.name ?? action.action ?? "",
              args: JSON.parse(draft.editText) as Record<string, unknown>,
            },
          }
        })

        return { decisions }
      }

      const genericDraft = genericDrafts[interruptKey]
      return genericDraft ? JSON.parse(genericDraft.responseText) : true
    })

    return responses.length === 1
      ? responses[0]
      : Object.fromEntries(
          responses.map((response, index) => [
            interrupts[index]?.id ?? `interrupt-${index}`,
            response,
          ])
        )
  }

  const onSubmit = async () => {
    try {
      setSubmitError(null)
      await onResume(buildResumeValue())
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : String(error))
    }
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onDismiss?.() }}>
      <DialogContent
        showCloseButton={true}
        className="max-h-[90vh] p-0"
      >
        <DialogHeader className="border-b px-6 pt-6 pb-4">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-full bg-amber-100 p-2 text-amber-700">
              <AlertTriangle className="size-4" />
            </div>
            <div className="space-y-1">
              <DialogTitle>Review required before continuing</DialogTitle>
              <DialogDescription>
                The agent paused execution and is waiting for a human decision before it can continue.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <ScrollArea className="max-h-[60vh] px-6 py-5">
          <div className="space-y-5">
            {interrupts.map((interrupt, interruptIndex) => {
              const key = getInterruptKey(interrupt, interruptIndex)
              return isHitlRequest(interrupt.value) ? (
                <HitlInterruptSection
                  key={key}
                  drafts={actionDrafts[key] ?? []}
                  interrupt={interrupt}
                  onImmediateApprove={() => {
                    if (interrupts.length !== 1) {
                      return
                    }
                    void onResume({ decisions: [{ type: "approve" }] }).catch((error) => {
                      setSubmitError(error instanceof Error ? error.message : String(error))
                    })
                  }}
                  onDraftChange={(actionIndex, nextDraft) => {
                    setActionDrafts((prev) => {
                      const current = [...(prev[key] ?? [])]
                      current[actionIndex] = nextDraft
                      return { ...prev, [key]: current }
                    })
                  }}
                />
              ) : (
                <GenericInterruptSection
                  key={key}
                  draft={genericDrafts[key]}
                  interrupt={interrupt}
                  onDraftChange={(nextDraft) => {
                    setGenericDrafts((prev) => ({
                      ...prev,
                      [key]: nextDraft,
                    }))
                  }}
                />
              )
            })}
          </div>
        </ScrollArea>

        <DialogFooter className="border-t px-6 py-4 gap-2">
          {submitError ? (
            <p className="mr-auto text-sm text-destructive">{submitError}</p>
          ) : (
            <p className="mr-auto text-xs text-muted-foreground">
              Approve can resume immediately for a single action. Use the footer button after edit or multi-action review.
            </p>
          )}
          {onDismiss ? (
            <Button variant="outline" onClick={onDismiss} disabled={busy} className="gap-1.5">
              <MessageSquarePlus className="size-3.5" />
              Start blank chat
            </Button>
          ) : null}
          <Button onClick={() => void onSubmit()} disabled={busy}>
            {busy ? "Resuming..." : "Submit decisions"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function HitlInterruptSection({
  drafts,
  interrupt,
  onImmediateApprove,
  onDraftChange,
}: {
  drafts: ActionDraft[]
  interrupt: InterruptLike
  onImmediateApprove: () => void
  onDraftChange: (actionIndex: number, nextDraft: ActionDraft) => void
}) {
  const request = isHitlRequest(interrupt.value) ? interrupt.value : {}
  const actions = Array.isArray(request.actionRequests) ? request.actionRequests : []
  const reviewConfigs = Array.isArray(request.reviewConfigs) ? request.reviewConfigs : []

  return (
    <section className="space-y-4 rounded-xl border bg-card p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold">Human-in-the-loop action review</h4>
          <p className="mt-1 text-xs text-muted-foreground">
            {actions.length} pending action{actions.length === 1 ? "" : "s"}
          </p>
        </div>
        {interrupt.id ? (
          <span className="rounded-md bg-muted px-2 py-1 font-mono text-[10px] text-muted-foreground">
            {interrupt.id}
          </span>
        ) : null}
      </div>

      <div className="space-y-4">
        {actions.map((action, actionIndex) => {
          const config = reviewConfigs[actionIndex] ?? reviewConfigs[0] ?? {}
          const allowed = config.allowedDecisions ?? ["approve"]
          const draft = drafts[actionIndex] ?? {
            mode: "approve",
            rejectReason: "",
            editText: prettyJson(action.args ?? {}),
          }

          return (
            <div key={`${action.name ?? action.action ?? "action"}-${actionIndex}`} className="rounded-lg border p-4">
              <div>
                <p className="text-sm font-medium">
                  {action.description ?? action.action ?? action.name ?? `Action ${actionIndex + 1}`}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Tool: {action.action ?? action.name ?? "unknown"}
                </p>
              </div>

              <div className="mt-3 rounded-md bg-muted p-3">
                <pre className="overflow-x-auto text-xs">{prettyJson(action.args ?? {})}</pre>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {allowed.includes("approve") ? (
                  <Button
                    size="sm"
                    variant={draft.mode === "approve" ? "default" : "outline"}
                    onClick={() => {
                      onDraftChange(actionIndex, { ...draft, mode: "approve" })
                      if (actions.length === 1) {
                        onImmediateApprove()
                      }
                    }}
                  >
                    <Check className="size-3.5" />
                    Approve
                  </Button>
                ) : null}
                {allowed.includes("reject") ? (
                  <Button
                    size="sm"
                    variant={draft.mode === "reject" ? "destructive" : "outline"}
                    onClick={() => onDraftChange(actionIndex, { ...draft, mode: "reject" })}
                  >
                    <X className="size-3.5" />
                    Reject
                  </Button>
                ) : null}
                {allowed.includes("edit") ? (
                  <Button
                    size="sm"
                    variant={draft.mode === "edit" ? "secondary" : "outline"}
                    onClick={() => onDraftChange(actionIndex, { ...draft, mode: "edit" })}
                  >
                    <PencilLine className="size-3.5" />
                    Edit
                  </Button>
                ) : null}
              </div>

              {draft.mode === "reject" ? (
                <div className="mt-4 space-y-2">
                  <label className="text-xs font-medium">Rejection reason</label>
                  <Textarea
                    value={draft.rejectReason}
                    onChange={(event) =>
                      onDraftChange(actionIndex, {
                        ...draft,
                        rejectReason: event.target.value,
                      })
                    }
                    placeholder="Explain why this action should not proceed."
                  />
                </div>
              ) : null}

              {draft.mode === "edit" ? (
                <div className="mt-4 space-y-2">
                  <label className="text-xs font-medium">Edited arguments as JSON</label>
                  <Textarea
                    className="min-h-40 font-mono text-xs"
                    value={draft.editText}
                    onChange={(event) =>
                      onDraftChange(actionIndex, {
                        ...draft,
                        editText: event.target.value,
                      })
                    }
                  />
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function GenericInterruptSection({
  draft,
  interrupt,
  onDraftChange,
}: {
  draft?: GenericDraft
  interrupt: InterruptLike
  onDraftChange: (nextDraft: GenericDraft) => void
}) {
  const payload = interrupt.value
  const responseText = draft?.responseText ?? "true"

  return (
    <section className="space-y-4 rounded-xl border bg-card p-4">
      <div className="flex items-start gap-3">
        <div className="rounded-full bg-muted p-2 text-muted-foreground">
          <FileWarning className="size-4" />
        </div>
        <div className="space-y-1">
          <h4 className="text-sm font-semibold">Generic interrupt</h4>
          <p className="text-xs text-muted-foreground">
            This pause did not match the higher-level HITL review shape, so the UI is exposing the raw payload
            and a custom JSON resume value.
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-medium">Interrupt payload</p>
        <div className="rounded-md bg-muted p-3">
          <pre className="overflow-x-auto text-xs">
            {prettyJson(payload ?? { when: interrupt.when ?? "breakpoint" })}
          </pre>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-xs font-medium" htmlFor={`resume-${interrupt.id ?? "generic"}`}>
          Resume value as JSON
        </label>
        {payload === undefined ? (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => onDraftChange({ responseText: "true" })}>
              Approve / continue
            </Button>
            <Button size="sm" variant="outline" onClick={() => onDraftChange({ responseText: "false" })}>
              Reject / stop
            </Button>
          </div>
        ) : null}
        <Input
          id={`resume-${interrupt.id ?? "generic"}`}
          value={responseText}
          onChange={(event) => onDraftChange({ responseText: event.target.value })}
        />
      </div>
    </section>
  )
}
