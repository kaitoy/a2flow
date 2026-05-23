import { Button } from "@/components/ui/button";

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
  return (
    <div className="mt-4 flex gap-2">
      <Button variant="secondary" disabled={offset === 0} onClick={onPrev}>
        ← Previous
      </Button>
      <Button variant="secondary" disabled={count < limit} onClick={onNext}>
        Next →
      </Button>
    </div>
  );
}
