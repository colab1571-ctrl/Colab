"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Card, CardContent, Input, useAuth } from "@colab/ui";
import { api, ApiError } from "../../lib/api";

type Step = "display" | "vocation" | "bio" | "location" | "review";

const STEPS: { id: Step; label: string }[] = [
  { id: "display", label: "Name" },
  { id: "vocation", label: "Vocation" },
  { id: "bio", label: "Bio" },
  { id: "location", label: "Location" },
  { id: "review", label: "Review" },
];

const VOCATIONS = [
  "Visual arts",
  "Music",
  "Design",
  "Film & video",
  "Writing & content",
  "Dance & performance",
  "Digital art",
  "Craft & textile",
  "Other",
] as const;

interface ProfileDraft {
  display_name: string;
  vocations: string[];
  bio: string;
  location_label: string;
  open_to_remote: boolean;
}

export default function OnboardingPage(): React.ReactElement {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [step, setStep] = useState<Step>("display");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<ProfileDraft>({
    display_name: "",
    vocations: [],
    bio: "",
    location_label: "",
    open_to_remote: true,
  });

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <main className="container mx-auto max-w-2xl px-4 py-12 text-center">
        <p className="text-[var(--color-muted-foreground)]">Loading…</p>
      </main>
    );
  }

  const stepIndex = STEPS.findIndex((s) => s.id === step);
  const canAdvance =
    step === "display" ? draft.display_name.length >= 2 :
    step === "vocation" ? draft.vocations.length >= 1 :
    step === "bio" ? true :
    step === "location" ? draft.location_label.length >= 2 || draft.open_to_remote :
    true;

  const next = () => {
    setError(null);
    const i = STEPS.findIndex((s) => s.id === step);
    const nextStep = STEPS[i + 1];
    if (nextStep) setStep(nextStep.id);
  };
  const back = () => {
    setError(null);
    const i = STEPS.findIndex((s) => s.id === step);
    const prevStep = STEPS[i - 1];
    if (prevStep) setStep(prevStep.id);
  };

  const submit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await api.patch("/v1/profile/me", {
        display_name: draft.display_name,
        vocations: draft.vocations,
        bio: draft.bio || null,
        location_label: draft.location_label || null,
        open_to_remote: draft.open_to_remote,
      });
      router.push("/discover");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to save your profile");
      setSubmitting(false);
    }
  };

  return (
    <main className="container mx-auto max-w-2xl px-4 py-12">
      <ol
        className="mb-8 flex items-center gap-2"
        aria-label={`Step ${stepIndex + 1} of ${STEPS.length}`}
      >
        {STEPS.map((s, i) => (
          <li key={s.id} className="flex items-center gap-2 text-xs">
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
                i <= stepIndex
                  ? "bg-[var(--color-brand-primary)] text-[var(--color-primary-foreground)]"
                  : "bg-[var(--color-muted)] text-[var(--color-muted-foreground)]"
              }`}
            >
              {i + 1}
            </span>
            <span
              className={`hidden sm:inline ${
                i === stepIndex
                  ? "font-medium text-[var(--color-foreground)]"
                  : "text-[var(--color-muted-foreground)]"
              }`}
            >
              {s.label}
            </span>
            {i < STEPS.length - 1 && (
              <span className="hidden sm:inline text-[var(--color-muted-foreground)]" aria-hidden="true">
                ›
              </span>
            )}
          </li>
        ))}
      </ol>

      <Card>
        <CardContent className="space-y-6 p-6">
          {step === "display" && (
            <div>
              <label htmlFor="display_name" className="block text-sm font-medium">
                What should other creators call you?
              </label>
              <Input
                id="display_name"
                type="text"
                className="mt-2"
                placeholder="e.g. Maya R."
                autoFocus
                value={draft.display_name}
                onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
                maxLength={48}
              />
              <p className="mt-1 text-xs text-[var(--color-muted-foreground)]">
                You can change this any time in Settings.
              </p>
            </div>
          )}

          {step === "vocation" && (
            <div>
              <p className="text-sm font-medium">Pick your primary creative vocations.</p>
              <p className="mt-1 text-xs text-[var(--color-muted-foreground)]">
                Pick 1–3. This helps us match you with complementary collaborators.
              </p>
              <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3" role="list">
                {VOCATIONS.map((v) => {
                  const selected = draft.vocations.includes(v);
                  return (
                    <li key={v}>
                      <button
                        type="button"
                        onClick={() =>
                          setDraft({
                            ...draft,
                            vocations: selected
                              ? draft.vocations.filter((x) => x !== v)
                              : draft.vocations.length < 3
                                ? [...draft.vocations, v]
                                : draft.vocations,
                          })
                        }
                        aria-pressed={selected}
                        className={`w-full rounded-md border px-3 py-2 text-sm transition-colors ${
                          selected
                            ? "border-[var(--color-brand-primary)] bg-[color-mix(in_srgb,var(--color-brand-primary)_10%,transparent)] text-[var(--color-brand-primary)]"
                            : "border-[var(--color-border)] hover:bg-[var(--color-muted)]"
                        }`}
                      >
                        {v}
                      </button>
                    </li>
                  );
                })}
              </ul>
              <p className="mt-2 text-xs text-[var(--color-muted-foreground)]">
                {draft.vocations.length}/3 selected
              </p>
            </div>
          )}

          {step === "bio" && (
            <div>
              <label htmlFor="bio" className="block text-sm font-medium">
                Tell creators what you&apos;re into. <span className="text-[var(--color-muted-foreground)]">(optional)</span>
              </label>
              <textarea
                id="bio"
                className="mt-2 w-full rounded-md border border-[var(--color-input)] bg-[var(--color-background)] px-3 py-2 text-sm focus-visible:border-[var(--color-brand-primary)] focus-visible:outline-2 focus-visible:outline-[var(--color-brand-primary)]"
                rows={5}
                maxLength={300}
                placeholder="A short intro: what you make, what you're looking for. 280 chars max."
                value={draft.bio}
                onChange={(e) => setDraft({ ...draft, bio: e.target.value })}
              />
              <p className="mt-1 text-xs text-[var(--color-muted-foreground)]">
                {draft.bio.length}/300
              </p>
            </div>
          )}

          {step === "location" && (
            <div>
              <label htmlFor="location_label" className="block text-sm font-medium">
                Where are you based?
              </label>
              <Input
                id="location_label"
                type="text"
                className="mt-2"
                placeholder="e.g. Brooklyn, NY"
                value={draft.location_label}
                onChange={(e) => setDraft({ ...draft, location_label: e.target.value })}
              />
              <label className="mt-3 flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.open_to_remote}
                  onChange={(e) => setDraft({ ...draft, open_to_remote: e.target.checked })}
                />
                I&apos;m open to remote collaboration.
              </label>
            </div>
          )}

          {step === "review" && (
            <div className="space-y-3 text-sm">
              <h2 className="text-lg font-semibold">Confirm your profile</h2>
              <dl className="space-y-2">
                <div>
                  <dt className="text-xs uppercase text-[var(--color-muted-foreground)]">Name</dt>
                  <dd>{draft.display_name}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-[var(--color-muted-foreground)]">Vocations</dt>
                  <dd>{draft.vocations.join(", ") || "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-[var(--color-muted-foreground)]">Bio</dt>
                  <dd className="whitespace-pre-wrap">{draft.bio || "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-[var(--color-muted-foreground)]">Location</dt>
                  <dd>
                    {draft.location_label || "—"}
                    {draft.open_to_remote ? " · Open to remote" : ""}
                  </dd>
                </div>
              </dl>
            </div>
          )}

          {error && (
            <div
              role="alert"
              className="rounded-md border border-[var(--color-destructive)] bg-[color-mix(in_srgb,var(--color-destructive)_10%,white)] px-3 py-2 text-sm text-[var(--color-destructive)]"
            >
              {error}
            </div>
          )}

          <div className="flex items-center justify-between gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={back}
              disabled={stepIndex === 0 || submitting}
            >
              Back
            </Button>
            {step !== "review" ? (
              <Button type="button" onClick={next} disabled={!canAdvance}>
                Continue
              </Button>
            ) : (
              <Button type="button" onClick={submit} disabled={submitting}>
                {submitting ? "Saving…" : "Finish setup"}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
