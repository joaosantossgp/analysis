"use client";

import { useCallback, useRef, useState } from "react";

import { type fetchBatchJobStatus } from "@/lib/api";
import {
  computeRefreshProgress,
  getStageProgressFloor,
} from "@/lib/update-base-admin";

export type LogType = "info" | "success" | "warning" | "error" | "dim";

export type LogLine = {
  time: string;
  message: string;
  type: LogType;
};

type PollStatus = Awaited<ReturnType<typeof fetchBatchJobStatus>>;

type UseBatchJobProgressResult = {
  progress: number;
  processed: number;
  successCount: number;
  failCount: number;
  currentCompany: string;
  currentStep: string;
  elapsed: number;
  logs: LogLine[];
  addLog: (message: string, type?: LogType) => void;
  setProgress: (pct: number) => void;
  resetProgress: () => void;
  markInstantSuccess: () => void;
  recordPollTick: (status: PollStatus, startedAt: number) => void;
};

const LOG_CAP = 100;
const STALL_THRESHOLD = 3;

function nowAsLogTime(): string {
  const now = new Date();
  return [now.getHours(), now.getMinutes(), now.getSeconds()]
    .map((part) => String(part).padStart(2, "0"))
    .join(":");
}

export function useBatchJobProgress(): UseBatchJobProgressResult {
  const [progress, setProgress] = useState(0);
  const [processed, setProcessed] = useState(0);
  const [successCount, setSuccessCount] = useState(0);
  const [failCount, setFailCount] = useState(0);
  const [currentCompany, setCurrentCompany] = useState("");
  const [currentStep, setCurrentStep] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [logs, setLogs] = useState<LogLine[]>([]);

  const lastLogCountRef = useRef(0);
  const lastProgressRef = useRef(0);
  const stalledPollCountRef = useRef(0);

  const addLog = useCallback((message: string, type: LogType = "info") => {
    setLogs((current) =>
      [...current, { time: nowAsLogTime(), message, type }].slice(-LOG_CAP),
    );
  }, []);

  const resetProgress = useCallback(() => {
    setProgress(0);
    setProcessed(0);
    setSuccessCount(0);
    setFailCount(0);
    setElapsed(0);
    setCurrentCompany("");
    setCurrentStep("");
    setLogs([]);
    lastLogCountRef.current = 0;
    lastProgressRef.current = 0;
    stalledPollCountRef.current = 0;
  }, []);

  const markInstantSuccess = useCallback(() => {
    setProgress(100);
    setProcessed(1);
    setSuccessCount(1);
    setElapsed(0);
  }, []);

  const recordPollTick = useCallback(
    (status: PollStatus, startedAt: number) => {
      const queued = status.queued || 1;
      const numericPct = Math.min(
        Math.round((status.processed / queued) * 100),
        99,
      );

      setProcessed(status.processed);
      setFailCount(status.failures);
      setSuccessCount(Math.max(0, status.processed - status.failures));
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
      if (status.current_cvm != null) {
        setCurrentCompany(String(status.current_cvm));
      }
      if (status.stage) {
        setCurrentStep(status.stage);
      }

      const incoming = status.log_lines ?? [];
      const newLines = incoming.slice(lastLogCountRef.current);
      lastLogCountRef.current = incoming.length;
      newLines.forEach((line) => addLog(line, "info"));

      const stageFloor = getStageProgressFloor(status.stage ?? null);
      const hasActivity =
        newLines.length > 0 || status.processed !== lastProgressRef.current;
      if (hasActivity) {
        stalledPollCountRef.current = 0;
      } else {
        stalledPollCountRef.current += 1;
      }
      lastProgressRef.current = status.processed;

      const isStalled = stalledPollCountRef.current >= STALL_THRESHOLD;
      const displayPct = computeRefreshProgress({
        numericPct,
        stageFloor,
        isStalled,
      });
      setProgress(displayPct);
    },
    [addLog],
  );

  return {
    progress,
    processed,
    successCount,
    failCount,
    currentCompany,
    currentStep,
    elapsed,
    logs,
    addLog,
    setProgress,
    resetProgress,
    markInstantSuccess,
    recordPollTick,
  };
}
