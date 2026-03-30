/**
 * Reusable loading spinner component with CSS-only animation.
 * Used as a Suspense fallback for lazy-loaded routes and standalone loading states.
 */

interface LoadingSpinnerProps {
  message?: string;
  fullScreen?: boolean;
}

export default function LoadingSpinner({
  message = "Loading...",
  fullScreen = false,
}: LoadingSpinnerProps) {
  const containerClasses = fullScreen
    ? "fixed inset-0 z-50 flex flex-col items-center justify-center bg-white/80 backdrop-blur-sm"
    : "flex flex-col items-center justify-center py-16";

  return (
    <div className={containerClasses}>
      <div
        className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600"
        role="status"
        aria-label={message}
      />
      <p className="mt-4 text-sm font-medium text-slate-500">{message}</p>
    </div>
  );
}
