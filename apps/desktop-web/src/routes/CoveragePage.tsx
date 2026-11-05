import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { fetchCoverageUniverses, updateCoverageUniverse, fetchCoverageCapacityData, downloadCoverageUniverseExcel } from "@/lib/api/coverage";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";
import { UniverseSidebar } from "@/components/coverage/UniverseSidebar";
import { BulkCompanyManagerModal } from "@/components/coverage/BulkCompanyManagerModal";
import { CoverageMethodologyModal } from "@/components/coverage/CoverageMethodologyModal";
import { DashboardHub, CreateUniverseModal, DuplicateUniverseModal } from "@/components/coverage/UniverseLifecycle";
import { UniverseSummarySection } from "@/components/coverage/UniverseSummarySection";
import { PrioritizationSection } from "@/components/coverage/PrioritizationSection";
import { WorkQueueSection } from "@/components/coverage/WorkQueueSection";
import { CapacitySection } from "@/components/coverage/CapacitySection";

type Props = {
  section: "universes" | "prioritization" | "work-queue" | "capacity";
};

export function CoveragePage({ section }: Props) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [activeUniverseId, setActiveUniverseId] = useState<string>(() => {
    return localStorage.getItem("active_coverage_universe_id") || "";
  });
  const [showArchived, setShowArchived] = useState(false);

  // Modal and custom workflow states
  const [isBulkModalOpen, setIsBulkModalOpen] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isDuplicateModalOpen, setIsDuplicateModalOpen] = useState(false);
  const [duplicateUniverseId, setDuplicateUniverseId] = useState("");
  const [isMethodologyOpen, setIsMethodologyOpen] = useState(false);
  const [methodologyTab, setMethodologyTab] = useState<"scoring" | "capacity">("scoring");

  const universesQuery = useQuery({
    queryKey: ["coverage-universes"],
    queryFn: fetchCoverageUniverses,
  });

  const universes = universesQuery.data || [];
  const filteredUniverses = useMemo(() => {
    return universes.filter((u) => showArchived || u.status !== "archived");
  }, [universes, showArchived]);

  // Land on empty/dashboard if activeUniverseId is empty or not found in filtered list
  const activeUniverse = filteredUniverses.find((u) => u.id === activeUniverseId);
  const currentUniverseId = activeUniverse?.id || "";

  const capacityQuery = useQuery({
    queryKey: ["coverage-capacity", currentUniverseId],
    queryFn: () => fetchCoverageCapacityData(currentUniverseId),
    enabled: !!currentUniverseId,
  });

  const archiveMutation = useMutation({
    mutationFn: (newStatus: string) => {
      const payload = {
        id: currentUniverseId,
        name: activeUniverse?.name || "",
        purpose: activeUniverse?.purpose || "",
        benchmark: activeUniverse?.benchmark || "",
        status: newStatus,
      };
      return updateCoverageUniverse(payload);
    },
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["coverage-universes"] });
      alert(activeUniverse?.status === "archived" ? "Workspace restored!" : "Workspace archived!");
      if (variables === "archived") {
        handleSelectUniverse("");
      }
    },
    onError: (err) => alert(String(err))
  });

  useEffect(() => {
    if (!currentUniverseId && section !== "universes") {
      navigate("/coverage", { replace: true });
    }
  }, [currentUniverseId, section, navigate]);

  useEffect(() => {
    // If activeUniverseId was set but is not found in filtered list (e.g. deleted/archived), clear it
    if (activeUniverseId && !activeUniverse) {
      setActiveUniverseId("");
      localStorage.removeItem("active_coverage_universe_id");
      window.dispatchEvent(new Event("storage"));
    }
  }, [activeUniverse, activeUniverseId]);

  const handleSelectUniverse = (id: string) => {
    setActiveUniverseId(id);
    if (id) {
      localStorage.setItem("active_coverage_universe_id", id);
    } else {
      localStorage.removeItem("active_coverage_universe_id");
    }
    window.dispatchEvent(new Event("storage"));
  };

  if (universesQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading coverage universes..." />;
  }

  if (universesQuery.isError) {
    return (
      <StateBanner
        variant="error"
        title="Could not load universes"
        message={String(universesQuery.error)}
        onRetry={() => void universesQuery.refetch()}
      />
    );
  }

  const handleExport = async () => {
    try {
      const { filename, content_base64 } = await downloadCoverageUniverseExcel(currentUniverseId);
      const blob = await fetch(`data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,${content_base64}`).then((r) => r.blob());
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      link.click();
    } catch (err) {
      alert(String(err));
    }
  };

  return (
    <div className="flex h-[calc(100vh-48px)] overflow-hidden select-none">
      {currentUniverseId && (
        <UniverseSidebar
          universes={filteredUniverses}
          activeUniverseId={currentUniverseId}
          onSelectUniverse={handleSelectUniverse}
          onOpenCreateModal={() => setIsCreateModalOpen(true)}
        />
      )}

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6 min-w-0 bg-[var(--color-surface-1)]">
        {!currentUniverseId ? (
          <DashboardHub
            universes={filteredUniverses}
            showArchived={showArchived}
            onShowArchivedChange={setShowArchived}
            onSelectUniverse={handleSelectUniverse}
            onOpenCreateModal={() => setIsCreateModalOpen(true)}
            onOpenDuplicateModal={(id) => {
              setDuplicateUniverseId(id);
              setIsDuplicateModalOpen(true);
            }}
            onArchiveUniverse={async (id, currentStatus) => {
              const u = universes.find((univ) => univ.id === id);
              if (!u) return;
              const newStatus = currentStatus === "archived" ? "active" : "archived";
              await updateCoverageUniverse({
                id,
                name: u.name,
                purpose: u.purpose || "",
                benchmark: u.benchmark || "",
                status: newStatus,
              });
              if (newStatus === "archived" && id === activeUniverseId) {
                handleSelectUniverse("");
              }
              void universesQuery.refetch();
            }}
          />
        ) : (
          <>
            {/* Header cluster */}
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--color-border-subtle)] pb-4">
              <div className="space-y-1">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => handleSelectUniverse("")}
                    className="text-zinc-500 hover:text-cyan-400 font-mono text-2xs uppercase tracking-wider cursor-pointer border border-zinc-800 rounded px-1.5 py-0.5 bg-zinc-950/20"
                  >
                    ← Dashboard
                  </button>
                  <span className="text-zinc-700">/</span>
                  <span className="font-mono text-xs text-[var(--color-text-tertiary)] uppercase tracking-wider">Active Workspace</span>
                  <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-wide">
                    {activeUniverse?.name} [{activeUniverse?.analysis_type}]
                  </h2>
                  <label className="flex items-center gap-1.5 ml-3 cursor-pointer text-2xs text-[var(--color-text-secondary)] font-mono select-none">
                    <input
                      type="checkbox"
                      checked={showArchived}
                      onChange={(e) => setShowArchived(e.target.checked)}
                      className="bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded accent-cyan-600"
                    />
                    Show Archived
                  </label>
                </div>
                {activeUniverse?.purpose && (
                  <p className="text-xs text-[var(--color-text-secondary)] italic">{activeUniverse.purpose}</p>
                )}
              </div>
              <div className="flex items-center gap-3">
                <Button variant="ghost" onClick={handleExport} disabled={!currentUniverseId}>
                  Export to Excel
                </Button>
                <Button variant="ghost" onClick={() => {
                  setDuplicateUniverseId(currentUniverseId);
                  setIsDuplicateModalOpen(true);
                }}>
                  Duplicate
                </Button>
                {activeUniverse?.status === "archived" ? (
                  <Button
                    variant="primary"
                    onClick={() => archiveMutation.mutate("active")}
                    disabled={archiveMutation.isPending}
                  >
                    Restore Workspace
                  </Button>
                ) : (
                  <Button
                    variant="ghost"
                    onClick={() => archiveMutation.mutate("archived")}
                    disabled={archiveMutation.isPending}
                  >
                    Archive Workspace
                  </Button>
                )}
              </div>
            </div>

            {/* Main Area */}
            {section === "universes" && activeUniverse && (
              <UniverseSummarySection
                universe={activeUniverse}
                onOpenMethodology={(tab) => {
                  setMethodologyTab(tab);
                  setIsMethodologyOpen(true);
                }}
                onSelectUniverse={handleSelectUniverse}
              />
            )}

            {section === "prioritization" && currentUniverseId && (
              <PrioritizationSection
                universeId={currentUniverseId}
                onOpenBulkModal={() => setIsBulkModalOpen(true)}
                onOpenMethodology={(tab) => {
                  setMethodologyTab(tab);
                  setIsMethodologyOpen(true);
                }}
              />
            )}

            {section === "work-queue" && currentUniverseId && (
              <WorkQueueSection
                universeId={currentUniverseId}
                onOpenMethodology={(tab) => {
                  setMethodologyTab(tab);
                  setIsMethodologyOpen(true);
                }}
              />
            )}

            {section === "capacity" && currentUniverseId && (
              <CapacitySection
                universeId={currentUniverseId}
                onOpenMethodology={(tab) => {
                  setMethodologyTab(tab);
                  setIsMethodologyOpen(true);
                }}
              />
            )}
          </>
        )}
      </div>

      <CreateUniverseModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSuccess={(id) => {
          handleSelectUniverse(id);
        }}
      />

      <DuplicateUniverseModal
        isOpen={isDuplicateModalOpen}
        onClose={() => setIsDuplicateModalOpen(false)}
        universeId={duplicateUniverseId}
        onSuccess={(id) => {
          handleSelectUniverse(id);
        }}
      />

      <BulkCompanyManagerModal
        isOpen={isBulkModalOpen}
        onClose={() => setIsBulkModalOpen(false)}
        universeId={currentUniverseId}
        onSuccess={() => {
          void queryClient.invalidateQueries({ queryKey: ["coverage-scores", currentUniverseId] });
        }}
      />

      <CoverageMethodologyModal
        isOpen={isMethodologyOpen}
        onClose={() => setIsMethodologyOpen(false)}
        defaultTab={methodologyTab}
        availableHours={capacityQuery.data?.available_hours || 1600}
      />
    </div>
  );
}
