"use client";

import { Button } from "@/components/ui/button";
import { useT } from "@/i18n/provider";

interface PaginationControlsProps {
  offset: number;
  limit: number;
  count: number;
  onPrev: () => void;
  onNext: () => void;
}

/** Previous/Next pagination controls; disables Previous at offset 0 and Next when the page is not full. */
export function PaginationControls({
  offset,
  limit,
  count,
  onPrev,
  onNext,
}: PaginationControlsProps) {
  const t = useT();
  return (
    <div className="mt-4 flex gap-2">
      <Button variant="secondary" disabled={offset === 0} onClick={onPrev}>
        {t("admin.previous")}
      </Button>
      <Button variant="secondary" disabled={count < limit} onClick={onNext}>
        {t("admin.next")}
      </Button>
    </div>
  );
}
