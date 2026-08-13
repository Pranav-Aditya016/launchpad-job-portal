"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import { ApiError, getProfile, uploadResume, type Profile } from "@/lib/api";
import { NavBar } from "@/components/NavBar";
import { Dropzone } from "@/components/Dropzone";
import { ProfileCard } from "@/components/ProfileCard";
import { Button } from "@/components/Button";
import { TextAreaField } from "@/components/Field";

type Stage = "loading" | "empty" | "uploading" | "review" | "paste";

export default function UploadPage() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("loading");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [pasteText, setPasteText] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProfile()
      .then((p) => {
        if (p && p.resume_text) {
          setProfile(p);
          setStage("review");
        } else {
          setStage("empty");
        }
      })
      .catch(() => setStage("empty"));
  }, []);

  async function handleFile(file: File) {
    setError(null);
    setFileName(file.name);
    setStage("uploading");
    try {
      const parsed = await uploadResume(file);
      setProfile(parsed);
      setStage("review");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong reading that file.");
      setStage("empty");
    }
  }

  async function handlePaste() {
    if (!pasteText.trim()) return;
    const file = new File([pasteText], "resume.txt", { type: "text/plain" });
    await handleFile(file);
  }

  const looksThin =
    profile !== null &&
    profile.skills.length === 0 &&
    profile.target_roles.length === 0 &&
    !profile.name;

  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-6 py-14">
        <div className="flex flex-col gap-2">
          <h1 className="text-display">Let&apos;s get you hired.</h1>
          <p className="text-body text-muted max-w-lg">
            Upload your resume once. LaunchPad reads it, scans the roles that match, scores each
            one honestly, and tailors your application — you stay in control of every send.
          </p>
        </div>

        <AnimatePresence mode="wait">
          {stage === "loading" && (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="flex h-48 items-center justify-center text-body text-muted"
            >
              Checking for an existing profile…
            </motion.div>
          )}

          {stage === "empty" && (
            <motion.div
              key="empty"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ type: "spring", bounce: 0, duration: 0.35 }}
              className="flex flex-col gap-4"
            >
              {error && (
                <div className="rounded-xl bg-[color:var(--danger-wash)] px-4 py-3 text-body text-danger">
                  {error}
                </div>
              )}
              <Dropzone onFile={handleFile} />
              <button
                type="button"
                onClick={() => setStage("paste")}
                className="pressable self-center text-[0.875rem] font-medium text-accent"
              >
                Parsing looks off? Paste your resume text instead
              </button>
            </motion.div>
          )}

          {stage === "paste" && (
            <motion.div
              key="paste"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ type: "spring", bounce: 0, duration: 0.35 }}
              className="flex flex-col gap-4"
            >
              <TextAreaField
                label="Resume text"
                rows={12}
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                placeholder="Paste the full text of your resume here…"
              />
              <div className="flex items-center gap-3">
                <Button onClick={handlePaste} disabled={!pasteText.trim()}>
                  Parse text
                </Button>
                <Button variant="ghost" onClick={() => setStage("empty")}>
                  Back to file upload
                </Button>
              </div>
            </motion.div>
          )}

          {stage === "uploading" && (
            <motion.div
              key="uploading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex h-48 flex-col items-center justify-center gap-3 text-body text-muted"
            >
              <span className="h-6 w-6 animate-spin rounded-full border-2 border-[color:var(--border-strong)] border-t-accent" />
              Reading {fileName ?? "your resume"}…
            </motion.div>
          )}

          {stage === "review" && profile && (
            <motion.div
              key="review"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ type: "spring", bounce: 0, duration: 0.35 }}
              className="flex flex-col gap-4"
            >
              <p className="text-headline">Here&apos;s what we found</p>
              {looksThin && (
                <div className="rounded-xl bg-[color:var(--warning-wash)] px-4 py-3 text-body text-warning">
                  This came back sparse — the parser may have struggled with your file. Feel free to
                  fill in the gaps below, or{" "}
                  <button
                    type="button"
                    className="pressable underline"
                    onClick={() => {
                      setProfile(null);
                      setStage("paste");
                    }}
                  >
                    paste your resume text
                  </button>{" "}
                  for a cleaner pass.
                </div>
              )}
              <ProfileCard profile={profile} onChange={setProfile} />
              <div className="flex items-center gap-3">
                <Button size="lg" onClick={() => router.push("/dashboard")}>
                  Continue to dashboard
                </Button>
                <Button variant="ghost" onClick={() => setStage("empty")}>
                  Upload a different resume
                </Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}
