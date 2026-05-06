import { Button } from "@/components/ui/button";

interface PaginationControlsProps {
  offset: number;
  limit: number;
  count: number;
  onPrev: () => void;
  onNext: () => void;
}

export function PaginationControls({
  offset,
  limit,
  count,
  onPrev,
  onNext,
}: PaginationControlsProps) {
  return (
    <div className="mt-4 flex gap-2">
      <Button variant="ghost" disabled={offset === 0} onClick={onPrev}>
        ← Previous
      </Button>
      <Button variant="ghost" disabled={count < limit} onClick={onNext}>
        Next →
      </Button>
    </div>
  );
}
