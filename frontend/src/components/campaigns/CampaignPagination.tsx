import React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface CampaignPaginationProps {
  currentPage: number;
  pageSize: number;
  totalItems?: number;
  itemCountOnPage?: number;
  hasNextPage?: boolean;
  onPageChange: (page: number) => void;
}

export const CampaignPagination: React.FC<CampaignPaginationProps> = ({
  currentPage,
  pageSize,
  totalItems,
  itemCountOnPage,
  hasNextPage,
  onPageChange,
}) => {
  const currentCount =
    itemCountOnPage !== undefined
      ? itemCountOnPage
      : totalItems !== undefined
      ? Math.max(0, Math.min(totalItems - (currentPage - 1) * pageSize, pageSize))
      : 0;

  const totalPages =
    totalItems !== undefined
      ? Math.max(1, Math.ceil(totalItems / pageSize))
      : hasNextPage
      ? currentPage + 1
      : currentPage;

  const startItem = currentCount === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endItem = (currentPage - 1) * pageSize + currentCount;

  const canGoPrevious = currentPage > 1;
  const canGoNext =
    hasNextPage !== undefined
      ? hasNextPage
      : totalItems !== undefined
      ? currentPage < totalPages
      : false;

  // Build compact page number array
  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    if (totalPages <= 5) {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      pages.push(1);
      if (currentPage > 3) {
        pages.push("...");
      }
      const start = Math.max(2, currentPage - 1);
      const end = Math.min(totalPages - 1, currentPage + 1);
      for (let i = start; i <= end; i++) {
        pages.push(i);
      }
      if (currentPage < totalPages - 2) {
        pages.push("...");
      }
      pages.push(totalPages);
    }
    return pages;
  };

  return (
    <div className="p-3.5 bg-slate-50/40 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-3 w-full rounded-b-xl">
      <div className="text-xs text-slate-500">
        Showing{" "}
        <span className="font-semibold text-slate-800">
          {startItem}–{endItem}
        </span>{" "}
        {totalItems !== undefined ? (
          <>
            of <span className="font-semibold text-slate-800">{totalItems}</span>{" "}
            campaigns
          </>
        ) : (
          <span>campaigns (page {currentPage})</span>
        )}
      </div>

      <div className="flex items-center gap-1 text-xs">
        {/* Previous */}
        <button
          type="button"
          disabled={!canGoPrevious}
          onClick={() => onPageChange(currentPage - 1)}
          className="px-2.5 py-1 rounded-md text-slate-600 bg-white border border-slate-200/80 hover:bg-slate-50 flex items-center gap-1 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-white shadow-2xs"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          <span>Previous</span>
        </button>

        {/* Page Buttons */}
        {getPageNumbers().map((p, idx) => {
          if (p === "...") {
            return (
              <span key={`ellipsis-${idx}`} className="px-1 text-slate-400">
                ...
              </span>
            );
          }

          const pageNum = p as number;
          const isActive = pageNum === currentPage;

          return (
            <button
              key={pageNum}
              type="button"
              onClick={() => onPageChange(pageNum)}
              className={`w-7 h-7 rounded-md font-medium text-xs transition-colors ${
                isActive
                  ? "bg-indigo-600 text-white shadow-2xs"
                  : "hover:bg-slate-100 text-slate-600"
              }`}
            >
              {pageNum}
            </button>
          );
        })}

        {/* Next */}
        <button
          type="button"
          disabled={!canGoNext}
          onClick={() => onPageChange(currentPage + 1)}
          className="px-2.5 py-1 rounded-md text-slate-600 bg-white border border-slate-200/80 hover:bg-slate-50 flex items-center gap-1 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-white shadow-2xs"
        >
          <span>Next</span>
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
};
